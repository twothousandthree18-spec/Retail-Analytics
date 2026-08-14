-- ============================================================================
--  06_cohort_retention_analysis.sql — Cohort & Customer Retention Analysis
--  ============================================================================
--  Phase 4 additive capability. Answers the question:
--      "When customers first purchase, how well do we retain them and bring
--       them back for future purchases?"
--
--  Methodology (business rules)
--    * Cohort        = the calendar month of a customer's FIRST purchase.
--    * PurchaseMonth = the calendar month of each individual purchase.
--    * CohortIndex   = number of months between CohortMonth and PurchaseMonth.
--                      0 = acquisition month, 1 = first month after, ...
--    * CUSTOMER RETENTION = customers active in month N
--                           ÷ customers acquired in the cohort
--      (denominator is CUSTOMERS, never revenue).
--    * REVENUE RETENTION  = revenue earned in month N (separate, clearly
--      distinguished from customer retention).
--
--  Data rules
--    * Anonymous rows (customer_id IS NULL) are excluded — they cannot be
--      assigned to a cohort.
--    * The observation window ends 2011-12. A cohort acquired in month X only
--      has valid data up to cohort index (X -> 2011-12). Months beyond the
--      window are left BLANK (NULL), never shown as a false 0%.
--    * One customer belongs to exactly one cohort (their first purchase month).
--
--  Techniques on show
--    * Staged temp tables (as in 05) for readable, reusable queries
--    * CTEs, DATE_TRUNC month arithmetic, generate_series grids
--    * Window functions (running totals / cumulative revenue)
--    * Conditional aggregation pivots (FILTER / CASE WHEN)
--  ============================================================================

-- ============================================================================
--  BUILD BLOCK — temp tables reused by every query below
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Customer cohort assignment: CustomerID -> FirstPurchaseDate -> CohortMonth.
-- The cohort is the FIRST purchase month — never the last activity.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS cohort_customers;
CREATE TEMP TABLE cohort_customers AS
SELECT customer_id,
       MIN(invoice_date)::date AS first_purchase_date,
       DATE_TRUNC('month', MIN(invoice_date))::date AS cohort_month
FROM retail_transactions
WHERE customer_id IS NOT NULL
GROUP BY customer_id;

-- ----------------------------------------------------------------------------
-- Per-purchase activity: every transaction of every attributed customer, tagged
-- with PurchaseMonth and CohortIndex (months since their cohort month).
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS cohort_activity;
CREATE TEMP TABLE cohort_activity AS
SELECT a.customer_id,
       a.cohort_month,
       TO_CHAR(DATE_TRUNC('month', t.invoice_date), 'YYYY-MM') AS purchase_month,
       ((EXTRACT(YEAR FROM DATE_TRUNC('month', t.invoice_date)) * 12
           + EXTRACT(MONTH FROM DATE_TRUNC('month', t.invoice_date)))
        - (EXTRACT(YEAR FROM a.cohort_month) * 12
           + EXTRACT(MONTH FROM a.cohort_month)))::int              AS cohort_index,
       t.invoice_date,
       t.invoice_no,
       t.total_price
FROM cohort_customers a
JOIN retail_transactions t USING (customer_id);

-- ----------------------------------------------------------------------------
-- Availability grid: every (cohort, index) pair that could possibly hold data,
-- i.e. index 0..(months from the cohort month to the end of the window).
-- Months beyond the window are NOT in the grid -> they stay blank, not 0%.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS cohort_avail;
CREATE TEMP TABLE cohort_avail AS
WITH sizes AS (
    SELECT cohort_month, COUNT(*) AS size
    FROM cohort_customers
    GROUP BY cohort_month
)
SELECT s.cohort_month,
       s.size,
       x.cohort_index
FROM sizes s,
     LATERAL (
         SELECT generate_series(
                    0,
                    (EXTRACT(YEAR FROM DATE '2011-12-01') * 12
                       + EXTRACT(MONTH FROM DATE '2011-12-01'))
                  - (EXTRACT(YEAR FROM s.cohort_month) * 12
                       + EXTRACT(MONTH FROM s.cohort_month))
             )::int AS cohort_index
     ) x;

-- ----------------------------------------------------------------------------
-- Normalized retention matrix (long form) — the single source for the pivots.
-- One row per (cohort, cohort_index) that is INSIDE the observation window.
-- Genuine 0s (customers existed but none returned that month) are kept as 0.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS cohort_matrix;
CREATE TEMP TABLE cohort_matrix AS
WITH activity_counts AS (
    SELECT cohort_month,
           cohort_index,
           COUNT(DISTINCT customer_id) AS active_customers,
           ROUND(SUM(total_price), 2)  AS revenue
    FROM cohort_activity
    GROUP BY cohort_month, cohort_index
)
SELECT a.cohort_month,
       a.cohort_index,
       a.size                                   AS cohort_size,
       COALESCE(c.active_customers, 0)          AS active_customers,
       ROUND(100.0 * COALESCE(c.active_customers, 0) / a.size, 2) AS retention_pct,
       COALESCE(c.revenue, 0)                   AS revenue
