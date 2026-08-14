# Power BI — DAX Measures

All measures belong to a dedicated **Measures** (a.k.a. *Report Measures*) table.
Column references are fully qualified; adjust names if the imported tables are
renamed. The measures are written so the **FactSales** filter propagates through
the star-schema relationships (DimDate → FactSales, DimCustomer → FactSales,
DimProduct → FactSales, DimCountry → FactSales). The Phase 4 cohort measures
(section 6) read the standalone **CohortRetention** / **CohortSummary** tables
directly — they are pre-aggregated in SQL and are filtered only by their own
columns.

---

## 1. Core KPIs (Executive Overview)

```dax
Total Revenue        = SUM(FactSales[total_price])
Total Orders         = DISTINCTCOUNT(FactSales[invoice_no])
Total Units Sold     = SUM(FactSales[quantity])
Total Customers      = DISTINCTCOUNT(FactSales[customer_id])
Total Transactions   = COUNTROWS(FactSales)
```

> **Definition note — Total Customers** only counts rows where `customer_id` is
> not blank (134,658 line items in the fact have no customer). It equals the
> validated customer count of **4,339**.

---

## 2. Derived & Value Metrics

```dax
Average Order Value        = DIVIDE([Total Revenue], [Total Orders])
Average Unit Price         = DIVIDE([Total Revenue], [Total Units Sold])
Average Revenue per Customer = DIVIDE([Total Revenue], [Total Customers])
Average Orders per Customer = DIVIDE([Total Orders], [Total Customers])
Average Daily Revenue       = DIVIDE([Total Revenue], DISTINCTCOUNT(FactSales[invoice_date]))

Customer Revenue           =
    CALCULATE([Total Revenue], NOT ISBLANK(FactSales[customer_id]))

Revenue Contribution %     =
    DIVIDE([Total Revenue], CALCULATE([Total Revenue], ALLSELECTED()))
```

> **Customer Revenue** (£8,887,208.89) intentionally differs from **Total Revenue**
> (£10,619,986.68): it excludes line items with no customer attribution. Document
> this difference in the report footnote rather than hiding it.

---

## 3. Customer Behaviour (uses validated RFM dimension)

```dax
Repeat Customer Rate =
    DIVIDE(
        CALCULATE([Total Customers], DimCustomer[is_repeat] = 1),
        [Total Customers]
    )

One-Time Customer Count   = CALCULATE([Total Customers], DimCustomer[is_repeat] = 0)
Repeat Customer Count     = CALCULATE([Total Customers], DimCustomer[is_repeat] = 1)

Average Frequency (orders)   = AVERAGE(DimCustomer[frequency])
Average Recency (days)       = AVERAGE(DimCustomer[recency_days])
Average Monetary (£)         = AVERAGE(DimCustomer[monetary])
Average RFM Score            = AVERAGE(DimCustomer[rfm_score])
Customer Lifetime (days)     = AVERAGE(DimCustomer[customer_lifetime_days])

Segment Revenue Share % =
    DIVIDE(
        [Total Revenue],
        CALCULATE([Total Revenue], ALL(DimCustomer[segment]))
    )
```

> **Repeat Customer Rate = 65.57%** (2,845 repeat / 4,339 customers) — validated
> identically in PostgreSQL and the Excel workbook.

---

## 4. Time Intelligence (DimDate is the marked date table)

```dax
Previous Month Revenue =
    CALCULATE([Total Revenue], PREVIOUSMONTH(DimDate[date]))

MoM Revenue Growth % =
    DIVIDE([Total Revenue] - [Previous Month Revenue], [Previous Month Revenue])

Running Revenue YTD = TOTALYTD([Total Revenue], DimDate[date])

Revenue vs Same Period Last Year =
    [Total Revenue] - CALCULATE([Total Revenue], SAMEPERIODLASTYEAR(DimDate[date]))

YoY Revenue Growth % =
    DIVIDE(
        [Revenue vs Same Period Last Year],
        CALCULATE([Total Revenue], SAMEPERIODLASTYEAR(DimDate[date]))
    )
```

> **Caveat:** the dataset covers **13 months (Dec 2010 – Dec 2011)**. YoY
> comparisons are only meaningful for Dec 2011; for Jan–Nov 2011 the prior-year
> period is empty, so YoY% renders blank. Do not present YoY as a headline figure.
>
> **Cumulative vs YTD:** `Running Revenue YTD` is a genuine calendar **YTD**
> (`TOTALYTD`) — it resets each January. The Page 2 preview chart labelled
> *Cumulative Revenue* is the full-window running total (13 months), which is a
> different series; keep the two labels distinct and do not call the
> window-cumulative series "YTD".

---

## 5. Concentration & Ranking

