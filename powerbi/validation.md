# Power BI — Validation Report

The Power BI dataset (`powerbi/dataset/*.csv`) is a **projection of the validated
PostgreSQL source**, not an independent calculation. `powerbi/scripts/validate_pbi.py`
reconciles every table against PostgreSQL / SQL figures (37 checks). Run:

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/retail_analysis
python powerbi/scripts/validate_pbi.py
```

## Results (all checks PASS)

### KPI benchmarks vs Excel / SQL
| Metric | Expected | FactSales | Match |
|--------|----------|-----------|-------|
| Total Revenue (£) | 10,619,986.68 | 10,619,986.68 | ✅ |
| Total Orders | 22,064 | 22,064 | ✅ |
| Total Customers | 4,339 | 4,339 | ✅ |
| Total Units | 5,438,062 | 5,438,062 | ✅ |
| Average Order Value (£) | 481.33 | 481.33 | ✅ |

### Monthly revenue (13 months) vs SQL
Every month (2010-12 … 2011-12) reconciles to the penny against
`retail_transactions`.

### RFM reconciliation (100%)
Segment counts in `DimCustomer` vs SQL NTILE RFM (identical methodology):

| Segment | Count |
|---------|-------|
| Hibernating | 938 |
| At Risk | 924 |
| Champions | 774 |
| Loyal Customers | 538 |
| Needs Attention | 475 |
| Potential Loyalists | 433 |
| New Customers | 257 |
| **Total** | **4,339** |

### Dimension integrity
- DimCustomer: 4,339 rows, PK unique ✅
- DimProduct: 3,947 rows, PK unique ✅
- DimDate: 730 rows, PK unique, fully covers the fact's date range ✅
- DimCountry: 38 rows, covers every distinct fact country ✅

### Referential integrity
- Customer orphans: **0** (all fact customer_ids resolve to DimCustomer)
- Product orphans: **0** (all fact stock_codes resolve to DimProduct)

### Derived metrics used in the report
| Metric | Power BI dataset | SQL | Match |
|--------|------------------|-----|-------|
| Repeat Customer Rate | 65.57% | 65.57% | ✅ |
| Repeat customers | 2,845 | 2,845 | ✅ |
| One-time customers | 1,494 | 1,494 | ✅ |
| Customer Revenue (non-null) | £8,887,208.89 | £8,887,208.89 | ✅ |
| Unattributed line items | 134,658 | 134,658 | ✅ |

### Geography reconciliation (mutually exclusive + exhaustive)
Region shares (vs total revenue, computed from `DimCountry[region]`):

| Region | Revenue (£) | Share | Countries |
|--------|-------------|-------|-----------|
| UK & Ireland | 9,283,201.03 | 87.4% | United Kingdom, Eire, Channel Islands |
| Europe | 1,097,393.93 | 10.3% | 21 EU/EEA + European Community |
| Asia Pacific | 212,632.47 | 2.0% | Australia, Hong Kong, Japan, Singapore |
| Middle East & Africa | 13,627.94 | 0.1% | Bahrain, Israel, Lebanon, RSA, Saudi Arabia, UAE |
| Americas | 8,390.37 | 0.1% | Brazil, Canada, USA |
| Unspecified | 4,740.94 | 0.0% | no country code |
| **Total** | **10,619,986.68** | **100.0%** | |

Every country maps to exactly one region, so the shares sum to 100% and
regional revenue equals total revenue to the penny. The country-level totals
reconcile the same way (top 15 markets = 98.6% of revenue).

### Weekday / trading-day finding (genuine data result)
- **Saturday has no transactions** in the source — 0 rows and 0 trading days
  across Dec 2010–Dec 2011. The preview shows £0 with an explicit footnote;
  nothing is imputed.
- **Sunday is genuine trading**: £806,790.78 across 50 Sundays.
- Highest-revenue weekday: **Thursday** £2,199,292.57 (4,689 orders).

### Phase 4 — cohort & retention reconciliation (100%)
The dataset's `CohortRetention.csv` (91 rows) and `CohortSummary.csv` (13 rows)
reconcile against the SQL cohort layer (`sql/06_cohort_retention_analysis.sql`)
and, independently, against pandas (`sql/cohort_validation.py`, 12/12 PASS):

| Check | Expected | Result | Match |
|-------|----------|--------|-------|
| Cohort customers | 4,339 (same as Total Customers) | 4,339 | ✅ |
| Cohort sizes sum | 4,339 | 4,339 | ✅ |
| Cohorts (first-purchase months) | 13 (2010-12 … 2011-12) | 13 | ✅ |
| M0 retention | 100.0% for every cohort | 100.0% ×13 | ✅ |
| Retention % SQL vs pandas (91 cells) | identical | max deviation 0.00 pp | ✅ |
| Active-customer counts SQL vs pandas | identical | 91/91 | ✅ |
| Revenue SQL vs pandas | identical | to the penny | ✅ |
| Availability grid | bounded to data window (future months blank) | confirmed | ✅ |
| Weighted retention series SQL vs pandas (M0..M12) | identical | max deviation 0.00 pp | ✅ |

### Weighted retention series — DAX vs SQL/Pandas (M0..M12)
The decay chart's measure **`Retention Rate`** is the cohort-size weighted value
at each month index:

```text
weighted retention at month N = SUM(active_customers) ÷ SUM(cohort_size)
                                over only the cohorts with observed data at N
```

Future/unavailable periods are absent from `CohortRetention`, so they are never
treated as zero. `validate_pbi.py` re-computes exactly this aggregation on the
Power BI dataset (mirroring the DAX) and reconciles it against the SQL matrix —
**max deviation 0.00 pp across all 13 indices**:

| Index | Weighted retention (PBI == SQL) |
|-------|--------------------------------|
| M0  | 100.0% (all 13 cohorts available) |
| M1  | 22.7% |
| M2  | 23.7% |
| M3  | 25.6% |
| M4  | 27.3% |
| M5  | 27.9% |
| M6  | 27.2% |
| M7  | 26.7% |
| M8  | 27.9% |
| M9  | 30.0% |
| M10 | 30.3% |
| M11 | 37.9% |
| M12 | 26.6% (only the Dec-2010 cohort reaches M12) |

The `AVERAGE(retention_pct)` (unweighted) formula previously used for this series
was replaced — it does not equal the weighted value when cohort sizes differ.
Weighted averages (all customers with ≥1 observed month): M1 retention **22.7%**
(976 / 4,298), 6-month retention **27.2%** (804 / 2,960), plateau months 3–10 in
the 25.6–30.3% band, M11 **37.9%** (Peak season; Dec-2010 cohort = 50.3%). The
founding Dec-2010 cohort: repeat rate **87.5%**, revenue per customer **£5,087**,
**50.7%** of total cohort revenue. Because **cohort tables are standalone and
already pre-aggregated**, no relationship or row-level cross-check applies — the
figures above are the full reconciliation.

## Known limitations (documented, not hidden)
1. **Cancellation Rate** is intentionally absent — after cleaning, zero
   cancellation-only invoices remain in `retail_transactions`; the metric is not
   supportable and would be fabricated. The Excel workbook retains the
   *Cancellation per Country* / *Top 10 Cancellations* sheets from its
   pre-cleaning data, but those cannot be reproduced in the validated database.
2. **YoY growth** is only meaningful for Dec 2011 (data spans Dec 2010–Dec 2011).
3. **Total Revenue** (£10,619,986.68) includes 134,658 unattributed line items;
   **Customer Revenue** (£8,887,208.89) excludes them. Both are surfaced.
