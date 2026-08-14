# PostgreSQL + Advanced SQL Analytics Layer

A professional SQL analytics layer on top of the cleaned retail dataset, built to
complement (and independently validate) the Python/Pandas pipeline that produces
`Retail_Analysis_Report.xlsx`.

- **Source data:** `data/cleaned_retail_data.csv` (527,390 rows, 13 columns) —
  the exact same cleaned dataset exported by the notebook
  (`OnlineRetail cleaning.ipynb`, last cell).
- **Database table:** `retail_transactions` — one row per transaction line item.
- **Language:** PostgreSQL (uses CTEs, window functions, date/time intelligence).

## Why a SQL layer?

1. Reproduces and **validates** the Excel/pandas KPIs from a second, independent
   engine (PostgreSQL vs Python).
2. Reproduces the workbook's **RFM Customer Segmentation** in pure SQL and proves
   the two engines agree (see *RFM reproduction* below).
3. Provides interview-grade, business-focused SQL answers to concrete retail
   questions.
4. Keeps SQL files **portable** (pure SQL, no client-specific meta-commands) so
   they run in `psql`, DBeaver, or any PostgreSQL client.

## Project structure

```
sql/
├── schema.sql                   # DDL: table + indexes + comments
├── load_data.py                 # Loads the CSV into PostgreSQL (COPY, safe)
├── requirements.txt             # Python dependencies for the SQL tooling
├── 01_sales_analysis.sql        # Sales & revenue KPIs
├── 02_customer_analysis.sql     # Customer behaviour & cohorts
├── 03_product_analysis.sql      # Product & basket analysis
├── 04_time_analysis.sql         # Time intelligence (MoM, YoY, weekday, hourly)
├── 05_advanced_analytics.sql    # RFM in SQL + window/advanced techniques
├── 06_cohort_retention_analysis.sql  # Phase 4: cohort & customer retention
├── cohort_validation.py         # SQL vs pandas reconcile of the cohort tables
├── generate_insights_report.py  # Machine-generates insights_report.md
├── insights_report.md           # Generated business insights (checked in)
└── verify_pipeline.py           # Automated end-to-end verification
```

## Setup

1. Have a running PostgreSQL server (any recent version, 13+ is fine).
2. Create the database and (optionally) a dedicated user:

   ```sql
   CREATE DATABASE retail_analysis;
   ```

3. Configure the connection string. Copy `.env.example` to `.env` at the repo
   root and fill in the values:

   ```dotenv
   DATABASE_URL=postgresql://postgres:CHANGE_ME@localhost:5432/retail_analysis
   ```

   Credentials are read from the environment (`DATABASE_URL` variable or `.env`).
   **No credentials are hard-coded or committed.**

4. Install the Python dependencies (a virtual environment is recommended):

   ```bash
   pip install -r sql/requirements.txt
   ```

## Loading the data

```bash
# Generate the CSV from the notebook first (the notebook's last cell writes it):
#   jupyter nbconvert --to notebook --execute "OnlineRetail cleaning.ipynb"

python sql/load_data.py                      # load fresh table
python sql/load_data.py --truncate           # reload, clearing existing rows
python sql/load_data.py --append             # append without deleting
```

`load_data.py`:
- creates the schema (idempotent) if it does not exist,
- refuses to load into a non-empty table unless `--truncate`/`--append` is given
  (protects against accidental duplicate loads),
- copies the data in bulk (`COPY`) and verifies the loaded row count.

Example output:

```
Loaded 527,390 rows into retail_transactions in 24.3s.
Verified: 527,390 rows (matches data/cleaned_retail_data.csv).
```

## Running the analysis

```bash
# via psql
psql "$DATABASE_URL" -f sql/01_sales_analysis.sql
# ... repeat for 02..06

# or run everything and verify the pipeline automatically:
python sql/verify_pipeline.py
```

