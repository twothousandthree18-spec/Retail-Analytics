# Power BI — DAX Measures

All measures belong to a dedicated **Measures** (a.k.a. *Report Measures*) table.
Column references are fully qualified; adjust names if the imported tables are
renamed. The measures are written so the **FactSales** filter propagates through
the star-schema relationships (DimDate → FactSales, DimCustomer → FactSales,
DimProduct → FactSales, DimCountry → FactSales).

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

## Measure Table Layout (suggested grouping)

| Group            | Measures |
|------------------|----------|
| Core KPIs        | Total Revenue, Total Orders, Total Units Sold, Total Customers, Total Transactions |
| Value            | Average Order Value, Average Unit Price, Average Revenue per Customer, Average Orders per Customer, Average Daily Revenue, Customer Revenue, Revenue Contribution % |
| Customer         | Repeat Customer Rate, Repeat Customer Count, One-Time Customer Count, Avg Frequency, Avg Recency, Avg Monetary, Avg RFM Score, Customer Lifetime, Segment Revenue Share % |
| Time             | Previous Month Revenue, MoM Revenue Growth %, Running Revenue YTD, Revenue vs Same Period Last Year, YoY Revenue Growth % |
| Ranking          | Product Revenue Rank, Country Revenue Rank, Top 10% Customer Revenue Share |
