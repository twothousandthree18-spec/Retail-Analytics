"""
verify_pipeline.py — Automated end-to-end verification of the SQL analytics layer.

Run:
    DATABASE_URL=postgresql://... python sql/verify_pipeline.py

Checks:
  1. PostgreSQL connection and schema (table, row count, columns, data types).
  2. Every SQL script in sql/ (schema + 01..06) executes without error.
  3. Metric consistency between the pandas-cleaned CSV and PostgreSQL
     (revenue, orders, customers, products, units, AOV).
  4. RFM reproduction: SQL segment counts vs the workbook's pandas RFM.

Exits non-zero if any check fails.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal

import pandas as pd
import psycopg2
from dotenv import load_dotenv

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SQL_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(REPO_ROOT, "data", "cleaned_retail_data.csv")

load_dotenv(os.path.join(REPO_ROOT, ".env"))

PASS = "PASS"
FAIL = "FAIL"


def check(name: str, ok: bool, detail: str = "") -> bool:
    status = PASS if ok else FAIL
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))
    return ok


def sql_all(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        return [r[0] for r in cur.fetchall()]


def column_types(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'retail_transactions'
            ORDER BY ordinal_position
            """
        )
        return {r[0]: r[1] for r in cur.fetchall()}


def run_sql_file(conn, path: str) -> None:
    with open(path, "r", encoding="utf-8") as fh:
        sql = fh.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("ERROR: DATABASE_URL is not set (see .env.example).")

    ok_all = True

    # ---- 1. Connection + schema ----
    conn = psycopg2.connect(url, connect_timeout=15)
    ok_all &= check("Connect to PostgreSQL", conn is not None)

    tables = sql_all(conn)
    ok_all &= check("retail_transactions exists", "retail_transactions" in tables)

    n_rows_sql = None
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM retail_transactions")
        n_rows_sql = cur.fetchone()[0]
    ok_all &= check("Row count is 527,390", n_rows_sql == 527_390, f"got {n_rows_sql}")

    types = column_types(conn)
    expected_types = {
        "transaction_id": "bigint",
        "invoice_no": "character varying",
        "stock_code": "character varying",
        "description": "text",
        "quantity": "integer",
        "invoice_date": "timestamp without time zone",
        "unit_price": "numeric",
        "customer_id": "bigint",
        "country": "character varying",
        "total_price": "numeric",
    }
    missing = [c for c in expected_types if c not in types]
    wrong = [f"{c}:{types[c]}" for c in expected_types if c in types and types[c] != expected_types[c]]
    ok_all &= check("All columns present", not missing, f"missing {missing}" if missing else "")
    ok_all &= check("Column types correct", not wrong, ", ".join(wrong) if wrong else "")

    # ---- 2. Execute every SQL script ----
    files = ["schema.sql", "01_sales_analysis.sql", "02_customer_analysis.sql",
             "03_product_analysis.sql", "04_time_analysis.sql", "05_advanced_analytics.sql",
             "06_cohort_retention_analysis.sql"]
    for f in files:
        try:
            run_sql_file(conn, os.path.join(SQL_DIR, f))
            ok_all &= check(f"SQL script executes: {f}", True)
        except Exception as exc:  # noqa: BLE001
            ok_all &= check(f"SQL script executes: {f}", False, str(exc).strip().splitlines()[0])

    # ---- 3. Consistency: CSV (pandas) vs PostgreSQL ----
    df = pd.read_csv(CSV_PATH, dtype={"CustomerID": str, "InvoiceNo": str, "StockCode": str})
    df["CustomerID"] = pd.to_numeric(df["CustomerID"], errors="coerce")
    df["total_price"] = df["Quantity"] * df["UnitPrice"]

    def pd_metric(metric: str) -> Decimal:
        if metric == "revenue":
            return Decimal(str(round(float(df["total_price"].sum()), 2)))
        if metric == "orders":
            return Decimal(str(df["InvoiceNo"].nunique()))
        if metric == "customers":
            return Decimal(str(df["CustomerID"].nunique()))
        if metric == "products":
            return Decimal(str(df["StockCode"].nunique()))
        if metric == "units":
            return Decimal(str(df["Quantity"].sum()))
        if metric == "aov":
            return Decimal(str(round(float(df["total_price"].sum()) / df["InvoiceNo"].nunique(), 2)))
        raise ValueError(metric)

    sql_metrics = {
        "revenue": "SELECT SUM(total_price) FROM retail_transactions",
        "orders": "SELECT COUNT(DISTINCT invoice_no) FROM retail_transactions",
        "customers": "SELECT COUNT(DISTINCT customer_id) FROM retail_transactions",
        "products": "SELECT COUNT(DISTINCT stock_code) FROM retail_transactions",
        "units": "SELECT SUM(quantity) FROM retail_transactions",
        "aov": "SELECT ROUND(SUM(total_price) / COUNT(DISTINCT invoice_no), 2) FROM retail_transactions",
    }
    with conn.cursor() as cur:
        for metric, q in sql_metrics.items():
            cur.execute(q)
            sql_val = Decimal(str(cur.fetchone()[0]))
            pd_val = pd_metric(metric)
            tol = Decimal("0.01")
            ok = abs(sql_val - pd_val) <= tol
            ok_all &= check(
                f"Consistency: {metric}", ok,
                f"SQL={sql_val} vs pandas={pd_val}",
            )

    # ---- 4. RFM reproduction ----
    # SQL RFM (temp table, same rules as the workbook; tie-break by customer_id).
    with conn.cursor() as cur:
        cur.execute("""
            DROP TABLE IF EXISTS customer_rfm;
            CREATE TEMP TABLE customer_rfm AS
            WITH base AS (
                SELECT customer_id, invoice_no, invoice_date, total_price
                FROM retail_transactions WHERE customer_id IS NOT NULL
            ),
            reference AS (SELECT MAX(invoice_date) AS snapshot FROM base),
            rfm AS (
                SELECT b.customer_id,
                       (SELECT snapshot FROM reference)::date - MAX(b.invoice_date)::date AS recency_days,
                       COUNT(DISTINCT b.invoice_no) AS frequency,
                       ROUND(SUM(b.total_price), 2) AS monetary
                FROM base b GROUP BY b.customer_id
            ),
            scored AS (
                SELECT customer_id, recency_days, frequency, monetary,
                       5 - NTILE(4) OVER (ORDER BY recency_days ASC, customer_id ASC) AS r_score,
                       NTILE(4)      OVER (ORDER BY frequency ASC,   customer_id ASC) AS f_score,
                       NTILE(4)      OVER (ORDER BY monetary ASC,    customer_id ASC) AS m_score
                FROM rfm
            )
            SELECT customer_id,
                   CASE
                       WHEN r_score >= 4 AND f_score >= 3 AND m_score >= 3 THEN 'Champions'
                       WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3 THEN 'Loyal Customers'
                       WHEN r_score >= 3 AND f_score >= 2 AND m_score >= 2 THEN 'Potential Loyalists'
                       WHEN r_score >= 3 AND f_score = 1 THEN 'New Customers'
                       WHEN r_score <= 2 AND (f_score >= 3 OR m_score >= 3) THEN 'At Risk'
                       WHEN r_score >= 2 AND (f_score >= 2 OR m_score >= 2) THEN 'Needs Attention'
                       ELSE 'Hibernating'
                   END AS segment
            FROM scored
        """)
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM customer_rfm")
        rfm_rows = cur.fetchone()[0]
        cur.execute("SELECT segment, COUNT(*) FROM customer_rfm GROUP BY segment")
        sql_segments = dict(cur.fetchall())

    # pandas RFM (same logic as the workbook's RFM cell).
    snapshot = df["InvoiceDate"].max() if "InvoiceDate" in df else None
    if snapshot is None:
        df["InvoiceDate"] = pd.to_datetime(df["Invoice Date"], format="%y/%m/%d")
        snapshot = df["InvoiceDate"].max()
    rfm = (
        df[df["CustomerID"].notna()]
        .groupby("CustomerID")
        .agg(Recency=("InvoiceDate", lambda x: (snapshot - x.max()).days),
             Frequency=("InvoiceNo", "nunique"),
             Monetary=("TotalPrice", "sum"))
    )
    rfm["R_Score"] = pd.qcut(rfm["Recency"].rank(method="first"), 4, labels=[4, 3, 2, 1]).astype(int)
    rfm["F_Score"] = pd.qcut(rfm["Frequency"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
    rfm["M_Score"] = pd.qcut(rfm["Monetary"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
    conditions = [
        (rfm["R_Score"] >= 4) & (rfm["F_Score"] >= 3) & (rfm["M_Score"] >= 3),
        (rfm["R_Score"] >= 3) & (rfm["F_Score"] >= 3) & (rfm["M_Score"] >= 3),
        (rfm["R_Score"] >= 3) & (rfm["F_Score"] >= 2) & (rfm["M_Score"] >= 2),
        (rfm["R_Score"] >= 3) & (rfm["F_Score"] == 1),
        (rfm["R_Score"] <= 2) & ((rfm["F_Score"] >= 3) | (rfm["M_Score"] >= 3)),
        (rfm["R_Score"] >= 2) & ((rfm["F_Score"] >= 2) | (rfm["M_Score"] >= 2)),
    ]
    choices = ["Champions", "Loyal Customers", "Potential Loyalists", "New Customers",
               "At Risk", "Needs Attention"]
    import numpy as np

    rfm["Segment"] = np.select(conditions, choices, default="Hibernating")

    pd_segments = rfm["Segment"].value_counts().to_dict()

    ok_all &= check("RFM: same customer count", rfm_rows == len(rfm),
                    f"SQL={rfm_rows} vs pandas={len(rfm)}")
    all_segs = sorted(set(pd_segments) | set(sql_segments))
    seg_ok = all(abs(int(pd_segments.get(s, 0)) - int(sql_segments.get(s, 0))) <= 1 for s in all_segs)
    detail = ", ".join(f"{s}: SQL={sql_segments.get(s, 0)}/pd={pd_segments.get(s, 0)}" for s in all_segs)
    ok_all &= check("RFM: segment counts match pandas", seg_ok, detail)

    # Per-customer segment agreement.
    with conn.cursor() as cur:
        cur.execute("SELECT customer_id, segment FROM customer_rfm")
        sql_map = dict(cur.fetchall())
    pd_map = rfm["Segment"].to_dict()
    common = set(pd_map) & set(sql_map)
    agree = sum(1 for c in common if pd_map[c] == sql_map[c])
    ok_all &= check("RFM: per-customer segment agreement 100%", agree == len(common),
                    f"{agree}/{len(common)}")

    conn.close()

    print()
    print("OVERALL:", "ALL CHECKS PASSED" if ok_all else "SOME CHECKS FAILED")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