All scripts are safe to re-run (`schema.sql` uses `IF NOT EXISTS`, temp tables
are `DROP ... IF EXISTS` first).

## Business Questions Answered

Every script answers named questions — each query is introduced with a comment
stating the question.

| # | Question | File |
|---|----------|------|
| 1 | Total revenue, total orders and average order value | `01` |
| 2 | Revenue contribution and share by country (with `DENSE_RANK` and cumulative `%`) | `01` |
| 3 | Best month ever by revenue (order of magnitude check) | `01` |
| 4 | Top 10 revenue-generating products | `01` |
| 5 | 2011 monthly revenue vs the previous month (MoM, with growth % and cumulative total) | `01` |
| 6 | 2011 best and worst months by YoY growth | `01` |
| 7 | Average order value per country, ranked | `01` |
| 8 | 2011 daily revenue vs the daily average (volatility detection) | `01` |
| 9 | Weekday and hourly revenue patterns | `01` |
| 10 | How many customers, new customers, repeat customers and one-time buyers | `02` |
| 11 | Repeat customer rate | `02` |
| 12 | Customer lifetime value (CLV) distribution — top, median and share of top 1% | `02` |
| 13 | Customers whose last order was > 6 months ago (at-risk for churn) | `02` |
| 14 | Customer cohort retention by first-purchase month | `02` |
| 15 | Order-value distribution — share of orders under £50 / under £100 | `02` |
| 16 | Cross-selling: products frequently bought together (self-join) | `02` |
| 17 | Average basket size and average revenue per basket | `03` |
| 18 | Most popular products by units sold | `03` |
| 19 | Products with negative revenue (returns/adjustments) | `03` |
| 20 | Products with the largest number of distinct customers | `03` |
| 21 | Revenue and quantity by product category (first token of the description) | `03` |
| 22 | Monthly revenue trend with MoM growth and contribution to the annual total | `04` |
| 23 | Year-over-year growth (2011 vs 2010) | `04` |
| 24 | Weekday revenue analysis | `04` |
| 25 | Hourly revenue analysis | `04` |
| 26 | RFM scores (R/F/M quartiles) and 7 customer segments, reproduced in SQL | `05` |
| 27 | RFM segment distribution and segment profiles | `05` |
| 28 | Customers at risk of churn, ranked by revenue | `05` |
| 29 | Top customers by country (`DENSE_RANK`) | `05` |
| 30 | `RANK` vs `DENSE_RANK` vs `ROW_NUMBER` compared on the same query | `05` |
| 31 | Top products by quantity with `RANK` | `05` |
| 32 | Time intelligence: moving average, same-month-last-year, running totals | `05` |
| 33 | Customer lifecycle: first order, last order, days between, cohort month | `05` |
| 34 | Revenue concentration: customers needed for 80% of revenue; top-10% share | `05` |
| 35 | Cohort retention matrix: % of cohort customers active in each period M0..M12 (customer cohorts by first-purchase month) | `06` |
| 36 | Cohort customer counts matrix (absolute active customers per cohort per period) | `06` |
| 37 | Cohort lifecycle summary: size, repeat customers, repeat rate, lifetime revenue, revenue per customer, avg orders, avg active months, avg lifetime days | `06` |
| 38 | Revenue by cohort age: revenue generated per cohort in each period M0..M12 | `06` |

## Advanced SQL techniques used

- **Common Table Expressions (CTEs)** — every script decomposes queries into
  readable, reusable steps (e.g. `base → reference → rfm → scored`).
- **Window functions** — `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE`, `LAG`,
  `SUM(...) OVER (...)`, `AVG(...) OVER (...)`, `FIRST_VALUE/LAST_VALUE`,
  partitioned and ordered frames.
- **Conditional aggregation** — `COUNT(*) FILTER (WHERE ...)`, `SUM(CASE WHEN ...)`.
- **Date/time intelligence** — `DATE_TRUNC`, `TO_CHAR`, `EXTRACT`,
  `EXTRACT(EPOCH ...)`, `DATE_PART`, `generate_series` where relevant.