FROM cohort_avail a
LEFT JOIN activity_counts c USING (cohort_month, cohort_index)
ORDER BY a.cohort_month, a.cohort_index;

-- ============================================================================
--  QUERIES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Customer cohort assignment (CustomerID, FirstPurchaseDate, CohortMonth).
-- ----------------------------------------------------------------------------
SELECT customer_id,
       first_purchase_date,
       TO_CHAR(cohort_month, 'YYYY-MM') AS cohort_month
FROM cohort_customers
ORDER BY customer_id;

-- ----------------------------------------------------------------------------
-- 2. Cohort sizes — the acquisition base for every retention calculation.
-- ----------------------------------------------------------------------------
SELECT TO_CHAR(cohort_month, 'YYYY-MM') AS cohort_month,
       COUNT(*)                          AS cohort_size
FROM cohort_customers
GROUP BY cohort_month
ORDER BY cohort_month;

-- ----------------------------------------------------------------------------
-- 3. Purchase month + cohort index per customer transaction (sample, top 20
--    customers by revenue for readability; the full table lives in the temp).
-- ----------------------------------------------------------------------------
SELECT customer_id,
       purchase_month,
       cohort_index,
       TO_CHAR(invoice_date, 'YYYY-MM-DD') AS invoice_date
FROM cohort_activity
WHERE customer_id IN (
    SELECT customer_id FROM cohort_customers ORDER BY first_purchase_date, customer_id LIMIT 20
)
ORDER BY customer_id, cohort_index;

-- ----------------------------------------------------------------------------
-- 4. Sanity: max cohort index per cohort == months to the end of the window;
--    proves no cohort claims months beyond the available data.
-- ----------------------------------------------------------------------------
SELECT TO_CHAR(cohort_month, 'YYYY-MM')  AS cohort_month,
       COUNT(*)                          AS cohort_size,
       MAX(cohort_index)                 AS max_index_in_grid,
       (EXTRACT(YEAR FROM DATE '2011-12-01') * 12
          + EXTRACT(MONTH FROM DATE '2011-12-01'))
        - (EXTRACT(YEAR FROM cohort_month) * 12
           + EXTRACT(MONTH FROM cohort_month))::int AS months_available
FROM cohort_avail
GROUP BY cohort_month
ORDER BY cohort_month;

-- ----------------------------------------------------------------------------
-- 5. Retention matrix, NORMALIZED long form (customers + %), the canonical
--    output used by the Power BI / Excel / Python layers.
-- ----------------------------------------------------------------------------
SELECT TO_CHAR(cohort_month, 'YYYY-MM') AS cohort_month,
       cohort_index,
       cohort_size,
       active_customers,
       retention_pct,
       revenue
FROM cohort_matrix
ORDER BY cohort_month, cohort_index;

-- ----------------------------------------------------------------------------
-- 6. Customer retention matrix — PIVOTED PERCENTAGES (M0..M12).
--    Rows = cohort month, columns = months since acquisition.
--    M0 is always 100.0% (the acquisition month itself). Months beyond the
--    observation window are blank, not 0%.
-- ----------------------------------------------------------------------------
SELECT TO_CHAR(cohort_month, 'YYYY-MM') AS cohort_month,
       MAX(cohort_size)                 AS cohort_size,
       MAX(CASE WHEN cohort_index = 0  THEN retention_pct END) AS m0,
       MAX(CASE WHEN cohort_index = 1  THEN retention_pct END) AS m1,
       MAX(CASE WHEN cohort_index = 2  THEN retention_pct END) AS m2,
       MAX(CASE WHEN cohort_index = 3  THEN retention_pct END) AS m3,
       MAX(CASE WHEN cohort_index = 4  THEN retention_pct END) AS m4,
       MAX(CASE WHEN cohort_index = 5  THEN retention_pct END) AS m5,
       MAX(CASE WHEN cohort_index = 6  THEN retention_pct END) AS m6,
       MAX(CASE WHEN cohort_index = 7  THEN retention_pct END) AS m7,
       MAX(CASE WHEN cohort_index = 8  THEN retention_pct END) AS m8,
       MAX(CASE WHEN cohort_index = 9  THEN retention_pct END) AS m9,
       MAX(CASE WHEN cohort_index = 10 THEN retention_pct END) AS m10,
       MAX(CASE WHEN cohort_index = 11 THEN retention_pct END) AS m11,
       MAX(CASE WHEN cohort_index = 12 THEN retention_pct END) AS m12
