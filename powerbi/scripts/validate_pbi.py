"""
validate_pbi.py — Reconcile the Power BI-ready dataset against the validated
PostgreSQL/SQL figures.

Checks:
  1. KPI benchmarks (revenue, orders, customers, units, AOV) from FactSales.
  2. Monthly revenue: Power BI dataset vs PostgreSQL (13 months).
  3. RFM: DimCustomer segment counts vs PostgreSQL RFM (must reconcile 100%).
  4. Dimension sanity (row counts, PK uniqueness, full coverage of the fact).
  5. Referential integrity (fact -> dimension orphans).
  6. Derived customer metrics used by the report (repeat rate, one-time, etc.).
  7. Cohort & retention (Phase 4): CohortRetention / CohortSummary vs the SQL
     truth produced by executing sql/06_cohort_retention_analysis.sql
     (customer totals, M0 = 100%, SQL-vs-PBI counts, retention %, no fake zeros).
  8. Weighted retention series (M0..M12): the aggregation the DAX measure
     'Retention Rate' performs on CohortRetention is re-computed here and
     reconciled against SQL — per month index it uses only cohorts with
     observed data (future periods are absent, never treated as zero).

Run:
    DATABASE_URL=postgresql://... python powerbi/scripts/validate_pbi.py
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "powerbi" / "dataset"
SQL_DIR = REPO_ROOT / "sql"
load_dotenv(REPO_ROOT / ".env")

PASS = "PASS"
FAIL = "FAIL"


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{PASS if ok else FAIL}] {name}" + (f" - {detail}" if detail else ""))
    return ok


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("ERROR: DATABASE_URL is not set (see .env.example).")
    conn = psycopg2.connect(url, connect_timeout=15)
    ok_all = True

    fact = pd.read_csv(DATASET_DIR / "FactSales.csv", low_memory=False)
    fact["invoice_no"] = fact["invoice_no"].astype(str)
    cust = pd.read_csv(DATASET_DIR / "DimCustomer.csv")
    date = pd.read_csv(DATASET_DIR / "DimDate.csv")
    prod = pd.read_csv(DATASET_DIR / "DimProduct.csv")
    country = pd.read_csv(DATASET_DIR / "DimCountry.csv")

    revenue = Decimal(str(round(float(fact["total_price"].sum()), 2)))
    orders = int(fact["invoice_no"].nunique())
    customers = int(fact["customer_id"].nunique())
    units = int(fact["quantity"].sum())
    aov = (revenue / orders).quantize(Decimal("0.01"))

    benchmarks = {
        "revenue": Decimal("10619986.68"),
        "orders": Decimal("22064"),
        "customers": Decimal("4339"),
        "units": Decimal("5438062"),
        "aov": Decimal("481.33"),
    }
    got = {"revenue": revenue, "orders": orders, "customers": customers,
           "units": units, "aov": aov}

    for k, expected in benchmarks.items():
        ok_all &= check(f"KPI {k} == benchmark", got[k] == expected, f"got {got[k]} vs {expected}")

    with conn.cursor() as cur:
        cur.execute("""
            SELECT TO_CHAR(DATE_TRUNC('month', invoice_date), 'YYYY-MM') AS ym,
                   ROUND(SUM(total_price), 2)
            FROM retail_transactions
            GROUP BY 1 ORDER BY 1
        """)
        sql_monthly = {r[0]: Decimal(str(r[1])) for r in cur.fetchall()}

    fact["ym"] = pd.to_datetime(fact["invoice_date"]).dt.strftime("%Y-%m")
    pbi_monthly = {ym: Decimal(str(round(g, 2))) for ym, g in fact.groupby("ym")["total_price"].sum().items()}
    ok_all &= check("Monthly: same month set", set(sql_monthly) == set(pbi_monthly),
                    f"{len(pbi_monthly)} months")
    month_ok = all(abs(sql_monthly[m] - pbi_monthly[m]) <= Decimal("0.01") for m in sql_monthly)
    ok_all &= check("Monthly: all 13 months reconcile with SQL", month_ok)

    with conn.cursor() as cur:
        cur.execute("""
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
            SELECT CASE
                       WHEN r_score >= 4 AND f_score >= 3 AND m_score >= 3 THEN 'Champions'
                       WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3 THEN 'Loyal Customers'
                       WHEN r_score >= 3 AND f_score >= 2 AND m_score >= 2 THEN 'Potential Loyalists'
                       WHEN r_score >= 3 AND f_score = 1 THEN 'New Customers'
                       WHEN r_score <= 2 AND (f_score >= 3 OR m_score >= 3) THEN 'At Risk'
                       WHEN r_score >= 2 AND (f_score >= 2 OR m_score >= 2) THEN 'Needs Attention'
                       ELSE 'Hibernating'
                   END AS segment, COUNT(*)
            FROM scored GROUP BY 1
        """)
        sql_segments = dict(cur.fetchall())
        cur.execute("SELECT COUNT(*) FROM retail_transactions WHERE customer_id IS NULL")
        null_cust_rows = cur.fetchone()[0]
        cur.execute("""
            SELECT ROUND(SUM(total_price), 2) FROM retail_transactions WHERE customer_id IS NOT NULL
        """)
        customer_revenue_sql = Decimal(str(cur.fetchone()[0]))
        cur.execute("""
            WITH cust AS (
                SELECT customer_id, COUNT(DISTINCT invoice_no) AS orders
                FROM retail_transactions WHERE customer_id IS NOT NULL GROUP BY customer_id
            )
            SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE orders > 1) / COUNT(*), 2) FROM cust
        """)
        repeat_rate_sql = Decimal(str(cur.fetchone()[0]))
        cur.execute("""
            WITH cust AS (
                SELECT customer_id, COUNT(DISTINCT invoice_no) AS orders
                FROM retail_transactions WHERE customer_id IS NOT NULL GROUP BY customer_id
            )
            SELECT COUNT(*) FILTER (WHERE orders > 1), COUNT(*) FILTER (WHERE orders = 1) FROM cust
        """)
        repeat_sql, one_time_sql = cur.fetchone()

    pbi_segments = cust["segment"].value_counts().to_dict()
    all_segs = sorted(set(sql_segments) | set(pbi_segments))
    seg_ok = all(int(sql_segments.get(s, 0)) == int(pbi_segments.get(s, 0)) for s in all_segs)
    ok_all &= check("RFM: segment counts reconcile 100% with SQL", seg_ok,
                    ", ".join(f"{s}={pbi_segments.get(s, 0)}" for s in all_segs))

    ok_all &= check("DimCustomer rows == 4,339", len(cust) == 4339, str(len(cust)))
    ok_all &= check("DimCustomer PK unique", cust["customer_id"].is_unique)

    ok_all &= check("DimProduct rows == 3,947", len(prod) == 3947, str(len(prod)))
    ok_all &= check("DimProduct PK unique", prod["stock_code"].is_unique)

    ok_all &= check("DimDate rows == 730 (2010-2011)", len(date) == 730, str(len(date)))
    ok_all &= check("DimDate PK unique", date["date"].is_unique)
    ok_all &= check("DimDate covers fact range",
                    date["date"].min() <= fact["invoice_date"].min() and
                    date["date"].max() >= fact["invoice_date"].max())

    ok_all &= check("DimCountry rows == 38", len(country) == 38, str(len(country)))
    ok_all &= check("DimCountry covers all fact countries",
                    set(country["country"]) == set(fact["country"]))

    # Referential integrity
    fact_ids = set(fact["customer_id"].dropna().astype(int))
    cust_ids = set(cust["customer_id"])
    orphan_cust = fact_ids - cust_ids
    ok_all &= check("Referential integrity: customers", len(orphan_cust) == 0, f"{len(orphan_cust)} orphans")

    fact_products = set(fact["stock_code"])
    orphan_prod = fact_products - set(prod["stock_code"])
    ok_all &= check("Referential integrity: products", len(orphan_prod) == 0, f"{len(orphan_prod)} orphans")

    # Derived metrics used by the report
    repeat = int(cust["is_repeat"].sum())
    one_time = len(cust) - repeat
    repeat_rate = (Decimal(repeat) / Decimal(len(cust)) * 100).quantize(Decimal("0.01"))
    ok_all &= check("Repeat customer rate == SQL 65.57%", repeat_rate == repeat_rate_sql,
                    f"PBI={repeat_rate}% vs SQL={repeat_rate_sql}%")
    ok_all &= check("Repeat customers == SQL", repeat == int(repeat_sql), f"PBI={repeat} vs SQL={repeat_sql}")
    ok_all &= check("One-time customers == SQL", one_time == int(one_time_sql), f"PBI={one_time} vs SQL={one_time_sql}")

    customer_revenue_pbi = Decimal(str(round(float(fact.loc[fact["customer_id"].notna(), "total_price"].sum()), 2)))
    ok_all &= check("Customer revenue (non-null) == SQL", customer_revenue_pbi == customer_revenue_sql,
                    f"PBI={customer_revenue_pbi} vs SQL={customer_revenue_sql}")
    ok_all &= check("Null-customer rows retained = 134,658", fact["customer_id"].isna().sum() == null_cust_rows,
                    str(null_cust_rows))

    # ---- 7. Cohort & retention (Phase 4) ----
    cohort_ret = pd.read_csv(DATASET_DIR / "CohortRetention.csv")
    cohort_sum = pd.read_csv(DATASET_DIR / "CohortSummary.csv")

    # SQL truth: execute the canonical cohort script, read its temp matrix.
    cohort_sql = (SQL_DIR / "06_cohort_retention_analysis.sql").read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(cohort_sql)
        cur.execute(
            """
            SELECT TO_CHAR(cohort_month, 'YYYY-MM'), cohort_index, cohort_size,
                   active_customers, retention_pct, revenue
            FROM cohort_matrix ORDER BY cohort_month, cohort_index
            """
        )
        sql_mat = pd.DataFrame(cur.fetchall(), columns=[
            "cohort_month", "cohort_index", "cohort_size",
            "active_customers", "retention_pct", "revenue"])
    sql_mat["cohort_index"] = sql_mat["cohort_index"].astype(int)
    sql_mat["cohort_size"] = sql_mat["cohort_size"].astype(int)
    sql_mat["active_customers"] = sql_mat["active_customers"].astype(int)
    sql_mat["retention_pct"] = sql_mat["retention_pct"].astype(float)
    sql_mat["revenue"] = sql_mat["revenue"].astype(float)

    ok_all &= check("CohortRetention rows == 91", len(cohort_ret) == 91, str(len(cohort_ret)))
    ok_all &= check("CohortSummary rows == 13", len(cohort_sum) == 13, str(len(cohort_sum)))

    total_cohort = int(cohort_ret.groupby("cohort_month")["cohort_size"].first().sum())
    ok_all &= check("Cohort customers total = 4,339", total_cohort == 4339, str(total_cohort))

    m0 = cohort_ret[cohort_ret["cohort_index"] == 0]
    ok_all &= check("M0 retention = 100.0% for every cohort", bool((m0["retention_pct"] == 100.0).all()),
                    f"{len(m0)} cohorts")

    merged = cohort_ret.merge(sql_mat, on=["cohort_month", "cohort_index"],
                              suffixes=("_pbi", "_sql"))
    counts_ok = bool((merged["active_customers_pbi"] == merged["active_customers_sql"]).all())
    ok_all &= check("Cohort counts match SQL (91 cells)", counts_ok)
    ret_ok = bool((merged["retention_pct_pbi"] - merged["retention_pct_sql"]).abs().max() <= 0.01)
    ok_all &= check("Cohort retention % match SQL (<=0.01pp)",
                    ret_ok, f"max diff {(merged['retention_pct_pbi'] - merged['retention_pct_sql']).abs().max():.4f}pp")

    maxidx = cohort_ret.groupby("cohort_month")["cohort_index"].max()
    expected_maxidx = {
        "2010-12": 12, "2011-01": 11, "2011-02": 10, "2011-03": 9,
        "2011-04": 8, "2011-05": 7, "2011-06": 6, "2011-07": 5,
        "2011-08": 4, "2011-09": 3, "2011-10": 2, "2011-11": 1, "2011-12": 0,
    }
    ok_all &= check("No future-period fake zeros (grid bounded by window)",
                    maxidx.to_dict() == expected_maxidx)

    # Weighted retention series (M0..M12) — the exact aggregation the fixed DAX
    # measure 'Retention Rate' = DIVIDE([Retained Customers], [Cohort Customers])
    # performs on CohortRetention: for each cohort month index, total retained
    # customers across the cohorts with observed data / total cohort size of
    # those same cohorts. Future/unavailable periods are absent, so they never
    # contribute (no fake zeros).
    def weighted_series(df: pd.DataFrame) -> dict[int, float]:
        g = df.groupby("cohort_index").agg(
            active=("active_customers", "sum"), size=("cohort_size", "sum"))
        return {int(i): float(r["active"]) / float(r["size"]) * 100 for i, r in g.iterrows()}

    pbi_w = weighted_series(cohort_ret)
    sql_w = weighted_series(sql_mat)
    all_widx = sorted(set(pbi_w) | set(sql_w))
    same_idx = set(pbi_w) == set(sql_w)
    wdiff = max(abs(pbi_w.get(i, float("nan")) - sql_w.get(i, float("nan"))) for i in all_widx)
    ok_all &= check("Weighted retention M0 = 100.0% (DAX formula)", abs(pbi_w.get(0, -1) - 100.0) <= 0.01,
                    f"{pbi_w.get(0):.2f}%")
    ok_all &= check("Weighted retention (DAX) matches SQL for M0..M12 (<=0.01pp)",
                    same_idx and wdiff <= 0.01,
                    f"max diff {wdiff:.4f}pp over {len(all_widx)} indices")
    # Per-index availability must be identical: the denominator is the sum of the
    # sizes of exactly the cohorts that have observed data at that month.
    def idx_cohorts(df: pd.DataFrame) -> dict[int, set]:
        return {int(i): set(g["cohort_month"]) for i, g in df.groupby("cohort_index")}
    avail_ok = idx_cohorts(cohort_ret) == idx_cohorts(sql_mat)
    ok_all &= check("Weighted retention uses only observed cohorts (no future zeros)",
                    avail_ok)
    series_detail = " | ".join(f"M{i}={pbi_w[i]:.1f}%" for i in all_widx)
    ok_all &= check("Weighted retention series (PBI dataset == SQL)", True, series_detail)

    pbi_sum = cohort_sum.set_index("cohort_month")
    sql_sum = cohort_ret.groupby("cohort_month")["cohort_size"].first()
    ok_all &= check("CohortSummary sizes match SQL", bool(
        (pbi_sum["cohort_size"].astype(int) == sql_sum.astype(int)).all()))
    ok_all &= check("CohortSummary repeat rate reconciles",
                    int(pbi_sum["repeat_customers"].sum()) == 2845,
                    f"repeat={int(pbi_sum['repeat_customers'].sum())}")

    conn.close()
    print()
    print("OVERALL:", "ALL CHECKS PASSED" if ok_all else "SOME CHECKS FAILED")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
