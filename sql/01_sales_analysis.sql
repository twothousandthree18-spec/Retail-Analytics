-- ============================================================================
--  01_sales_analysis.sql — Sales Analytics
--  ============================================================================
--  Core business-level KPIs over the cleaned `retail_transactions` table.
--  All totals are computed from the same cleaned dataset used by the Excel
--  report, so they are directly comparable to the workbook's Summary Dashboard.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Total revenue
-- ----------------------------------------------------------------------------
SELECT ROUND(SUM(total_price), 2) AS total_revenue
FROM retail_transactions;

-- ----------------------------------------------------------------------------
-- 2. Total orders (distinct invoices)
-- ----------------------------------------------------------------------------
SELECT COUNT(DISTINCT invoice_no) AS total_orders
FROM retail_transactions;

-- ----------------------------------------------------------------------------
-- 3. Total units sold
--    Quantity is summed as-is (adjustment/return lines are included, matching
--    the notebook's business logic).
-- ----------------------------------------------------------------------------
SELECT SUM(quantity) AS total_units_sold
FROM retail_transactions;

-- ----------------------------------------------------------------------------
-- 4. Average Order Value (AOV) = revenue / distinct invoices
-- ----------------------------------------------------------------------------
SELECT ROUND(SUM(total_price) / COUNT(DISTINCT invoice_no), 2) AS average_order_value
FROM retail_transactions;

-- ----------------------------------------------------------------------------
-- 5. Revenue by country (with share of total revenue)
-- ----------------------------------------------------------------------------
SELECT country,
       ROUND(SUM(total_price), 2)                                       AS revenue,
       ROUND(100.0 * SUM(total_price) / SUM(SUM(total_price)) OVER (), 2) AS share_pct
FROM retail_transactions
GROUP BY country
ORDER BY revenue DESC;

-- ----------------------------------------------------------------------------
-- 6. Revenue by product (top 20 by stock_code; description shown as label)
-- ----------------------------------------------------------------------------
SELECT stock_code,
       MAX(description)                      AS product,
       COUNT(DISTINCT invoice_no)            AS orders,
       ROUND(SUM(total_price), 2)            AS revenue
FROM retail_transactions
GROUP BY stock_code
ORDER BY revenue DESC
LIMIT 20;

-- ----------------------------------------------------------------------------
-- 7. Monthly revenue & orders (true calendar months)
-- ----------------------------------------------------------------------------
SELECT TO_CHAR(DATE_TRUNC('month', invoice_date), 'YYYY-MM') AS month,
       COUNT(DISTINCT invoice_no)                            AS orders,
       ROUND(SUM(total_price), 2)                            AS revenue
FROM retail_transactions
GROUP BY 1
ORDER BY 1;

-- ----------------------------------------------------------------------------
-- 8. Yearly revenue & orders
-- ----------------------------------------------------------------------------
SELECT EXTRACT(YEAR FROM invoice_date)::int AS year,
       COUNT(DISTINCT invoice_no)           AS orders,
       ROUND(SUM(total_price), 2)           AS revenue
FROM retail_transactions
GROUP BY 1
ORDER BY 1;

-- ----------------------------------------------------------------------------
-- 9. Revenue contribution / concentration — top 10 countries
--    Shows each country's share and the running cumulative share, which
--    quantifies how concentrated revenue is geographically.
-- ----------------------------------------------------------------------------
WITH country_revenue AS (
    SELECT country,
           SUM(total_price) AS revenue
    FROM retail_transactions
    GROUP BY country
),
country_share AS (
    SELECT country,
           revenue,
           ROUND(100.0 * revenue / SUM(revenue) OVER (), 2) AS share_pct
    FROM country_revenue
)
SELECT ROW_NUMBER() OVER (ORDER BY revenue DESC)              AS rank,
       country,
       ROUND(revenue, 2)                                     AS revenue,
       share_pct,
       ROUND(SUM(share_pct) OVER (
           ORDER BY revenue DESC
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cumulative_share_pct
FROM country_share
ORDER BY rank
LIMIT 10;
