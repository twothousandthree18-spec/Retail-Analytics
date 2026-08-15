-- ============================================================================
--  04_time_analysis.sql — Time Intelligence
--  ============================================================================
--  Time-based analysis on TRUE calendar dates (invoice_date is reconstructed
--  from the notebook's "%y/%m/%d %H:%M:%S" strings with an explicit format).
--  Includes month-over-month change, growth %, cumulative revenue, monthly
--  contribution to annual revenue, and weekday/hourly demand patterns.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Monthly revenue with MoM change, growth % and running cumulative revenue
-- (LAG() + SUM() OVER) — 13 months of trading (Dec 2010 - Dec 2011).
-- ----------------------------------------------------------------------------
WITH monthly AS (
    SELECT DATE_TRUNC('month', invoice_date) AS month,
           SUM(total_price)                  AS revenue
    FROM retail_transactions
    GROUP BY 1
)
SELECT TO_CHAR(month, 'YYYY-MM')                                                                      AS month,
       ROUND(revenue, 2)                                                                              AS revenue,
       ROUND(LAG(revenue) OVER (ORDER BY month), 2)                                                   AS prev_month_revenue,
       ROUND(revenue - LAG(revenue) OVER (ORDER BY month), 2)                                         AS month_over_month_change,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
             / NULLIF(LAG(revenue) OVER (ORDER BY month), 0), 2)                                      AS mom_growth_pct,
       ROUND(SUM(revenue) OVER (ORDER BY month
             ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2)                                    AS cumulative_revenue
FROM monthly
ORDER BY month;

-- ----------------------------------------------------------------------------
-- Yearly revenue with year-over-year growth
-- ----------------------------------------------------------------------------
WITH yearly AS (
    SELECT EXTRACT(YEAR FROM invoice_date)::int AS year,
           SUM(total_price)                     AS revenue
    FROM retail_transactions
    GROUP BY 1
)
SELECT year,
       ROUND(revenue, 2) AS revenue,
       ROUND(LAG(revenue) OVER (ORDER BY year), 2) AS prev_year_revenue,
       ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY year))
             / NULLIF(LAG(revenue) OVER (ORDER BY year), 0), 2) AS yoy_growth_pct
FROM yearly
ORDER BY year;

-- ----------------------------------------------------------------------------
-- Monthly contribution to annual revenue (share of each year's total)
-- ----------------------------------------------------------------------------
WITH year_month AS (
    SELECT EXTRACT(YEAR  FROM invoice_date)::int AS year,
           EXTRACT(MONTH FROM invoice_date)::int AS month,
           SUM(total_price)                      AS revenue
    FROM retail_transactions
    GROUP BY 1, 2
)
SELECT year,
       month,
       ROUND(revenue, 2) AS revenue,
       ROUND(100.0 * revenue / SUM(revenue) OVER (PARTITION BY year), 2) AS pct_of_year
FROM year_month
ORDER BY year, month;

-- ----------------------------------------------------------------------------
-- Weekday demand: revenue and orders by day of week (ISO: 1 = Monday)
-- ----------------------------------------------------------------------------
SELECT EXTRACT(ISODOW FROM invoice_date)::int         AS dow,
       TO_CHAR(invoice_date, 'Day')                   AS weekday,
       COUNT(DISTINCT invoice_no)                     AS orders,
       ROUND(SUM(total_price), 2)                     AS revenue,
       ROUND(100.0 * SUM(total_price) / SUM(SUM(total_price)) OVER (), 2) AS revenue_share_pct
FROM retail_transactions
GROUP BY 1, TO_CHAR(invoice_date, 'Day')
ORDER BY 1;

-- ----------------------------------------------------------------------------
-- Hourly demand: revenue and transactions by hour of day
-- ----------------------------------------------------------------------------
SELECT EXTRACT(HOUR FROM invoice_date)::int AS hour,
       COUNT(*)                             AS transactions,
       COUNT(DISTINCT invoice_no)           AS orders,
       ROUND(SUM(total_price), 2)           AS revenue
FROM retail_transactions
GROUP BY 1
ORDER BY 1;