```dax
Product Revenue Rank  = RANKX(ALL(DimProduct[stock_code]), [Total Revenue], , DESC)
Country Revenue Rank  = RANKX(ALL(DimCountry[country]),    [Total Revenue], , DESC)

Top 10% Customer Revenue Share =
VAR _rev      = CALCULATE([Total Revenue], NOT ISBLANK(FactSales[customer_id]))
VAR _cust     = SUMMARIZE(FactSales, DimCustomer[customer_id], "@Rev", [Total Revenue])
VAR _ranked   = ADDCOLUMNS(_cust, "@Rnk", RANKX(_cust, [@Rev], , DESC))
VAR _topN     = ROUND(COUNTROWS(_ranked) * 0.10, 0)
VAR _top      = FILTER(_ranked, [@Rnk] <= _topN)
RETURN DIVIDE(SUMX(_top, [@Rev]), _rev)
```

> **Benchmark:** top 10% of customers contribute **61.45%** of customer revenue
> (validated in SQL). This measure is documented but optional — it is not
> hard-coded in any validation step.

---

## 6. Cohort & Retention (Phase 4 — reads CohortRetention / CohortSummary)

The six cohort measures read the two standalone cohort tables (see
`data_model.md`). They are filtered only by the cohort tables' own columns
(`cohort_month`, `cohort_index`, …); use the heatmap matrix (rows =
`CohortRetention[cohort_month]`, columns = `CohortRetention[cohort_index]`) with
these measures.

```dax
Cohort Customers =
    SUMX(VALUES(CohortRetention[cohort_month]),
         CALCULATE(MAX(CohortRetention[cohort_size])))

Retained Customers =
    SUM(CohortRetention[active_customers])

Retention Rate =
    DIVIDE([Retained Customers], [Cohort Customers])

Cohort Repeat Customer Rate =
    DIVIDE(SUM(CohortSummary[repeat_customers]), SUM(CohortSummary[cohort_size]))

Revenue by Cohort =
    SUM(CohortRetention[revenue])

Revenue per Cohort Customer =
    DIVIDE([Revenue by Cohort], [Cohort Customers])
```

> **Why `Cohort Customers` uses SUMX + MAX:** `cohort_size` repeats on every row
> of a cohort (one row per M0..M12), so a plain `SUM` would overcount
> (36,807 instead of 4,339). `SUMX(VALUES(...), MAX(...))` returns the true total.
>
> **`Retention Rate` is the weighted retention** at each cohort month:
>
> ```text
> weighted retention at month N =
>     SUM(active_customers) across cohorts with observed data at N
>   ÷ SUM(cohort_size) across those same cohorts
> ```
>
> It is deliberately **not** `AVERAGE(CohortRetention[retention_pct])` (an
> unweighted mean). Because the chart is drawn over `cohort_index`, the
> denominator uses only the cohorts that actually have a row for that month —
> future/unavailable periods are absent from the table and therefore never
> contribute a zero. In a heatmap cell (one cohort × one month) the measure
> equals that cell's `retention_pct`; over an M-line it is the cohort-size
> weighted value. M0 is 100% by construction. Validated against SQL/Pandas for
> M0..M12 (max deviation 0.00 pp).
>
> **`Cohort Repeat Customer Rate`** is named to avoid clashing with the existing
> **`Repeat Customer Rate`** (section 3); it uses the **cohort** definition of
> repeat (customer active in ≥2 calendar months) from `CohortSummary`, not the
> invoice-count definition.
>
> **Validated figures:** total cohort customers **4,339** (matches `Total
> Customers`), weighted M1 retention **22.7%**, cohort repeat rate **65.5%**,
> cohort lifetime revenue **£8,887,208.89** (matches **Customer Revenue** —
> both are attributed-only), founding-cohort revenue per customer **£5,087**.

---

## Measure Table Layout (suggested grouping)

| Group            | Measures |
|------------------|----------|
| Core KPIs        | Total Revenue, Total Orders, Total Units Sold, Total Customers, Total Transactions |
| Value            | Average Order Value, Average Unit Price, Average Revenue per Customer, Average Orders per Customer, Average Daily Revenue, Customer Revenue, Revenue Contribution % |
| Customer         | Repeat Customer Rate, Repeat Customer Count, One-Time Customer Count, Avg Frequency, Avg Recency, Avg Monetary, Avg RFM Score, Customer Lifetime, Segment Revenue Share % |
| Time             | Previous Month Revenue, MoM Revenue Growth %, Running Revenue YTD, Revenue vs Same Period Last Year, YoY Revenue Growth % |
| Ranking          | Product Revenue Rank, Country Revenue Rank, Top 10% Customer Revenue Share |
| Cohort           | Cohort Customers, Retained Customers, Retention Rate, Cohort Repeat Customer Rate, Revenue by Cohort, Revenue per Cohort Customer |
