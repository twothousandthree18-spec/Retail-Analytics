# Cohort & Customer Retention Insights

> Machine-generated on 2026-08-14 by `reports/generate_cohort_insights.py` from the Phase 4 cohort tables (`powerbi/dataset/CohortRetention.csv`, `CohortSummary.csv`), which are validated 100% against the PostgreSQL queries in `sql/06_cohort_retention_analysis.sql`.

## 1. Executive Summary

Across the 13 acquisition cohorts (Dec 2010 – Dec 2011) the business acquired **4,339 customers**, of whom **2,845** (65.6%) returned for at least one further purchase. The cohort analysis shows a textbook but striking pattern: **retention is highest at the start of life (M1 typically 11–37%), settles to a 20–30% plateau rather than decaying to zero, and the founding December 2010 cohort dominates everything that follows.**

- The **Dec 2010 founding cohort** (885 customers) is the largest, the most loyal (repeat rate 87.5%, M1 retention 36.6%) and generates **£4,502,009.52 — 50.7% of all customer-attributed revenue**.
- Weighted average **M1 retention is 22.7%** (976 of 4,298 customers return the month after acquisition) and **M6 retention is 27.2%** (804 of 2,960).
- Retention does not linearly decay to zero: it drops sharply after M0, settles to a 25.6%–30.3% plateau for months 3–10, then spikes in the M11 (November 2011) peak season.
- **First-purchase month revenue (M0) is £2,244,830.59 = 25.3% of lifetime revenue** — acquisition itself is the largest single revenue event for a customer.
- Cohorts acquired later in the window (from autumn 2011) are **larger but weaker**: their M1 retention and repeat rates fall well below the founding cohort, and they have had less time to accrue revenue.

## 2. Methodology

| Element | Definition |
|---|---|
| Cohort | All customers whose **first purchase month** falls in that month (M0 = acquisition month) |
| Cohort Index | Whole months elapsed from cohort month to purchase month (M0..M12) |
| Retention | **Customers** active in period N ÷ customers acquired in the cohort (customer counts, never revenue) |
| Data window | Dec 2010 – Dec 2011 (13 months; Dec 2011 is partial, data ends 9 Dec 2011) |
| Exclusion | 134,658 transactions with NULL `customer_id` are excluded (attribution impossible) |
| Future cells | Cohorts are only shown up to the last month of the window; future periods are blank, never 0% |
| Revenue by cohort | Sum of `total_price` across the cohort's transactions (revenue retention is tracked separately from customer retention) |

Implemented in `sql/06_cohort_retention_analysis.sql` (temp-table + window-function queries), mirrored independently in pandas by `sql/cohort_validation.py`, and exported to `CohortRetention.csv` (91 rows) and `CohortSummary.csv` (13 rows).

## 3. Cohorts at a Glance

| Cohort | Customers | Repeat Rate | Lifetime Revenue | Rev / Customer | Avg Orders | Avg Active Months | Avg Lifetime (days) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2010-12 | 885 | 87.5% | £4,502,010 | £5,087 | 9.4 | 5.4 | 268 |
| 2011-01 | 417 | 81.5% | £1,122,957 | £2,693 | 5.2 | 3.9 | 208 |
| 2011-02 | 380 | 77.1% | £592,500 | £1,559 | 4.1 | 3.3 | 171 |
| 2011-03 | 452 | 72.1% | £641,669 | £1,420 | 3.6 | 2.9 | 141 |
| 2011-04 | 300 | 66.7% | £325,723 | £1,086 | 3.1 | 2.6 | 113 |
| 2011-05 | 284 | 69.4% | £454,679 | £1,601 | 2.9 | 2.3 | 100 |
| 2011-06 | 242 | 64.5% | £272,500 | £1,126 | 2.7 | 2.3 | 83 |
| 2011-07 | 188 | 60.6% | £143,728 | £765 | 2.4 | 2.0 | 58 |
| 2011-08 | 169 | 54.4% | £195,765 | £1,158 | 2.1 | 1.8 | 43 |
| 2011-09 | 299 | 47.8% | £232,634 | £778 | 2.0 | 1.6 | 27 |
| 2011-10 | 358 | 34.6% | £225,684 | £630 | 1.7 | 1.4 | 12 |
| 2011-11 | 324 | 26.2% | £150,355 | £464 | 1.4 | 1.1 | 4 |
| 2011-12 | 41 | 2.4% | £27,005 | £659 | 1.1 | 1.0 | 0 |
| **Total / Avg** | **4,339** | **65.6%** | **£8,887,209** | **£2,048** | **3.2*** | **2.4*** | **95*** |

