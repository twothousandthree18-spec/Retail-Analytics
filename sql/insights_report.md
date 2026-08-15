# Retail SQL Insights Report

> Machine-generated on 2026-08-13 by `sql/generate_insights_report.py` against the `retail_transactions` PostgreSQL table. Every figure is computed from the cleaned dataset shared with the Excel workbook.

## Key Metrics

| Metric | Value |
|---|---|
| Total Revenue | 10,619,986.68 |
| Total Orders | 22,064 |
| Total Units Sold | 5,438,062 |
| Average Order Value | 481.33 |
| Top Country | United Kingdom (8,979,619.97, 84.55% of revenue) |
| Top Customer | 14646 (280,206.02) |
| Top Product (stock code) | Dot (206,248.77) |
| Latest MoM Revenue Growth | -57.59% |
| Average MoM Revenue Growth | 3.03% |
| Repeat Customer Rate | 65.57% |
| Customers for 80% of Revenue | 1,130 of 4,339 |
| Revenue Share of Top 10% Customers | 61.45% |

## Business Significance

- **Revenue concentration:** Just 1,130 of 4,339 customers (26.04%) generate 80% of revenue, and the top 10% of customers hold 61.45% of it. The customer base is strongly Pareto-distributed (a retail long-tail).
- **Geography:** Revenue is highly concentrated in a single market: United Kingdom alone accounts for 84.55% of total revenue. The business is a domestic-dominant operator with international upside - growth strategy depends heavily on one country.
- **Products:** The highest-revenue stock code is 'Dot' (Dotcom Postage) at 206,248.77 - an operational/postage line, not a physical product. Excluding postage and adjustment codes, physical product revenue would be lower, which matters when reading product rankings.
- **Momentum:** Revenue fell 57.59% month over month in the final period - expected, because the dataset's last month (December 2011) is truncated (data ends 9 Dec 2011), so the final month is not a full month.
- **Seasonality:** Peak revenue month is 2011-11 (1,503,866.78); Q4 (Sep-Nov) is the strongest sales window, consistent with a seasonal gift/homeware retailer.

## RFM Customer Segments (reproduced in SQL)

| Segment | Customers | Share |
|---|---|---|
| Hibernating | 938 | 21.62% |
| At Risk | 924 | 21.30% |
| Champions | 774 | 17.84% |
| Loyal Customers | 538 | 12.40% |
| Needs Attention | 475 | 10.95% |
| Potential Loyalists | 433 | 9.98% |
| New Customers | 257 | 5.92% |

These segment counts match the workbook's `RFM Customer Segmentation` sheet (4,339 customers; 100% segment-level agreement when the same quartile tie-breaking is used).
