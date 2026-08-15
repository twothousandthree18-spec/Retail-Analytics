"""
load_data.py — Load the cleaned retail dataset into PostgreSQL.

This is the loading step of the SQL analytics layer. It reads the cleaned
analytical dataset exported by the notebook (``data/cleaned_retail_data.csv``),
reconstructs a proper ``invoice_date`` timestamp, and bulk-loads it into the
``retail_transactions`` table defined in ``schema.sql``.

Usage
-----
    # from the project root, after creating the database:
    DATABASE_URL=postgresql://postgres:PASSWORD@localhost:5432/retail_analysis \\
        python sql/load_data.py

    # explicit flags (overrides DATABASE_URL)
    python sql/load_data.py --db-url postgresql://... --csv data/cleaned_retail_data.csv

Options
-------
    --db-url     PostgreSQL connection string (overrides the DATABASE_URL env var).
    --csv        Path to the cleaned dataset (default: <repo>/data/cleaned_retail_data.csv).
    --schema     Path to schema.sql (default: alongside this script).
    --truncate   Empty the table before loading (used on repeat runs).
    --append     Load into a non-empty table without truncating (use with care).

Never hard-code credentials: the connection string always comes from
DATABASE_URL (optionally loaded from a local ``.env`` file) or --db-url.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time

import psycopg2
import pandas as pd
from dotenv import load_dotenv

# Repo root = parent of the sql/ folder this script lives in.
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DEFAULT_CSV = os.path.join(REPO_ROOT, "data", "cleaned_retail_data.csv")
DEFAULT_SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")
DEFAULT_ENV = os.path.join(REPO_ROOT, ".env")

# Columns the CSV must contain (the notebook's cleaned dataframe).
REQUIRED_COLUMNS = [
    "InvoiceNo", "StockCode", "Description", "Quantity", "UnitPrice",
    "CustomerID", "Country", "TotalPrice", "Invoice Date", "Invoice Time",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-url", help="PostgreSQL connection string (overrides DATABASE_URL).")
    parser.add_argument("--csv", default=DEFAULT_CSV, help=f"Cleaned dataset CSV (default: {DEFAULT_CSV}).")
    parser.add_argument("--schema", default=DEFAULT_SCHEMA, help=f"schema.sql to execute (default: {DEFAULT_SCHEMA}).")
    parser.add_argument("--truncate", action="store_true", help="Truncate the table before loading.")
    parser.add_argument("--append", action="store_true", help="Allow loading into a non-empty table.")
    return parser.parse_args()


def get_connection_string(args: argparse.Namespace) -> str:
    load_dotenv(DEFAULT_ENV)  # optional: loads DATABASE_URL from repo root .env
    url = args.db_url or os.environ.get("DATABASE_URL")
    if not url:
        sys.exit(
            "ERROR: No database connection string provided.\n"
            "  Set the DATABASE_URL environment variable (see .env.example) or pass --db-url.\n"
            "  Example: DATABASE_URL=postgresql://postgres:secret@localhost:5432/retail_analysis"
        )
    return url


def load_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        sys.exit(f"ERROR: cleaned dataset not found: {path}\n"
                 "  Run the notebook 'OnlineRetail cleaning.ipynb' first - it exports "
                 "data/cleaned_retail_data.csv as part of the pipeline.")
    df = pd.read_csv(path, dtype={"InvoiceNo": str, "StockCode": str}, low_memory=False)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        sys.exit(f"ERROR: CSV is missing expected columns: {missing}")
    return df


def prepare_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Build a DataFrame ready for COPY with PostgreSQL-typed text values."""
    parsed = pd.to_datetime(
        df["Invoice Date"].astype(str) + " " + df["Invoice Time"].astype(str),
        format="%y/%m/%d %H:%M:%S",
        errors="coerce",
    )
    if parsed.isna().any():
        sys.exit(f"ERROR: {int(parsed.isna().sum())} rows have unparsable "
                 "'Invoice Date'/'Invoice Time' — aborting.")

    customer_id = df["CustomerID"].copy()
    customer_id = customer_id.astype("Int64")  # nullable int; NaN stays NA -> NULL

    out = pd.DataFrame({
        "invoice_no": df["InvoiceNo"].astype(str).str.strip(),
        "stock_code": df["StockCode"].astype(str).str.strip(),
        "description": df["Description"].astype("object").where(
            df["Description"].notna(), None),
        "quantity": df["Quantity"].astype("int64"),
        "invoice_date": parsed.dt.strftime("%Y-%m-%d %H:%M:%S"),
        "unit_price": df["UnitPrice"].map(lambda v: f"{v:.2f}"),
        "customer_id": customer_id,
        "country": df["Country"].astype(str).str.strip(),
        "total_price": df["TotalPrice"].map(lambda v: f"{v:.2f}"),
    })
    return out


