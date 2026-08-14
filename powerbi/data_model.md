# Power BI — Data Model

Star schema, 1 fact table + 4 dimension tables, built from the **validated
PostgreSQL source** (`retail_transactions`, 527,390 rows). No cleaning or
recalculation was performed in the Power BI layer; all numbers trace back to the
validated SQL / Excel pipeline.

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

## Relationships
| From (1) | To (many) | Cardinality | Filter direction |
|----------|-----------|-------------|------------------|
| DimDate[date] | FactSales[invoice_date] | One-to-many | Single (both directions available) |
| DimCustomer[customer_id] | FactSales[customer_id] | One-to-many | Single |
| DimProduct[stock_code] | FactSales[stock_code] | One-to-many | Single |
| DimCountry[country] | FactSales[country] | One-to-many | Single |

All relationships are single-direction (dimension → fact), which is the
recommended star-schema pattern and keeps cross-filtering deterministic.

## Loading the dataset in Power BI Desktop (Get Data → Text/CSV)
1. **FactSales.csv** — set `total_price` to **Currency**, `invoice_date` to **Datetime**, `quantity` to **Whole Number**.
2. **DimDate.csv** — set `date` to **Date**; mark as **Date Table** (Table tools).
3. **DimCustomer.csv** — set `monetary` to **Currency**, `recency_days`/`frequency`/scores to **Whole Number**, `is_repeat` to **Whole Number**.
4. **DimProduct.csv** / **DimCountry.csv** — defaults; `country`/`stock_code` text.
5. Create the four relationships as above.
6. Put measures (see `dax_measures.md`) in a dedicated **Measures** table.

Alternative source: if direct CSV import is preferred over the exported files,
connect Power BI directly to PostgreSQL (`retail_transactions`) and define the
same model there — all columns exist in the source table. The exported CSV set
is the **fallback path** and is byte-for-byte derived from the same validated
data (see `validation.md`).