FROM cohort_matrix
GROUP BY cohort_month
ORDER BY cohort_month;

-- ----------------------------------------------------------------------------
-- 7. Retention matrix — PIVOTED ABSOLUTE CUSTOMER COUNTS (M0..M12).
--    Always alongside the percentages: absolute and relative views together.
-- ----------------------------------------------------------------------------
SELECT TO_CHAR(cohort_month, 'YYYY-MM') AS cohort_month,
       MAX(cohort_size)                 AS cohort_size,
       MAX(CASE WHEN cohort_index = 0  THEN active_customers END) AS m0,
       MAX(CASE WHEN cohort_index = 1  THEN active_customers END) AS m1,
       MAX(CASE WHEN cohort_index = 2  THEN active_customers END) AS m2,
       MAX(CASE WHEN cohort_index = 3  THEN active_customers END) AS m3,
       MAX(CASE WHEN cohort_index = 4  THEN active_customers END) AS m4,
       MAX(CASE WHEN cohort_index = 5  THEN active_customers END) AS m5,
       MAX(CASE WHEN cohort_index = 6  THEN active_customers END) AS m6,
       MAX(CASE WHEN cohort_index = 7  THEN active_customers END) AS m7,
       MAX(CASE WHEN cohort_index = 8  THEN active_customers END) AS m8,
       MAX(CASE WHEN cohort_index = 9  THEN active_customers END) AS m9,
       MAX(CASE WHEN cohort_index = 10 THEN active_customers END) AS m10,
       MAX(CASE WHEN cohort_index = 11 THEN active_customers END) AS m11,
       MAX(CASE WHEN cohort_index = 12 THEN active_customers END) AS m12
FROM cohort_matrix
GROUP BY cohort_month
ORDER BY cohort_month;

-- ----------------------------------------------------------------------------
-- 8. Cohort summary — acquisition + lifetime behaviour per cohort:
--    size, repeat behaviour, lifetime revenue, revenue per customer,
--    average orders and active months, average customer lifetime duration.
-- ----------------------------------------------------------------------------
WITH base AS (
    SELECT customer_id,
           cohort_month,
           COUNT(DISTINCT invoice_no) AS orders,
           ROUND(SUM(total_price), 2) AS revenue,
           MIN(invoice_date)::date    AS first_purchase_date,
           MAX(invoice_date)::date    AS last_purchase_date,
           COUNT(DISTINCT DATE_TRUNC('month', invoice_date)) AS active_months
    FROM cohort_activity
    GROUP BY customer_id, cohort_month
)
SELECT TO_CHAR(cohort_month, 'YYYY-MM')            AS cohort_month,
       COUNT(*)                                    AS cohort_size,
       COUNT(*) FILTER (WHERE orders > 1)          AS repeat_customers,
       COUNT(*) FILTER (WHERE orders = 1)          AS one_time_customers,
       ROUND(100.0 * COUNT(*) FILTER (WHERE orders > 1) / COUNT(*), 2) AS repeat_rate_pct,
       ROUND(SUM(revenue), 2)                      AS lifetime_revenue,
       ROUND(AVG(revenue), 2)                      AS revenue_per_customer,
       ROUND(AVG(orders), 2)                       AS avg_orders_per_customer,
       ROUND(AVG(active_months), 2)                AS avg_active_months,
       ROUND(AVG(last_purchase_date - first_purchase_date), 1) AS avg_lifetime_days
FROM base
GROUP BY cohort_month
ORDER BY cohort_month;