- **Self-joins** for basket/co-purchase analysis.
- **Set / window ranking** for top-N and concentration analysis.

## RFM reproduction (pandas ↔ SQL agreement)

`05_advanced_analytics.sql` recreates the workbook's **RFM Customer Segmentation**
sheet (Recency, Frequency, Monetary quartile scores + 7 segments) directly in SQL.

To make the two engines agree exactly, the SQL uses an explicit **tie-breaker**:
quartiles are assigned with `NTILE(4) OVER (ORDER BY ..., customer_id)` so that
tied customers are ordered the same way pandas' `rank(method="first")` orders
them (pandas breaks ties by index order, which is the `customer_id`-sorted group
order). With that convention:

| Check | Result |
|---|---|
| Per-customer segment agreement (4,339 customers) | **100%** |
| R / F / M individual score agreement | ≥ 99.98% |
| Combined RFM score agreement | 99.93% |

Segment counts (identical in both engines):

```
Champions           774
Loyal Customers     538
Potential Loyalists 433
New Customers       257
At Risk             924
Needs Attention     475
Hibernating         938
```

> The residual score differences (≤ 3 of 4,339 customers) come from monetary
> values: PostgreSQL sums exact 2-dp decimals while Python sums binary floats —
> a sub-cent rounding artifact, never a data difference. Segment assignment is
> unaffected.

## Verification

`verify_pipeline.py` runs every check end-to-end and exits non-zero on failure:

- connection + schema (table, row count, columns, data types),
- every SQL script (`schema`, `01`–`06`) executes without error,
- KPI consistency CSV (pandas) vs PostgreSQL: revenue, orders, customers,
  products, units, AOV — all equal to the penny,
- RFM reproduction: same customer count, identical segment counts, 100%
  per-customer segment agreement.

Current status: **all checks pass**.

### Phase 4 — cohort & retention validation

`06_cohort_retention_analysis.sql` builds four temp tables
(`cohort_customers`, `cohort_activity`, `cohort_avail`, `cohort_matrix`) and
answers the retention questions above. `sql/cohort_validation.py` re-implements
the same cohort logic independently in pandas and reconciles the two engines
(12 checks — all PASS):

- total cohort customers = **4,339**; cohort sizes sum to 4,339;
- every cohort has M0 = **100%**;
- SQL vs pandas: cohort sizes, active-customer counts (91 cells) and retention %
  agree (max deviation 0.00 pp), revenue agrees to the penny;
- the availability grid is bounded to the data window (future months are blank,
  never fake 0%), and no customer belongs to more than one cohort;
- the **weighted retention series (M0..M12)** — total active customers across
  the cohorts with observed data at each month, divided by the total cohort
  sizes of those same cohorts — matches between engines (0.00 pp). This is the
  exact formula behind the Power BI decay-chart measure `Retention Rate`.

```bash
python sql/cohort_validation.py
```

## Generated insights

`insights_report.md` is a machine-generated report (`generate_insights_report.py`)
with the key metrics, business significance commentary, and the RFM segment
distribution. Regenerate it after any data refresh:

```bash
python sql/generate_insights_report.py
```

## Notes & caveats

- The notebook's `Month`/`Year` columns were generated with a date-parsing bug
  (e.g. `10/12/01` parsed as *2001-10-12* instead of *2010-12-01*). The SQL layer
  reconstructs real dates from `Invoice Date` + `Invoice Time` and is therefore
  the **correct** time reference. Row counts and totals are unaffected either way.
- 134,658 rows have a null `customer_id` (no customer linkage) and are retained in
  the table; they are excluded wherever customer-level analysis requires a
  customer id (RFM, CLV, cohorts), exactly as the notebook does.
- Cancellation / adjustment rows (negative quantities) were removed upstream
  during cleaning; the loaded data contains 0 of them.
