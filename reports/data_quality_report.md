# Data Quality & Monitoring Report — Retail Analytics

- **Generated:** 2026-08-15T19:16:40
- **Source dataset:** `data/cleaned_retail_data.csv` (527,390 rows x 13 columns)
- **Overall data-quality status:** **WARNING**
- **Latest pipeline run:** `2026-08-15-001` (FAILED, 2026-08-15T15:33:22) — failed at stage `POSTGRESQL LOAD`

## 1. Dataset snapshot

| Metric | Value |
|---|---|
| Revenue | £10,619,986.68 |
| Orders | 22,064 |
| Customers (distinct, attributed) | 4,339 |
| Products (stock codes) | 3,947 |
| Units sold | 5,438,062 |
| Average order value | £481.33 |
| Repeat customers | 2,845 |
| Customer revenue (attributed) | £8,887,208.89 |

## 2. Automated data-quality checks

| Status | Check | Detail |
|---|---|---|
| PASS | Schema: required columns | 13 columns |
| PASS | Schema: numeric dtypes | Quantity/UnitPrice/TotalPrice |
| PASS | Missing: critical fields | 0 nulls in critical fields |
| WARNING | Missing: CustomerID | 134,658 rows (kept per validated logic - customer-level metrics use non-null customers) |
| WARNING | Missing: Description | 1,454 rows (informational - preserved as NULL in PostgreSQL) |
| PASS | Duplicates: full rows | 0 |
| WARNING | Numeric: negative quantity | 1,336 rows (kept per validated cleaning - cancellations removed by invoice prefix only) |
| WARNING | Numeric: non-positive unit price | 2,512 rows (kept per validated cleaning) |
| WARNING | Numeric: non-positive TotalPrice | 2,512 rows (kept per validated cleaning) |
| PASS | Numeric: no NaN in numerics | 0 |
| PASS | Dates: all parsed | 0 malformed |
| PASS | Dates: expected window 2010-12..2011-12 | 2010-12-01 .. 2011-12-09 |
| PASS | Business: cancellations removed | 0 remaining |
| PASS | Business: TotalPrice == Quantity * UnitPrice | max abs diff 4.55e-13 |
| PASS | Business: customer attribution | 4,339 distinct customers |

## 3. Summary of issues

| Issue | Count | Notes |
|---|---|---|
| Missing critical values | 0 | all critical fields complete |
| Duplicate rows | 0 | none |
| Invalid dates | 0 | all parsed |
| Cancellation rows remaining | 0 | removed by cleaning |
| Rows without CustomerID | 134,658 | retained; excluded from customer-level analytics (validated logic) |
| Negative quantity rows | 1,336 | retained per validated cleaning (cancellations removed by invoice prefix) |
| Non-positive unit price rows | 2,512 | retained per validated cleaning |
| Non-positive TotalPrice rows | 2,512 | retained per validated cleaning |
| Distinct customers | 4,339 | matches the validated benchmark |

## 4. Cross-system reconciliation

Python vs PostgreSQL: **PASS** (16 metrics, all agree).

| KPI | PostgreSQL value |
|---|---|
| Revenue | £10,619,986.68 |
| Orders | 22,064 |
| Customers | 4,339 |
| Products (stock codes) | 3,947 |
| Units sold | 5,438,062 |
| AOV | £481.33 |
| Repeat customers | 2,845 |
| Customer revenue (attributed) | £8,887,208.89 |

## 5. Interpretation

The automated gate reports **no critical failures**: schema, missing critical fields, duplicates, date parsing and the business rules all pass. The `WARNING` items are deliberate and validated: null CustomerID rows, negative-quantity and non-positive-price rows are retained because the Phase 1-4 cleaning removes cancellations by invoice prefix only, and the customer-level analytics consistently exclude the 134,658 unattributed rows. None of these affect the benchmark KPIs, which agree to the penny between Python and PostgreSQL.

_Generated automatically — see `reports/generate_data_quality_report.py`._
