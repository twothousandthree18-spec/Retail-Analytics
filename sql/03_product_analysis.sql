-- ============================================================================
--  03_product_analysis.sql — Product Analytics
--  ============================================================================
--  Product-level performance: revenue, volume, revenue-per-unit efficiency,
--  revenue contribution, and ranking within groups. Products are keyed by
--  `stock_code` (the stable product identifier); `description` is shown as a
--  human-readable label via MAX().
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 17. Top products by revenue (top 20)
-- ----------------------------------------------------------------------------
SELECT stock_code,
       MAX(description)      AS product,
       ROUND(SUM(total_price), 2) AS revenue
FROM retail_transactions
GROUP BY stock_code
ORDER BY revenue DESC
LIMIT 20;

-- ----------------------------------------------------------------------------
-- 18. Top products by quantity sold (top 20)
-- ----------------------------------------------------------------------------
SELECT stock_code,
       MAX(description)   AS product,
       SUM(quantity)      AS units_sold,
       ROUND(SUM(total_price), 2) AS revenue
FROM retail_transactions
GROUP BY stock_code
ORDER BY units_sold DESC
LIMIT 20;

-- ----------------------------------------------------------------------------
-- 19. High quantity but relatively low revenue
--     Products that sell above-median units but generate below-median revenue.
--     Business meaning: volume leaders that may be priced too low, candidates
--     for price testing / margin review.
-- ----------------------------------------------------------------------------
WITH product_stats AS (
    SELECT stock_code,
           MAX(description)    AS product,
           SUM(quantity)       AS units,
           SUM(total_price)    AS revenue
    FROM retail_transactions
    GROUP BY stock_code
),
medians AS (
    SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY units)   AS median_units,
           PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY revenue) AS median_revenue
    FROM product_stats
)
SELECT p.stock_code,
       p.product,
       p.units,
       ROUND(p.revenue, 2) AS revenue,
       ROUND(p.revenue / NULLIF(p.units, 0), 4) AS revenue_per_unit
FROM product_stats p
CROSS JOIN medians m
WHERE p.units > m.median_units
  AND p.revenue < m.median_revenue
ORDER BY p.units DESC;

-- ----------------------------------------------------------------------------
-- 20. Product revenue contribution — top 20 with share & cumulative share
-- ----------------------------------------------------------------------------
WITH product_revenue AS (
    SELECT stock_code,
           MAX(description) AS product,
           SUM(total_price) AS revenue
    FROM retail_transactions
    GROUP BY stock_code
),
product_share AS (
    SELECT stock_code,
           product,
           revenue,
           ROUND(100.0 * revenue / SUM(revenue) OVER (), 2) AS share_pct
    FROM product_revenue
)
SELECT ROW_NUMBER() OVER (ORDER BY revenue DESC) AS rank,
       stock_code,
       product,
       ROUND(revenue, 2) AS revenue,
       share_pct,
       ROUND(SUM(share_pct) OVER (
           ORDER BY revenue DESC
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW), 2) AS cumulative_share_pct
FROM product_share
ORDER BY rank
LIMIT 20;

-- ----------------------------------------------------------------------------
-- 21. Product ranking within relevant groups — top product per country
--     Uses ROW_NUMBER() partitioned by country and ordered by revenue.
-- ----------------------------------------------------------------------------
WITH country_product AS (
    SELECT country,
           stock_code,
           MAX(description) AS product,
           SUM(total_price) AS revenue
    FROM retail_transactions
    GROUP BY country, stock_code
),
ranked AS (
    SELECT country,
           stock_code,
           product,
           revenue,
           ROW_NUMBER() OVER (PARTITION BY country ORDER BY revenue DESC) AS rn
    FROM country_product
)
SELECT country,
       stock_code,
       product,
       ROUND(revenue, 2) AS revenue
FROM ranked
WHERE rn = 1
ORDER BY revenue DESC
LIMIT 20;
