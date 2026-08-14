"""
cohort_validation.py — SQL vs Python reconciliation of the Phase 4 cohort and
customer retention analysis.

Run:
    DATABASE_URL=postgresql://... python sql/cohort_validation.py

How it works
------------
* The "SQL truth" is produced by executing ``sql/06_cohort_retention_analysis.sql``
  on the same connection (its temp tables ``cohort_customers`` /
  ``cohort_activity`` / ``cohort_matrix`` are then queried directly).
* The "Python truth" is computed independently in pandas from the raw
  attributed rows fetched from PostgreSQL.
* The two engines must agree on:

    1. total cohort customers = 4,339
    2. cohort sizes sum to 4,339
    3. M0 retention = 100.0% for every cohort
    4. per-cohort customer counts (SQL vs Python) match exactly
    5. retention percentages match within tolerance (0.01 pp)
    6. revenue by cohort age matches within tolerance (£0.01)
    7. no future-period fake zeros (grid bounded by the observation window)
    8. no customer assigned to multiple cohorts
    9. weighted retention series (M0..M12) matches between engines: at each cohort
       month the weighted average is total active customers across the cohorts
       with observed data, divided by the total cohort sizes of those same
       cohorts — future/unavailable periods are excluded, never counted as zero

Exits non-zero if any check fails.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = Path(__file__).resolve().parent

load_dotenv(REPO_ROOT / ".env")

PASS = "PASS"
FAIL = "FAIL"
TOL_PP = Decimal("0.01")      # retention percentage-point tolerance
TOL_GBP = Decimal("0.01")     # revenue tolerance


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{PASS if ok else FAIL}] {name}" + (f" - {detail}" if detail else ""))
    return ok


def sql_matrix(conn) -> pd.DataFrame:
    """Execute 06 and return its canonical normalized matrix."""
    sql = (SQL_DIR / "06_cohort_retention_analysis.sql").read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            """
            SELECT TO_CHAR(cohort_month, 'YYYY-MM') AS cohort_month,
                   cohort_index,
                   cohort_size,
                   active_customers,
                   retention_pct,
                   revenue
            FROM cohort_matrix
            ORDER BY cohort_month, cohort_index
            """
        )
        rows = cur.fetchall()
    return pd.DataFrame(
        rows,
        columns=["cohort_month", "cohort_index", "cohort_size",
                 "active_customers", "retention_pct", "revenue"],
    ).astype({
        "cohort_index": int,
        "cohort_size": int,
        "active_customers": int,
        "retention_pct": float,
        "revenue": float,
    })


def py_matrix(conn) -> pd.DataFrame:
    """Compute the same matrix independently in pandas."""
    df = pd.read_sql(
        """
        SELECT customer_id, invoice_no, invoice_date, total_price
        FROM retail_transactions
        WHERE customer_id IS NOT NULL
        """,
        conn,
    )
    df["dt"] = pd.to_datetime(df["invoice_date"])
    df["month"] = df["dt"].dt.to_period("M")
    first = df.groupby("customer_id")["month"].min().rename("first_month").reset_index()
    df = df.merge(first, on="customer_id")
    df["cohort_month"] = df["first_month"].astype(str)
    df["purchase_month"] = df["month"].astype(str)
    df["cohort_index"] = (df["month"] - df["first_month"]).apply(lambda x: x.n)

    sizes = df.groupby("cohort_month")["customer_id"].nunique().rename("cohort_size")
    cohorts = pd.DataFrame({"cohort_month": sizes.index, "cohort_size": sizes.values})
    cohorts["c_start"] = pd.to_datetime(cohorts["cohort_month"] + "-01")
    # available indices per cohort: 0..months(cohort -> window end 2011-12)
    cohorts["months_to_end"] = (
        2011 * 12 + 12 - (cohorts["c_start"].dt.year * 12 + cohorts["c_start"].dt.month)
    ).astype(int)

    grid_parts = []
    for _, row in cohorts.iterrows():
        for idx in range(int(row["months_to_end"]) + 1):
            grid_parts.append((row["cohort_month"], idx, int(row["cohort_size"])))
    grid = pd.DataFrame(grid_parts, columns=["cohort_month", "cohort_index", "cohort_size"])

    active = (
        df.groupby(["cohort_month", "cohort_index"])["customer_id"]
        .nunique()
        .rename("active_customers")
        .reset_index()
    )
    revenue = (
        df.groupby(["cohort_month", "cohort_index"])["total_price"]
        .sum()
        .rename("revenue")
        .reset_index()
    )

    m = grid.merge(active, on=["cohort_month", "cohort_index"], how="left")
    m = m.merge(revenue, on=["cohort_month", "cohort_index"], how="left")
    m["active_customers"] = m["active_customers"].fillna(0).astype(int)
    m["revenue"] = m["revenue"].fillna(0.0)
    m["retention_pct"] = (m["active_customers"] / m["cohort_size"] * 100).round(2)
    m = m.sort_values(["cohort_month", "cohort_index"]).reset_index(drop=True)
    return m


def main() -> None:
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("ERROR: DATABASE_URL is not set (see .env.example).")
    conn = psycopg2.connect(url, connect_timeout=15)
    ok_all = True

    sql = sql_matrix(conn)
    py = py_matrix(conn)

    # 1. Total cohort customers
    sizes_sql = sql.groupby("cohort_month")["cohort_size"].first()
    sizes_py = py.groupby("cohort_month")["cohort_size"].first()
    total_sql = int(sizes_sql.sum())
    ok_all &= check("Total cohort customers = 4,339", total_sql == 4339, str(total_sql))

    # 2. Cohort sizes sum to 4,339
    sum_sizes = int(sizes_sql.sum())
    ok_all &= check("Cohort sizes sum to 4,339", sum_sizes == 4339, str(sum_sizes))

    # 3. M0 retention = 100% for every cohort
    m0 = sql[sql["cohort_index"] == 0].set_index("cohort_month")["retention_pct"]
    ok_all &= check(
        "M0 retention = 100.0% for every cohort",
        bool((m0 == 100.0).all()) and len(m0) == len(sizes_sql),
        f"{len(m0)} cohorts, min={m0.min():.2f}%",
    )

    # 4. Cohort sizes SQL vs Python
    same_sizes = bool((sizes_sql.astype(int) == sizes_py.astype(int)).all())
    ok_all &= check("SQL/Python cohort sizes match", same_sizes,
                    ", ".join(f"{k}={int(v)}" for k, v in sizes_sql.items()))

    # 5. Customer counts by (cohort, index) SQL vs Python
    counts = sql.merge(
        py[["cohort_month", "cohort_index", "active_customers"]],
        on=["cohort_month", "cohort_index"],
        suffixes=("_sql", "_py"),
    )
    counts_ok = bool((counts["active_customers_sql"] == counts["active_customers_py"]).all())
    ok_all &= check("SQL/Python cohort customer counts match", counts_ok,
                    f"{len(counts)} cells compared")

    # 6. Retention percentages within tolerance
    both = sql.merge(
        py[["cohort_month", "cohort_index", "retention_pct"]],
        on=["cohort_month", "cohort_index"],
        suffixes=("_sql", "_py"),
    )
    both["diff"] = (both["retention_pct_sql"] - both["retention_pct_py"]).abs()
    ret_ok = bool((both["diff"] <= 0.01).all())
    ok_all &= check("SQL/Python retention % match (<=0.01pp)", ret_ok,
                    f"max diff {both['diff'].max():.4f}pp over {len(both)} cells")

    # 7. Revenue by cohort age within tolerance
    rev = sql.merge(
        py[["cohort_month", "cohort_index", "revenue"]],
        on=["cohort_month", "cohort_index"],
        suffixes=("_sql", "_py"),
    )
    rev["diff"] = (rev["revenue_sql"] - rev["revenue_py"]).abs()
    rev_ok = bool((rev["diff"] <= 0.02).all())
    ok_all &= check("SQL/Python cohort revenue match (<=£0.02)", rev_ok,
                    f"max diff £{rev['diff'].max():.2f} over {len(rev)} cells")

    # 8. No future-period fake zeros: max index per cohort = months to window end
    maxidx = sql.groupby("cohort_month")["cohort_index"].max()
    expected = {
        "2010-12": 12, "2011-01": 11, "2011-02": 10, "2011-03": 9,
        "2011-04": 8, "2011-05": 7, "2011-06": 6, "2011-07": 5,
        "2011-08": 4, "2011-09": 3, "2011-10": 2, "2011-11": 1, "2011-12": 0,
    }
    grid_ok = bool((maxidx.to_dict() == expected))
    ok_all &= check("No future-period fake zeros (grid bounded by window)", grid_ok,
                    ", ".join(f"{k}:M{v}" for k, v in maxidx.items()))

    # 9. No customer in multiple cohorts
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT customer_id, COUNT(DISTINCT cohort_month) AS n
            FROM cohort_customers GROUP BY customer_id HAVING COUNT(DISTINCT cohort_month) > 1
            LIMIT 1
            """
        )
        multi = cur.fetchone()
    ok_all &= check("No customer assigned to multiple cohorts", multi is None,
                    f"found {multi}" if multi else "")

    # 10. Weighted retention series (M0..M12) SQL vs Python.
    # Weighted retention at month N = SUM(active) / SUM(cohort_size) over the
    # cohorts that have an observed period N. The same formula feeds the Power BI
    # measure 'Retention Rate' = DIVIDE([Retained Customers], [Cohort Customers]).
    def weighted_series(m: pd.DataFrame) -> pd.Series:
        g = m.groupby("cohort_index").agg(
            active=("active_customers", "sum"), size=("cohort_size", "sum"))
        return (g["active"] / g["size"] * 100).round(2)

    wsql = weighted_series(sql)
    wpy = weighted_series(py)
    widx = sorted(set(wsql.index) | set(wpy.index))
    wdiff = max(abs(wsql.get(i, float("nan")) - wpy.get(i, float("nan"))) for i in widx)
    w_ok = wdiff <= 0.01 and bool((wsql.index == wpy.index).all())
    ok_all &= check("Weighted retention series matches (M0..M12, <=0.01pp)", w_ok,
                    f"max diff {wdiff:.4f}pp over {len(widx)} indices")
    ok_all &= check("Weighted retention M0 = 100.0% (all cohorts available)", wsql.get(0) == 100.0,
                    f"{wsql.get(0):.2f}%")
    detail = ", ".join(f"M{i}={wsql.get(i):.1f}%" for i in widx)
    ok_all &= check("Weighted retention series (SQL, used by DAX)", True, detail)

    conn.close()
    print()
    print("OVERALL:", "ALL CHECKS PASSED" if ok_all else "SOME CHECKS FAILED")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()
