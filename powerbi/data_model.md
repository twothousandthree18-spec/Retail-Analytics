# Power BI — Data Model

Star schema, 1 fact table + 4 dimension tables, **plus 2 standalone Phase 4
cohort tables**, built from the **validated PostgreSQL source**
(`retail_transactions`, 527,390 rows). No cleaning or recalculation was performed
in the Power BI layer; all numbers trace back to the validated SQL / Excel
pipeline.

```
                         DimDate
                       ┌──────────┐   date (PK, 1)
            invoice_date│ date ◄──┼─────────────────┐
                       └──────────┘                 │
                                                    │
 DimCustomer        DimProduct        DimCountry    │
 ┌──────────────┐  ┌──────────────┐  ┌──────────┐   │
 │ customer_id(PK) │  │ stock_code(PK)│  │ country(PK) │  │
 │ segment/RFM ◄──┼─►│ category     │  │ region   │  │  ┌──────────────┐
 └──────────────┘  └──────────────┘  └──────────┘  │  │  FactSales    │
    customer_id ◄─────┼────────────────────────────┼──┤ transaction_id│
    stock_code  ◄─────┼────────────────────────────┼──┤ invoice_no    │
    country     ◄─────┼────────────────────────────┼──┤ customer_id   │
        (many-to-one, all ────────────┼────────────) ──┤ stock_code    │
                                                    └──┤ country       │
                                                       │ invoice_date  │
                                                       │ quantity      │
                                                       │ unit_price    │
                                                       │ total_price   │
                                                       └──────────────┘
```

## Tables & Columns

### FactSales (527,390 rows — one row per transaction line item)
| Column | Type | Notes |
|--------|------|-------|
| transaction_id | Integer | Surrogate PK of the transaction line (from load order) |
| invoice_no | Text | Invoice number; an invoice is one order (22,064 distinct) |
| stock_code | Text | Product code FK → DimProduct |
| customer_id | Integer, nullable | FK → DimCustomer; NULL = unattributed line (134,658 rows) |
| country | Text | FK → DimCountry |
| invoice_date | Datetime | FK → DimDate[date] (datetime coerces to date in relationship) |
| quantity | Integer | Units (can be negative on returns/cancellations) |
| unit_price | Currency | Unit price in GBP |
| total_price | Currency | Revenue = quantity × unit_price (line level) |

### DimDate (730 rows, 2010-01-01 .. 2011-12-31) — **marked as date table**
`date (PK)`, `year`, `quarter`, `quarter_label`, `month_number`, `month_name`,
`year_month` (2010-12), `year_month_name` (Dec 2010), `week_of_year`, `day`,
`day_of_week_number`, `day_of_week_name`, `is_weekend`.

### DimCustomer (4,339 rows) — RFM attributes from validated SQL
`customer_id (PK)`, `first_order_date`, `last_order_date`, `recency_days`,
`frequency` (distinct orders), `monetary` (£), `r_score`, `f_score`, `m_score`
(quartiles 1–4), `rfm_score` (3–12), `segment`, `is_repeat` (0/1),
`customer_lifetime_days`, `first_purchase_year_month`.

> **RFM provenance:** generated with the exact methodology validated in
> `sql/05_advanced_analytics.sql` — NTILE quartiles with the `customer_id`
> tie-breaker, and the 7-segment rule (Champions / Loyal Customers / Potential
> Loyalists / New Customers / At Risk / Needs Attention / Hibernating). Segment
> counts reconcile 100% with both SQL and the Excel workbook.

### DimProduct (3,947 rows)
`stock_code (PK)`, `description` (blank for 114 codes), `category` (first word
of description, upper-cased; 831 values).

### DimCountry (38 rows)
`country (PK)`, `region`. Region groupings:

| Region | Countries |
|--------|-----------|
| UK & Ireland | United Kingdom, Eire, Channel Islands |
| Europe | Netherlands, Germany, France, Spain, Switzerland, Belgium, Sweden, Norway, Portugal, Finland, Denmark, Italy, Cyprus, Austria, Poland, Greece, Iceland, Malta, Lithuania, Czech Republic, European Community |
| Asia Pacific | Australia, Japan, Singapore, Hong Kong |
| Middle East & Africa | Israel, United Arab Emirates, Lebanon, Bahrain, Saudi Arabia, Rsa |
| Americas | Canada, Usa, Brazil |
| Unspecified | Unspecified |