def table_row_count(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM "{table}"')
        return cur.fetchone()[0]


def main() -> None:
    args = parse_args()
    url = get_connection_string(args)

    print(f"[1/4] Reading cleaned dataset: {args.csv}")
    df = load_csv(args.csv)
    expected_rows = len(df)
    print(f"      Rows in CSV: {expected_rows:,} | Columns: {len(df.columns)}")
    print(f"      Null CustomerID rows (kept): {int(df['CustomerID'].isna().sum()):,}")
    print(f"      Cancellation rows present (should be 0): "
          f"{int(df['InvoiceNo'].astype(str).str.startswith('C').sum())}")

    print("[2/4] Connecting to PostgreSQL ...")
    try:
        conn = psycopg2.connect(url, connect_timeout=15)
    except psycopg2.OperationalError as exc:
        sys.exit(
            f"ERROR: could not connect to PostgreSQL: {exc}\n"
            "  Is the server running? Does the database exist? (hint: create it with\n"
            '  `createdb retail_analysis` or `CREATE DATABASE retail_analysis;`)'
        )
    conn.autocommit = False
    print("      Connected.")

    print(f"[3/4] Ensuring schema ({args.schema}) ...")
    with open(args.schema, "r", encoding="utf-8") as fh:
        ddl = fh.read()
    with conn.cursor() as cur:
        cur.execute(ddl)
    conn.commit()

    existing = table_row_count(conn, "retail_transactions")
    if existing > 0 and not (args.truncate or args.append):
        sys.exit(
            f"ERROR: retail_transactions already contains {existing:,} rows.\n"
            "  Refusing to load to avoid accidental duplication. Re-run with --truncate "
            "to replace the data, or --append to add rows."
        )
    if args.truncate and existing > 0:
        print(f"      Truncating {existing:,} existing rows ...")
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE retail_transactions")
        conn.commit()

    print("[4/4] Loading rows via COPY ...")
    out = prepare_frame(df)
    buf = io.StringIO()
    out.to_csv(buf, index=False, header=False, na_rep="",
               quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    buf.seek(0)

    t0 = time.time()
    copy_sql = (
        "COPY retail_transactions "
        "(invoice_no, stock_code, description, quantity, invoice_date, "
        " unit_price, customer_id, country, total_price) "
        "FROM STDIN WITH (FORMAT csv, NULL '', HEADER false)"
    )
    try:
        with conn.cursor() as cur:
            cur.copy_expert(copy_sql, buf)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    elapsed = time.time() - t0

    loaded = table_row_count(conn, "retail_transactions")
    print(f"      Loaded {loaded:,} rows in {elapsed:.1f}s.")

    if loaded != expected_rows:
        conn.close()
        sys.exit(f"ERROR: row-count mismatch — expected {expected_rows:,}, found {loaded:,}. "
                 "Nothing was committed.")
    conn.close()

    print(f"OK: {loaded:,} rows verified in 'retail_transactions' (matches CSV exactly).")


if __name__ == "__main__":
    main()
