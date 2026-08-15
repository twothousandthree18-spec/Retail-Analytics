"""Data-quality gate + cross-system reconciliation for the pipeline.

This module *validates*, it does not re-implement analytics:

* ``run_data_quality`` checks the cleaned dataset produced by the notebook
  against schema / missing-data / duplicates / numeric / date / business-rule
  expectations and returns PASS / WARNING / FAIL.
* ``*_metrics`` read the same KPIs out of each system (Python cleaned CSV,
  PostgreSQL, the Excel workbook, and the Power BI dataset) using the exact
  definitions already validated in earlier phases.
* ``reconcile`` compares the systems and reports any material disagreement.

Nothing here invents figures: every number is computed from real artifacts.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = [
    "InvoiceNo", "StockCode", "Description", "Quantity", "UnitPrice",
    "CustomerID", "Country", "TotalPrice", "Invoice Date", "Invoice Time",
    "Month", "Year", "Hour",
]
CRITICAL_FIELDS = [
    "InvoiceNo", "StockCode", "Quantity", "UnitPrice", "Country",
    "TotalPrice", "Invoice Date", "Invoice Time",
]

PASS, WARNING, FAIL = "PASS", "WARNING", "FAIL"


def read_cleaned(path: Path | str | None = None) -> pd.DataFrame:
    """Load the cleaned analytical dataset (single source of truth)."""
    p = Path(path) if path is not None else Path(__file__).resolve().parents[1] / "data" / "cleaned_retail_data.csv"
    return pd.read_csv(p, low_memory=False, dtype={"InvoiceNo": str, "StockCode": str})


def _status_text(status: str) -> str:
    return status


def run_data_quality(df: pd.DataFrame) -> dict:
    """Validate the cleaned analytical dataset. Returns a quality report dict."""
    checks: list[dict] = []
    rows, cols = len(df), len(df.columns)

    def add(name: str, status: str, detail: str = "") -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    # ---- schema ----
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    add("Schema: required columns", FAIL if missing_cols else PASS,
        f"found {cols} columns; missing {missing_cols}" if missing_cols else f"{cols} columns")

    has = lambda *cs: all(c in df.columns for c in cs)  # noqa: E731
    numeric_ok = all(has(c) and pd.api.types.is_numeric_dtype(df[c])
                     for c in ("Quantity", "UnitPrice", "TotalPrice"))
    add("Schema: numeric dtypes", FAIL if not numeric_ok else PASS, "Quantity/UnitPrice/TotalPrice")

    # ---- missing data ----
    nulls = {c: int(df[c].isna().sum()) for c in CRITICAL_FIELDS if c in df.columns}
    bad = {c: n for c, n in nulls.items() if n > 0}
    add("Missing: critical fields", FAIL if bad else PASS,
        f"{sum(bad.values())} nulls {bad}" if bad else "0 nulls in critical fields")
    n_cust_null = int(df["CustomerID"].isna().sum()) if has("CustomerID") else 0
    add("Missing: CustomerID", WARNING if n_cust_null else PASS,
        f"{n_cust_null:,} rows (kept per validated logic - customer-level metrics use non-null customers)")
    n_desc_null = int(df["Description"].isna().sum()) if has("Description") else 0
    add("Missing: Description", WARNING if n_desc_null else PASS,
        f"{n_desc_null:,} rows (informational - preserved as NULL in PostgreSQL)")

    # ---- duplicates ----
    n_dup = int(df.duplicated().sum())
    add("Duplicates: full rows", FAIL if n_dup else PASS, f"{n_dup:,}" if n_dup else "0")

    # ---- numeric integrity ----
    neg_qty = int((df["Quantity"] <= 0).sum()) if has("Quantity") else 0
    neg_price = int((df["UnitPrice"] <= 0).sum()) if has("UnitPrice") else 0
    neg_total = int((df["TotalPrice"] <= 0).sum()) if has("TotalPrice") else 0
    add("Numeric: negative quantity", WARNING if neg_qty else PASS,
        f"{neg_qty:,} rows (kept per validated cleaning - cancellations removed by invoice prefix only)")
    add("Numeric: non-positive unit price", WARNING if neg_price else PASS, f"{neg_price:,} rows (kept per validated cleaning)")
    add("Numeric: non-positive TotalPrice", WARNING if neg_total else PASS, f"{neg_total:,} rows (kept per validated cleaning)")
    nan_num = int(df[["Quantity", "UnitPrice", "TotalPrice"]].isna().sum().sum()) if has("Quantity", "UnitPrice", "TotalPrice") else 0
    add("Numeric: no NaN in numerics", FAIL if nan_num else PASS, f"{nan_num} NaN" if nan_num else "0")

    # ---- dates ----
    if has("Invoice Date", "Invoice Time"):
        parsed = pd.to_datetime(df["Invoice Date"].astype(str) + " " + df["Invoice Time"].astype(str),
                                format="%y/%m/%d %H:%M:%S", errors="coerce")
        n_bad_date = int(parsed.isna().sum())
        dmin, dmax = parsed.min(), parsed.max()
        in_window = dmin >= pd.Timestamp("2010-12-01") and dmax <= pd.Timestamp("2011-12-31")
        add("Dates: all parsed", FAIL if n_bad_date else PASS, f"{n_bad_date} malformed" if n_bad_date else "0 malformed")
        add("Dates: expected window 2010-12..2011-12", PASS if in_window else FAIL,
            f"{dmin:%Y-%m-%d} .. {dmax:%Y-%m-%d}")
    else:
        n_bad_date = 0
        add("Dates: all parsed", FAIL, "Invoice Date/Invoice Time missing")

    # ---- business rules ----
    n_canc = int(df["InvoiceNo"].astype(str).str.startswith("C").sum()) if has("InvoiceNo") else 0
    add("Business: cancellations removed", FAIL if n_canc else PASS, f"{n_canc:,} remaining" if n_canc else "0 remaining")
    tol_err = float((df["TotalPrice"] - df["Quantity"] * df["UnitPrice"]).abs().max()) \
        if has("TotalPrice", "Quantity", "UnitPrice") else float("inf")
    add("Business: TotalPrice == Quantity * UnitPrice", FAIL if tol_err > 0.01 else PASS,
        f"max abs diff {tol_err:.2e}")
    n_cust = int(df["CustomerID"].nunique()) if has("CustomerID") else 0
    add("Business: customer attribution", PASS if n_cust == 4_339 else WARNING, f"{n_cust:,} distinct customers")

    has_fail = any(c["status"] == FAIL for c in checks)
    has_warn = any(c["status"] == WARNING for c in checks)
    overall = FAIL if has_fail else (WARNING if has_warn else PASS)

    return {
        "rows": rows,
        "columns": cols,
        "checks": checks,
        "status": overall,
        "summary": {
            "missing_critical": sum(nulls.values()),
            "duplicate_rows": n_dup,
            "invalid_dates": n_bad_date,
            "cancellations_remaining": n_canc,
            "null_customer_id_rows": n_cust_null,
            "distinct_customers": n_cust,
        },
    }


# ---------------------------------------------------------------------------
# Per-system KPI readers
# ---------------------------------------------------------------------------

def python_metrics(df: pd.DataFrame) -> dict:
    """KPIs computed from the cleaned dataset (the Python truth)."""
    rev = round(float(df["TotalPrice"].sum()), 2)
    orders = int(df["InvoiceNo"].nunique())
    customers = int(df["CustomerID"].nunique())
    units = int(df["Quantity"].sum())
    attributed = df[df["CustomerID"].notna()]
    per_cust = attributed.groupby("CustomerID")["InvoiceNo"].nunique()
    return {
        "revenue": rev,
        "orders": orders,
        "customers": customers,
        "products": int(df["StockCode"].nunique()),
        "products_desc": int(df["Description"].nunique()),
        "units": units,
        "aov": round(rev / orders, 2),
        "repeat_customers": int((per_cust > 1).sum()),
        "customer_revenue": round(float(attributed["TotalPrice"].sum()), 2),
        "cohort_customers": customers,
        "rfm": compute_rfm_segments(df),
    }


def sql_metrics(conn) -> dict:
    """KPIs read directly from PostgreSQL (the SQL truth)."""
    with conn.cursor() as cur:
        def q(sql):
            cur.execute(sql)
            return cur.fetchone()[0]

        revenue = float(q("SELECT ROUND(SUM(total_price)::numeric, 2) FROM retail_transactions"))
        orders = int(q("SELECT COUNT(DISTINCT invoice_no) FROM retail_transactions"))
        customers = int(q("SELECT COUNT(DISTINCT customer_id) FROM retail_transactions WHERE customer_id IS NOT NULL"))
        products = int(q("SELECT COUNT(DISTINCT stock_code) FROM retail_transactions"))
        units = int(q("SELECT SUM(quantity) FROM retail_transactions"))
        aov = float(q("SELECT ROUND(SUM(total_price)::numeric / COUNT(DISTINCT invoice_no), 2) FROM retail_transactions"))
        repeat = int(q(
            "SELECT COUNT(*) FROM ("
            "  SELECT customer_id FROM retail_transactions WHERE customer_id IS NOT NULL"
            "  GROUP BY customer_id HAVING COUNT(DISTINCT invoice_no) > 1) x"))
        customer_revenue = float(q(
            "SELECT ROUND(SUM(total_price)::numeric, 2) FROM retail_transactions WHERE customer_id IS NOT NULL"))

        cur.execute(
            "DROP TABLE IF EXISTS rfm_recon;"
            "CREATE TEMP TABLE rfm_recon AS "
            "WITH base AS ("
            "  SELECT customer_id, invoice_no, invoice_date, total_price"
            "  FROM retail_transactions WHERE customer_id IS NOT NULL),"
            "reference AS (SELECT MAX(invoice_date) AS snapshot FROM base),"
            "rfm AS ("
            "  SELECT b.customer_id,"
            "         (SELECT snapshot FROM reference)::date - MAX(b.invoice_date)::date AS recency_days,"
            "         COUNT(DISTINCT b.invoice_no) AS frequency,"
            "         ROUND(SUM(b.total_price), 2) AS monetary"
            "  FROM base b GROUP BY b.customer_id),"
            "scored AS ("
            "  SELECT customer_id, recency_days, frequency, monetary,"
            "         5 - NTILE(4) OVER (ORDER BY recency_days ASC, customer_id ASC) AS r_score,"
            "         NTILE(4) OVER (ORDER BY frequency ASC, customer_id ASC) AS f_score,"
            "         NTILE(4) OVER (ORDER BY monetary ASC, customer_id ASC) AS m_score"
            "  FROM rfm),"
            "segmented AS ("
            "  SELECT customer_id,"
            "         CASE WHEN r_score >= 4 AND f_score >= 3 AND m_score >= 3 THEN 'Champions'"
            "              WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3 THEN 'Loyal Customers'"
            "              WHEN r_score >= 3 AND f_score >= 2 AND m_score >= 2 THEN 'Potential Loyalists'"
            "              WHEN r_score >= 3 AND f_score = 1 THEN 'New Customers'"
            "              WHEN r_score <= 2 AND (f_score >= 3 OR m_score >= 3) THEN 'At Risk'"
            "              WHEN r_score >= 2 AND (f_score >= 2 OR m_score >= 2) THEN 'Needs Attention'"
            "              ELSE 'Hibernating' END AS segment"
            "  FROM scored)"
            "SELECT segment, COUNT(*) AS n FROM segmented GROUP BY segment")
        conn.commit()
        cur.execute("SELECT segment, n FROM rfm_recon")
        rfm = dict(cur.fetchall())

    return {
        "revenue": revenue,
        "orders": orders,
        "customers": customers,
        "products": products,
        "units": units,
        "aov": aov,
        "repeat_customers": repeat,
        "customer_revenue": customer_revenue,
        "cohort_customers": customers,
        "rfm": rfm,
    }


def compute_rfm_segments(df: pd.DataFrame) -> dict:
    """Segment counts using the exact validated workbook RFM logic."""
    rfm_base = df.dropna(subset=["CustomerID"]).copy()
    rfm_base["InvoiceDate"] = pd.to_datetime(rfm_base["Invoice Date"], format="%y/%m/%d")
    snapshot = rfm_base["InvoiceDate"].max()
    rfm = rfm_base.groupby("CustomerID").agg(
        Recency=("InvoiceDate", lambda x: (snapshot - x.max()).days),
        Frequency=("InvoiceNo", "nunique"),
        Monetary=("TotalPrice", "sum"),
    )
    rfm["R_Score"] = pd.qcut(rfm["Recency"].rank(method="first"), 4, labels=[4, 3, 2, 1]).astype(int)
    rfm["F_Score"] = pd.qcut(rfm["Frequency"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
    rfm["M_Score"] = pd.qcut(rfm["Monetary"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)

    def seg(row):
        R, F, M = row["R_Score"], row["F_Score"], row["M_Score"]
        if R >= 4 and F >= 3 and M >= 3:
            return "Champions"
        if R >= 3 and F >= 3 and M >= 3:
            return "Loyal Customers"
        if R >= 3 and F >= 2 and M >= 2:
            return "Potential Loyalists"
        if R >= 3 and F == 1:
            return "New Customers"
        if R <= 2 and (F >= 3 or M >= 3):
            return "At Risk"
        if R >= 2 and (F >= 2 or M >= 2):
            return "Needs Attention"
        return "Hibernating"

    return rfm.apply(seg, axis=1).value_counts().to_dict()


def excel_metrics(path: Path) -> dict:
    """KPIs read from the Excel workbook (Summary Dashboard + RFM sheet)."""
    xl = pd.ExcelFile(path)
    sd = xl.parse("Summary Dashboard").set_index("KPI")["Value"]
    rfm_sheet = xl.parse("RFM Customer Segmentation")
    xl.close()

    repeat = len(pd.read_excel(path, sheet_name="Repeat Customers", header=0))
    return {
        "revenue": round(float(sd["Total Revenue"]), 2),
        "orders": int(sd["Total Orders"]),
        "customers": int(sd["Total Customers"]),
        "products": int(sd["Total Products"]),          # Description-based in the workbook
        "products_desc": int(sd["Total Products"]),
        "units": int(sd["Total Quantity Sold"]),
        "aov": float(sd["Average Order Value"]),
        "repeat_customers": int(repeat),
        "customer_revenue": None,                        # not exposed in the workbook
        "cohort_customers": None,
        "rfm": rfm_sheet["Segment"].value_counts().to_dict(),
    }


def pbi_metrics(dataset_dir: Path) -> dict:
    """KPIs computed from the Power BI-ready dataset CSVs."""
    fact = pd.read_csv(dataset_dir / "FactSales.csv", low_memory=False,
                       dtype={"invoice_no": str, "stock_code": str})
    cust = pd.read_csv(dataset_dir / "DimCustomer.csv", dtype={"customer_id": str})
    rev = round(float(fact["total_price"].sum()), 2)
    orders = int(fact["invoice_no"].nunique())
    attributed = fact[fact["customer_id"].notna()]
    per_cust = attributed.groupby("customer_id")["invoice_no"].nunique()
    return {
        "revenue": rev,
        "orders": orders,
        "customers": int(attributed["customer_id"].nunique()),
        "products": int(fact["stock_code"].nunique()),
        "units": int(fact["quantity"].sum()),
        "aov": round(rev / orders, 2),
        "repeat_customers": int((per_cust > 1).sum()),
        "customer_revenue": round(float(attributed["total_price"].sum()), 2),
        "cohort_customers": int(len(cust)),
        "rfm": cust["segment"].value_counts().to_dict(),
    }


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------

# key -> (label, tolerance, how to render, warn-only-on-Excel-diff)
_METRICS = [
    ("revenue", "Revenue", 0.02, "£{:,.2f}", False),
    ("orders", "Orders", 0, "{:,}", False),
    ("customers", "Customers", 0, "{:,}", False),
    ("products", "Products", 0, "{:,}", False),
    ("units", "Units", 0, "{:,}", False),
    ("aov", "AOV", 0.01, "£{:,.2f}", False),
    ("repeat_customers", "Repeat Customers", 0, "{:,}", True),
    ("customer_revenue", "Customer Revenue (attributed)", 0.02, "£{:,.2f}", False),
    ("cohort_customers", "Cohort Customers", 0, "{:,}", False),
]
_RFM_SEGMENTS = [
    "Champions", "Loyal Customers", "Potential Loyalists", "New Customers",
    "At Risk", "Needs Attention", "Hibernating",
]


def _fmt(v, fmt):
    return fmt.format(v) if v is not None else "n/a"


def reconcile(py: dict, sql: dict, excel: dict | None, pbi: dict | None) -> dict:
    """Compare KPIs across systems. Returns a list of result rows + status."""
    rows: list[dict] = []
    include_excel = excel is not None
    include_pbi = pbi is not None

    def systems_for(key):
        systems = [("python", py)]
        if sql is not None:
            systems.append(("sql", sql))
        if include_excel and excel.get(key) is not None:
            systems.append(("excel", excel))
        if include_pbi and pbi.get(key) is not None:
            systems.append(("pbi", pbi))
        return systems

    def close(a, b, tol):
        if tol == 0:
            return abs(a - b) < 1e-9
        return abs(a - b) <= tol

    def compare(key, tol, label, fmt, special_note="", warn_on_excel_diff=False,
                skip_excel_compare=False):
        systems = systems_for(key)
        if skip_excel_compare:
            systems = [(n, m) for n, m in systems if n != "excel"]
        vals = [(name, m[key]) for name, m in systems]
        if len(vals) < 2:
            status = PASS
        else:
            first = vals[0][1]
            bad = [(n, v) for n, v in vals[1:] if not close(first, v, tol)]
            if bad:
                if warn_on_excel_diff and all(n == "excel" for n, _ in bad):
                    status = WARNING
                    special_note = (special_note + " " if special_note else "") + \
                        "Excel workbook counts repeat customers before cancellation removal (notebook cell order); " \
                        "the validated benchmark excludes cancellations - Python=SQL=PBI agree."
                else:
                    status = FAIL
            else:
                status = PASS
        row = {
            "metric": label,
            "python": _fmt(py.get(key), fmt),
            "sql": _fmt(sql.get(key), fmt) if sql is not None else "n/a",
            "excel": _fmt(excel.get(key), fmt) if include_excel and excel.get(key) is not None else "n/a",
            "pbi": _fmt(pbi.get(key), fmt) if include_pbi and pbi.get(key) is not None else "n/a",
            "status": status,
            "note": special_note or ("" if len(vals) > 1 else "single source"),
        }
        rows.append(row)
        return status

    ok = True
    for key, label, tol, fmt, warn_xl in _METRICS:
        note = ""
        skip_excel = False
        if key == "products" and include_excel and excel.get("products") is not None:
            desc_eq = close(excel["products"], py["products_desc"], 0)
            note = ("" if desc_eq else "MISMATCH ") + \
                   "(Excel counts distinct Description; other systems count distinct StockCode - verified internally)"
            ok = ok and desc_eq
            skip_excel = True
        st = compare(key, tol, label, fmt, note, warn_on_excel_diff=warn_xl,
                     skip_excel_compare=skip_excel)
        ok = ok and (st != FAIL)

    for seg in _RFM_SEGMENTS:
        def val(m):
            return m.get("rfm", {}).get(seg)
        systems = [("python", py)]
        if sql is not None:
            systems.append(("sql", sql))
        if include_excel and excel.get("rfm") is not None:
            systems.append(("excel", excel))
        if include_pbi and pbi.get("rfm") is not None:
            systems.append(("pbi", pbi))
        vals = [(n, val(m)) for n, m in systems if val(m) is not None]
        if not vals:
            continue
        first = vals[0][1]
        st = PASS if all(abs(first - v) == 0 for _, v in vals[1:]) else FAIL
        ok = ok and (st != FAIL)
        rows.append({
            "metric": f"RFM: {seg}",
            "python": f"{val(py):,}" if val(py) is not None else "n/a",
            "sql": f"{val(sql):,}" if sql is not None and val(sql) is not None else "n/a",
            "excel": f"{val(excel):,}" if include_excel and val(excel) is not None else "n/a",
            "pbi": f"{val(pbi):,}" if include_pbi and val(pbi) is not None else "n/a",
            "status": st,
            "note": "" if len(vals) > 1 else "single source",
        })

    return {"rows": rows, "status": PASS if ok else FAIL}