### CohortRetention (91 rows — Phase 4, standalone)
Retention matrix in long form (one row per cohort-month), computed in SQL
(`sql/06_cohort_retention_analysis.sql`) and validated against an independent
pandas implementation (`sql/cohort_validation.py`, 12/12 PASS).

| Column | Type | Notes |
|--------|------|-------|
| cohort_month | Text | First-purchase month of the customer cohort (2010-12 … 2011-12) |
| cohort_index | Integer | Months since cohort start, M0 … M12 (M0 = signup month) |
| cohort_size | Integer | Customers in the cohort (repeated per row; use `MAX` over cohort_month) |
| active_customers | Integer | Customers with ≥1 transaction in that cohort month |
| retention_pct | Decimal | active ÷ cohort_size × 100 (M0 = 100.0 by construction) |
| revenue | Decimal | Revenue (attributed) generated in that cohort month |

Only months within the data window exist — **future months are absent, never
fake 0%** (e.g. 2011-12 has only M0). Import as a table; no relationship needed.

### CohortSummary (13 rows — Phase 4, standalone)
One row per cohort with the lifecycle summary used on the retention page and in
`reports/cohort_insights_report.md`.

| Column | Type | Notes |
|--------|------|-------|
| cohort_month | Text | First-purchase month (2010-12 … 2011-12) |
| cohort_size | Integer | 4,339 total across all cohorts |
| repeat_customers | Integer | Customers with >1 purchase month |
| repeat_rate | Decimal | Repeat customers ÷ cohort size × 100 |
| lifetime_revenue | Currency | Attributed revenue from all cohort customers (full lifetime) |
| revenue_per_customer | Currency | Lifetime revenue ÷ cohort size |
| avg_orders_per_customer | Decimal | Distinct invoices ÷ cohort size |
| avg_active_months | Decimal | Months in which the customer transacted |
| avg_lifetime_days | Decimal | Last purchase − first purchase (≥0) |
| longest_lifetime_days | Integer | Max lifetime days in the cohort |

## Relationships
| From (1) | To (many) | Cardinality | Filter direction |
|----------|-----------|-------------|------------------|
| DimDate[date] | FactSales[invoice_date] | One-to-many | Single (both directions available) |
| DimCustomer[customer_id] | FactSales[customer_id] | One-to-many | Single |
| DimProduct[stock_code] | FactSales[stock_code] | One-to-many | Single |
| DimCountry[country] | FactSales[country] | One-to-many | Single |

All relationships are single-direction (dimension → fact), which is the
recommended star-schema pattern and keeps cross-filtering deterministic. The
cohort tables are intentionally **unrelated** — they are pre-aggregated in SQL
and are filtered only by their own columns (the 6 cohort measures read them
directly, e.g. `Retention Rate` = `DIVIDE(SUM(active_customers),
SUM(cohort_size))` over the visible cohort-month rows — the cohort-size weighted
retention, not an unweighted mean).

## Loading the dataset in Power BI Desktop (Get Data → Text/CSV)
1. **FactSales.csv** — set `total_price` to **Currency**, `invoice_date` to **Datetime**, `quantity` to **Whole Number**.
2. **DimDate.csv** — set `date` to **Date**; mark as **Date Table** (Table tools).
3. **DimCustomer.csv** — set `monetary` to **Currency**, `recency_days`/`frequency`/scores to **Whole Number**, `is_repeat` to **Whole Number**.
4. **DimProduct.csv** / **DimCountry.csv** — defaults; `country`/`stock_code` text.
5. **CohortRetention.csv** — set `revenue` to **Currency**, `retention_pct` to **Decimal**, `cohort_index`/`cohort_size`/`active_customers` to **Whole Number**.
6. **CohortSummary.csv** — set currency columns to **Currency**, everything else numeric (integers/decimal).
7. Create the four relationships as above.
8. Put measures (see `dax_measures.md`) in a dedicated **Measures** table.

Alternative source: if direct CSV import is preferred over the exported files,
connect Power BI directly to PostgreSQL (`retail_transactions`) and define the
same model there — all columns exist in the source table. The exported CSV set
is the **fallback path** and is byte-for-byte derived from the same validated
data (see `validation.md`).
