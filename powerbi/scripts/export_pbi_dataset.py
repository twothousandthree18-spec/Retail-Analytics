"""
export_pbi_dataset.py — Build the Power BI-ready star-schema dataset from the
validated PostgreSQL source (`retail_transactions`).

This is NOT a second cleaning pipeline. The fact table is a direct projection of
the validated PostgreSQL table, and the customer dimension reuses the exact RFM
methodology already validated in `sql/05_advanced_analytics.sql` (including the
`customer_id` tie-breaker that produces 100% agreement with the workbook).

Output (powerbi/dataset/):
    FactSales.csv       527,390 rows  one row per transaction line item
    DimDate.csv            730 rows   daily calendar 2010-01-01 .. 2011-12-31
    DimCustomer.csv      4,339 rows   customer + validated RFM scores/segment
    DimProduct.csv       3,947 rows   product attributes + category
    DimCountry.csv          38 rows   country + region grouping
    CohortRetention.csv     91 rows   cohort retention matrix (long form,
                                      Phase 4) - same logic as
                                      sql/06_cohort_retention_analysis.sql
    CohortSummary.csv       13 rows   per-cohort acquisition + lifetime metrics

Run:
    DATABASE_URL=postgresql://... python powerbi/scripts/export_pbi_dataset.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "powerbi" / "dataset"

load_dotenv(REPO_ROOT / ".env")

COUNTRY_REGION = {
    "United Kingdom": "UK & Ireland",
    "Eire": "UK & Ireland",
    "Channel Islands": "UK & Ireland",
    "Netherlands": "Europe",
    "Germany": "Europe",
    "France": "Europe",
    "Spain": "Europe",
    "Switzerland": "Europe",
    "Belgium": "Europe",
    "Sweden": "Europe",
    "Norway": "Europe",
    "Portugal": "Europe",
    "Finland": "Europe",
    "Denmark": "Europe",
    "Italy": "Europe",
    "Cyprus": "Europe",
    "Austria": "Europe",
    "Poland": "Europe",
    "Greece": "Europe",
    "Iceland": "Europe",
    "Malta": "Europe",
    "Lithuania": "Europe",
    "Czech Republic": "Europe",
    "European Community": "Europe",
    "Australia": "Asia Pacific",
    "Japan": "Asia Pacific",
    "Singapore": "Asia Pacific",
    "Hong Kong": "Asia Pacific",
    "Israel": "Middle East & Africa",
    "United Arab Emirates": "Middle East & Africa",
    "Lebanon": "Middle East & Africa",
    "Bahrain": "Middle East & Africa",
    "Saudi Arabia": "Middle East & Africa",
    "Rsa": "Middle East & Africa",
    "Canada": "Americas",
    "Usa": "Americas",
    "Brazil": "Americas",
    "Unspecified": "Unspecified",
}


def connect() -> psycopg2.extensions.connection:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("ERROR: DATABASE_URL is not set (see .env.example).")
    return psycopg2.connect(url, connect_timeout=15)


def export_fact_sales(conn) -> pd.DataFrame:
    print("[1/5] FactSales ...", flush=True)
    df = pd.read_sql(
        """
        SELECT transaction_id,
               invoice_no,
               stock_code,
               customer_id,
               country,
               invoice_date,
               quantity,
               unit_price::float8 AS unit_price,
               total_price::float8 AS total_price
        FROM retail_transactions
        ORDER BY transaction_id
        """,
        conn,
    )
    df["invoice_no"] = df["invoice_no"].astype(str)
    df["stock_code"] = df["stock_code"].astype(str)
    return df


def export_dim_date(conn) -> pd.DataFrame:
    print("[2/5] DimDate ...", flush=True)
    rng = pd.date_range("2010-01-01", "2011-12-31", freq="D")
    d = pd.DataFrame({"date": rng})
    d["year"] = d["date"].dt.year
    d["quarter"] = d["date"].dt.quarter
    d["quarter_label"] = "Q" + d["quarter"].astype(str)
    d["month_number"] = d["date"].dt.month
    d["month_name"] = d["date"].dt.strftime("%B")
    d["year_month"] = d["date"].dt.strftime("%Y-%m")
    d["year_month_name"] = d["date"].dt.strftime("%b %Y")
    d["week_of_year"] = d["date"].dt.isocalendar().week
    d["day"] = d["date"].dt.day
    d["day_of_week_number"] = d["date"].dt.dayofweek + 1
    d["day_of_week_name"] = d["date"].dt.strftime("%A")
    d["is_weekend"] = d["date"].dt.dayofweek >= 5
    d["date"] = d["date"].dt.strftime("%Y-%m-%d")
    return d


def export_dim_customer(conn) -> pd.DataFrame:
    print("[3/5] DimCustomer (validated RFM) ...", flush=True)
    df = pd.read_sql(
        """
        WITH base AS (
            SELECT customer_id, invoice_no, invoice_date, total_price
            FROM retail_transactions
            WHERE customer_id IS NOT NULL
        ),
        reference AS (SELECT MAX(invoice_date) AS snapshot FROM base),
        rfm AS (
            SELECT b.customer_id,
                   MIN(b.invoice_date)::date AS first_order_date,
                   MAX(b.invoice_date)::date AS last_order_date,
                   (SELECT snapshot FROM reference)::date - MAX(b.invoice_date)::date AS recency_days,
                   COUNT(DISTINCT b.invoice_no) AS frequency,
                   ROUND(SUM(b.total_price), 2) AS monetary
            FROM base b
            GROUP BY b.customer_id
        ),
        scored AS (
            SELECT customer_id, first_order_date, last_order_date, recency_days, frequency, monetary,
                   5 - NTILE(4) OVER (ORDER BY recency_days ASC, customer_id ASC) AS r_score,
                   NTILE(4)      OVER (ORDER BY frequency ASC,   customer_id ASC) AS f_score,
                   NTILE(4)      OVER (ORDER BY monetary ASC,    customer_id ASC) AS m_score
            FROM rfm
        )
        SELECT customer_id,
               first_order_date,
               last_order_date,
               recency_days,
               frequency,
               monetary::float8 AS monetary,
               r_score,
               f_score,
               m_score,
               r_score + f_score + m_score AS rfm_score,
               (last_order_date - first_order_date) AS customer_lifetime_days,
               CASE WHEN frequency > 1 THEN 1 ELSE 0 END AS is_repeat,
               TO_CHAR(first_order_date, 'YYYY-MM') AS first_purchase_year_month,
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
        ORDER BY customer_id
        """,
        conn,
    )
    return df


def export_dim_product(conn) -> pd.DataFrame:
    print("[4/5] DimProduct ...", flush=True)
    df = pd.read_sql(
        """
        SELECT stock_code,
               MAX(description) AS description,
               NULLIF(UPPER(SPLIT_PART(MAX(description), ' ', 1)), '') AS category
        FROM retail_transactions
        GROUP BY stock_code
        ORDER BY stock_code
        """,
        conn,
    )
    df["stock_code"] = df["stock_code"].astype(str)
    return df


def export_dim_country(conn) -> pd.DataFrame:
    print("[5/5] DimCountry ...", flush=True)
    rows = pd.read_sql(
        "SELECT DISTINCT country FROM retail_transactions ORDER BY country", conn
    )
    countries = rows["country"].tolist()
    unknown = [c for c in countries if c not in COUNTRY_REGION]
    if unknown:
        print(f"WARNING: countries without region mapping: {unknown}")
    df = pd.DataFrame(
        {"country": countries, "region": [COUNTRY_REGION.get(c, "Unspecified") for c in countries]}
    )
    return df


COHORT_WINDOW_END = "2011-12-01"


def export_cohort_retention(conn) -> pd.DataFrame:
    """Cohort retention matrix (long form) — mirrors sql/06 (Phase 4).

    One row per (cohort_month, cohort_index) inside the observation window.
    Months beyond the window are not emitted, so Power BI renders them blank,
    not as a false 0%. retention_pct = customers active in month N / cohort size.
    """
    print("[6/7] CohortRetention ...", flush=True)
    return pd.read_sql(
        f"""
        WITH cohorts AS (
            SELECT customer_id,
                   DATE_TRUNC('month', MIN(invoice_date))::date AS cohort_month
            FROM retail_transactions
            WHERE customer_id IS NOT NULL
            GROUP BY customer_id
        ),
        sizes AS (
            SELECT cohort_month, COUNT(*) AS size FROM cohorts GROUP BY cohort_month
        ),
        avail AS (
            SELECT s.cohort_month,
                   s.size,
                   x.cohort_index
            FROM sizes s,
                 LATERAL (
                     SELECT generate_series(
                                0,
                                (EXTRACT(YEAR FROM DATE '{COHORT_WINDOW_END}') * 12
                                   + EXTRACT(MONTH FROM DATE '{COHORT_WINDOW_END}'))
                              - (EXTRACT(YEAR FROM s.cohort_month) * 12
                                   + EXTRACT(MONTH FROM s.cohort_month))
                     )::int AS cohort_index
                 ) x
        ),
        activity AS (
            SELECT t.customer_id,
                   c.cohort_month,
                   ((EXTRACT(YEAR FROM DATE_TRUNC('month', t.invoice_date)) * 12
                       + EXTRACT(MONTH FROM DATE_TRUNC('month', t.invoice_date)))
                    - (EXTRACT(YEAR FROM c.cohort_month) * 12
                       + EXTRACT(MONTH FROM c.cohort_month)))::int AS cohort_index,
                   t.total_price
            FROM retail_transactions t
            JOIN cohorts c USING (customer_id)
        ),
        counts AS (
            SELECT cohort_month,
                   cohort_index,
                   COUNT(DISTINCT customer_id) AS active_customers,
                   ROUND(SUM(total_price), 2)  AS revenue
            FROM activity
            GROUP BY cohort_month, cohort_index
        )
        SELECT TO_CHAR(a.cohort_month, 'YYYY-MM')    AS cohort_month,
               a.cohort_index,
               a.size                                AS cohort_size,
               COALESCE(c.active_customers, 0)       AS active_customers,
               ROUND(100.0 * COALESCE(c.active_customers, 0) / a.size, 2)
                                                      AS retention_pct,
               COALESCE(c.revenue, 0)                AS revenue
        FROM avail a
        LEFT JOIN counts c USING (cohort_month, cohort_index)
        ORDER BY a.cohort_month, a.cohort_index
        """,
        conn,
    )


def export_cohort_summary(conn) -> pd.DataFrame:
    """Per-cohort acquisition + lifetime metrics (Phase 4)."""
    print("[7/7] CohortSummary ...", flush=True)
    return pd.read_sql(
        """
        WITH cohorts AS (
            SELECT customer_id,
                   DATE_TRUNC('month', MIN(invoice_date))::date AS cohort_month
            FROM retail_transactions
            WHERE customer_id IS NOT NULL
            GROUP BY customer_id
        ),
        base AS (
            SELECT customer_id,
                   cohort_month,
                   COUNT(DISTINCT invoice_no) AS orders,
                   SUM(total_price)           AS revenue,
                   COUNT(DISTINCT DATE_TRUNC('month', invoice_date)) AS active_months,
                   MIN(invoice_date)::date    AS first_purchase_date,
                   MAX(invoice_date)::date    AS last_purchase_date
            FROM retail_transactions
            JOIN cohorts USING (customer_id)
            GROUP BY customer_id, cohort_month
        )
        SELECT TO_CHAR(cohort_month, 'YYYY-MM')            AS cohort_month,
               COUNT(*)                                    AS cohort_size,
               COUNT(*) FILTER (WHERE orders > 1)          AS repeat_customers,
               COUNT(*) FILTER (WHERE orders = 1)          AS one_time_customers,
               ROUND(100.0 * COUNT(*) FILTER (WHERE orders > 1) / COUNT(*), 2)
                                                           AS repeat_rate_pct,
               ROUND(SUM(revenue), 2)                      AS lifetime_revenue,
               ROUND(AVG(revenue), 2)                      AS revenue_per_customer,
               ROUND(AVG(orders), 2)                       AS avg_orders_per_customer,
               ROUND(AVG(active_months), 2)                AS avg_active_months,
               ROUND(AVG(last_purchase_date - first_purchase_date), 1)
                                                           AS avg_lifetime_days
        FROM base
        GROUP BY cohort_month
        ORDER BY cohort_month
        """,
        conn,
    )


def write(df: pd.DataFrame, name: str) -> None:
    path = DATASET_DIR / name
    df.to_csv(path, index=False)
    print(f"  wrote {path} ({len(df):,} rows)")


def main() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        write(export_fact_sales(conn), "FactSales.csv")
        write(export_dim_date(conn), "DimDate.csv")
        write(export_dim_customer(conn), "DimCustomer.csv")
        write(export_dim_product(conn), "DimProduct.csv")
        write(export_dim_country(conn), "DimCountry.csv")
        write(export_cohort_retention(conn), "CohortRetention.csv")
        write(export_cohort_summary(conn), "CohortSummary.csv")
    finally:
        conn.close()
    print("\nPower BI dataset written to powerbi/dataset/")


if __name__ == "__main__":
    main()