\* unweighted mean of cohort averages. **Repeat rate** = share of cohort customers who ever purchased again after their first month. The Dec 2010 cohort leads every metric; later cohorts show broadly lower values, though the most recent cohorts have also simply had less time to accrue repeat activity (and partial Dec 2011 is not comparable).

## 4. Customer Retention Matrix (% of cohort active by period)

| Cohort | N | M0 | M1 | M2 | M3 | M4 | M5 | M6 | M7 | M8 | M9 | M10 | M11 | M12 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2010-12 | 885 | 100.0 | 36.6 | 32.3 | 38.4 | 36.3 | 39.8 | 36.3 | 34.9 | 35.4 | 39.5 | 37.4 | 50.3 | 26.6 |
| 2011-01 | 417 | 100.0 | 22.1 | 26.6 | 23.0 | 32.1 | 28.8 | 24.7 | 24.2 | 30.0 | 32.6 | 36.5 | 11.8 | — |
| 2011-02 | 380 | 100.0 | 18.7 | 18.7 | 28.4 | 27.1 | 24.7 | 25.3 | 27.9 | 24.7 | 30.5 | 6.8 | — | — |
| 2011-03 | 452 | 100.0 | 15.0 | 25.2 | 19.9 | 22.4 | 16.8 | 26.8 | 23.0 | 27.9 | 8.6 | — | — | — |
| 2011-04 | 300 | 100.0 | 21.3 | 20.3 | 21.0 | 19.7 | 22.7 | 21.7 | 26.0 | 7.3 | — | — | — | — |
| 2011-05 | 284 | 100.0 | 19.0 | 17.2 | 17.2 | 20.8 | 23.2 | 26.4 | 9.5 | — | — | — | — | — |
| 2011-06 | 242 | 100.0 | 17.4 | 15.7 | 26.4 | 23.1 | 33.5 | 9.5 | — | — | — | — | — | — |
| 2011-07 | 188 | 100.0 | 18.1 | 20.7 | 22.3 | 27.1 | 11.2 | — | — | — | — | — | — | — |
| 2011-08 | 169 | 100.0 | 20.7 | 24.9 | 24.3 | 12.4 | — | — | — | — | — | — | — | — |
| 2011-09 | 299 | 100.0 | 23.4 | 30.1 | 11.4 | — | — | — | — | — | — | — | — | — |
| 2011-10 | 358 | 100.0 | 24.0 | 11.4 | — | — | — | — | — | — | — | — | — | — |
| 2011-11 | 324 | 100.0 | 11.1 | — | — | — | — | — | — | — | — | — | — | — |
| 2011-12 | 41 | 100.0 | — | — | — | — | — | — | — | — | — | — | — | — |
| **Weighted avg** | | 100.0 | 22.7 | 23.7 | 25.6 | 27.3 | 27.9 | 27.2 | 26.7 | 27.9 | 30.0 | 30.3 | 37.9 | 26.6 |