-- ----------------------------------------------------------------------------
-- 9. REVENUE RETENTION — revenue by cohort age + cumulative revenue per cohort.
--    This is revenue retention, deliberately distinct from customer retention:
--    a cohort can retain few customers while keeping a large share of revenue.
-- ----------------------------------------------------------------------------
SELECT TO_CHAR(cohort_month, 'YYYY-MM') AS cohort_month,
       cohort_index,
       cohort_size,
       revenue,
       ROUND(revenue / NULLIF(cohort_size, 0), 2)   AS revenue_per_customer,
       SUM(revenue) OVER (PARTITION BY cohort_month
           ORDER BY cohort_index
           ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cumulative_revenue,
       ROUND(100.0 * revenue / NULLIF(
           SUM(revenue) OVER (PARTITION BY cohort_month), 0), 2) AS revenue_share_pct
FROM cohort_matrix
ORDER BY cohort_month, cohort_index;

-- ----------------------------------------------------------------------------
-- 10. Revenue retention matrix — PIVOTED (revenue by cohort age, M0..M12).
-- ----------------------------------------------------------------------------
SELECT TO_CHAR(cohort_month, 'YYYY-MM') AS cohort_month,
       MAX(cohort_size)                 AS cohort_size,
       MAX(CASE WHEN cohort_index = 0  THEN revenue END) AS m0,
       MAX(CASE WHEN cohort_index = 1  THEN revenue END) AS m1,
       MAX(CASE WHEN cohort_index = 2  THEN revenue END) AS m2,
       MAX(CASE WHEN cohort_index = 3  THEN revenue END) AS m3,
       MAX(CASE WHEN cohort_index = 4  THEN revenue END) AS m4,
       MAX(CASE WHEN cohort_index = 5  THEN revenue END) AS m5,
       MAX(CASE WHEN cohort_index = 6  THEN revenue END) AS m6,
       MAX(CASE WHEN cohort_index = 7  THEN revenue END) AS m7,
       MAX(CASE WHEN cohort_index = 8  THEN revenue END) AS m8,
       MAX(CASE WHEN cohort_index = 9  THEN revenue END) AS m9,
       MAX(CASE WHEN cohort_index = 10 THEN revenue END) AS m10,
       MAX(CASE WHEN cohort_index = 11 THEN revenue END) AS m11,
       MAX(CASE WHEN cohort_index = 12 THEN revenue END) AS m12
FROM cohort_matrix
GROUP BY cohort_month
ORDER BY cohort_month;

-- ----------------------------------------------------------------------------
-- 11. Overall customer lifecycle metrics (whole attributed base).
--     avg_days_between_purchases is defined for repeat customers only:
--     (last - first) ÷ (orders - 1); one-time customers contribute no interval.
-- ----------------------------------------------------------------------------
WITH base AS (
    SELECT customer_id,
           COUNT(DISTINCT invoice_no) AS orders,
           MIN(invoice_date)::date    AS first_purchase_date,
           MAX(invoice_date)::date    AS last_purchase_date,
           COUNT(DISTINCT DATE_TRUNC('month', invoice_date)) AS active_months
    FROM cohort_activity
    GROUP BY customer_id
)
SELECT COUNT(*)                                    AS total_customers,
       COUNT(*) FILTER (WHERE orders > 1)          AS repeat_customers,
       COUNT(*) FILTER (WHERE orders = 1)          AS one_time_customers,
       ROUND(100.0 * COUNT(*) FILTER (WHERE orders > 1) / COUNT(*), 2) AS repeat_customer_rate_pct,
       ROUND(AVG(orders), 2)                       AS avg_orders_per_customer,
       ROUND(AVG(CASE WHEN orders > 1
                      THEN (last_purchase_date - first_purchase_date) / (orders - 1) END), 1)
                                                   AS avg_days_between_purchases,
       ROUND(AVG(active_months), 2)                AS avg_customer_active_months,
       ROUND(AVG(CASE WHEN orders > 1
                      THEN last_purchase_date - first_purchase_date END), 1)
                                                   AS avg_customer_lifetime_days,
       MIN(first_purchase_date)                    AS first_purchase_date_any,
       MAX(last_purchase_date)                     AS last_purchase_date_any
FROM base;

-- ----------------------------------------------------------------------------
-- 12. Retention decay by cohort — the M1 / M3 / M6 / M12 ladder shows how
--     quickly each cohort thins out and whether later cohorts retain better.
--     Cells beyond a cohort's window stay blank (no false zeros).
-- ----------------------------------------------------------------------------
SELECT TO_CHAR(cohort_month, 'YYYY-MM') AS cohort_month,
       MAX(cohort_size)                 AS cohort_size,
       MAX(CASE WHEN cohort_index = 1  THEN retention_pct END) AS m1_pct,
       MAX(CASE WHEN cohort_index = 3  THEN retention_pct END) AS m3_pct,
       MAX(CASE WHEN cohort_index = 6  THEN retention_pct END) AS m6_pct,
       MAX(CASE WHEN cohort_index = 12 THEN retention_pct END) AS m12_pct,
       MAX(CASE WHEN cohort_index = 1  THEN active_customers END) AS m1_customers,
       MAX(CASE WHEN cohort_index = 3  THEN active_customers END) AS m3_customers,
       MAX(CASE WHEN cohort_index = 6  THEN active_customers END) AS m6_customers,
       MAX(CASE WHEN cohort_index = 12 THEN active_customers END) AS m12_customers
FROM cohort_matrix
GROUP BY cohort_month
ORDER BY cohort_month;