`—` = period after the end of the data window (future), left blank — never recorded as 0%. M0 is always 100% by construction (the cohort's own acquisition month).

## 5. Revenue by Cohort Age

| Cohort | M0 | M1 | M2 | M3 | M4 | M5 | M6 | M7 | M8 | M9 | M10 | M11 | M12 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2010-12 | £570,423 | £275,734 | £233,390 | £302,367 | £204,034 | £336,114 | £313,668 | £310,304 | £331,001 | £471,792 | £455,479 | £512,341 | £185,361 |
| 2011-01 | £292,367 | £54,994 | £63,157 | £71,526 | £80,990 | £84,465 | £70,073 | £72,503 | £71,870 | £111,371 | £123,253 | £26,388 | — |
| 2011-02 | £157,701 | £28,938 | £40,964 | £48,155 | £40,089 | £34,156 | £49,674 | £62,293 | £55,241 | £64,689 | £10,600 | — | — |
| 2011-03 | £199,620 | £30,040 | £58,958 | £42,739 | £51,392 | £39,962 | £64,824 | £70,524 | £70,848 | £12,761 | — | — | — |
| 2011-04 | £121,809 | £29,399 | £25,029 | £24,283 | £26,253 | £30,103 | £28,506 | £34,010 | £6,332 | — | — | — | — |
| 2011-05 | £123,739 | £18,642 | £20,156 | £19,162 | £27,753 | £32,875 | £33,168 | £179,184 | — | — | — | — | — |
| 2011-06 | £135,415 | £14,738 | £14,104 | £30,899 | £26,670 | £42,531 | £8,143 | — | — | — | — | — | — |
| 2011-07 | £73,860 | £11,790 | £15,488 | £17,392 | £19,157 | £6,041 | — | — | — | — | — | — | — |
| 2011-08 | £79,601 | £20,934 | £35,458 | £44,488 | £15,284 | — | — | — | — | — | — | — | — |
| 2011-09 | £154,734 | £28,701 | £36,899 | £12,300 | — | — | — | — | — | — | — | — | — |
| 2011-10 | £173,425 | £39,691 | £12,567 | — | — | — | — | — | — | — | — | — | — |
| 2011-11 | £135,131 | £15,223 | — | — | — | — | — | — | — | — | — | — | — |
| 2011-12 | £27,005 | — | — | — | — | — | — | — | — | — | — | — | — |

Customer-attributed revenue totals **£8,887,208.89** across all cohorts. The acquisition month M0 alone contributes **£2,244,830.59 (25.3%)** of lifetime revenue — each cohort pays for its own acquisition through its first-month purchases, and every later month is incremental.

## 6. Findings & Business Implications

1. **The founding cohort carries the business.** Dec 2010 acquired 885 customers (20.4% of the base) yet produced **50.7% of customer-attributed revenue** (£4,502,009.52). Its repeat rate (87.5%) is the highest of any cohort and its customers buy ~9.4 times on average over 5.4 active months. Early customers became the highest-value customers.

2. **Retention is front-loaded, then plateaus.** Weighted retention falls from 100% (M0) to 22.7% at M1 and 23.7% at M2, but then holds between ~25.6% and 30.3% from months 3–10 instead of decaying to zero. A customer who makes it past the first two months is roughly twice as likely to keep coming back — the win moment is the second purchase, and it happens within ~2 months of acquisition.

3. **November is the retention lever.** Retention climbs through the autumn and peaks at M11 (weighted 37.9%) — the Dec 2010 cohort rebounds to 50.3% at M11 (November 2011). Seasonal re-engagement (gift season) is the single most reliable driver of reactivation in the data.

4. **Recent cohorts under-perform their predecessors.** Cohorts acquired from autumn 2011 are larger (2011-09: 299, 2011-10: 358, 2011-11: 324) but return less: 2011-11 has M1 retention of 11.1% and a repeat rate of 26.2% vs 36.6% / 87.5% for the founding cohort. Either acquisition quality is falling, or retention payoff takes months to accrue — both argue for tracking these cohorts through 2012 before concluding.

5. **Revenue concentration per cohort is steep.** Across all cohorts the acquisition month M0 contributes 25.3% of total lifetime revenue, and the average revenue per customer ranges from £5,087 (2010-12) down to £464 (2011-12). Retention marketing should prioritise the top-decile spenders in each cohort, whose repeat purchases dominate the cohort's tail revenue.

## 7. Recommendations

- **Trigger on the second purchase.** The biggest retention risk is between M0 and M2; invest in a win-back/next-purchase offer within 60 days of the first order.
- **Exploit the November spike.** Plan re-engagement campaigns for Sep–Nov, when even lapsed cohorts (e.g. Dec 2010, 50.3% at M11) re-activate at peak rates.
- **Benchmark new cohorts against Dec 2010, not the average.** Later cohorts start weaker (22.7% weighted M1 vs 36.6% for the best cohort); treat the difference as a retention target to close, not a fixed ceiling.
- **Extend the window.** The dataset ends in partial Dec 2011; 13 cohorts exist but only the Dec 2010 cohort has a full 13-period history. Re-running `06_cohort_retention_analysis.sql` on later data will mature the young cohorts' retention curves.
