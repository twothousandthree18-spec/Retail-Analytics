-- ============================================================================
--  02_customer_analysis.sql — Customer Analytics
--  ============================================================================
--  Customer-level behaviour: value, order frequency, repeat purchasing,
--  average spend and the first/last purchase lifecycle. Anonymous rows
--  (customer_id IS NULL) are excluded from customer analysis.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 10. Top customers by revenue (top 20)
-- ----------------------------------------------------------------------------
SELECT customer_id,
       COUNT(DISTINCT invoice_no) AS orders,
       ROUND(SUM(total_price), 2) AS lifetime_revenue
FROM retail_transactions
WHERE customer_id IS NOT NULL
GROUP BY customer_id
ORDER BY lifetime_revenue DESC
LIMIT 20;

-- ----------------------------------------------------------------------------
-- 11. Customer order frequency — distribution by number of orders
-- ----------------------------------------------------------------------------
WITH customer_orders AS (
    SELECT customer_id,
           COUNT(DISTINCT invoice_no) AS orders
    FROM retail_transactions
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
)
SELECT CASE
           WHEN orders = 1                    THEN '1 order'
           WHEN orders = 2                    THEN '2 orders'
           WHEN orders BETWEEN 3 AND 5        THEN '3-5 orders'
           WHEN orders BETWEEN 6 AND 10       THEN '6-10 orders'
           WHEN orders > 10                   THEN '> 10 orders'
       END                                     AS order_frequency_band,
       COUNT(*)                               AS customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS share_pct
FROM customer_orders
GROUP BY 1
ORDER BY MIN(orders);

-- ----------------------------------------------------------------------------
-- 12. Repeat vs one-time customers (share of customer base)
-- ----------------------------------------------------------------------------
WITH customer_orders AS (
    SELECT customer_id,
           COUNT(DISTINCT invoice_no) AS orders
    FROM retail_transactions
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
)
SELECT CASE WHEN orders > 1 THEN 'Repeat' ELSE 'One-time' END AS customer_type,
       COUNT(*)                                              AS customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)    AS share_pct
FROM customer_orders
GROUP BY 1;

-- ----------------------------------------------------------------------------
-- 13. Average customer spend (mean lifetime revenue per customer)
-- ----------------------------------------------------------------------------
WITH customer_spend AS (
    SELECT customer_id,
           SUM(total_price) AS lifetime_revenue
    FROM retail_transactions
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
)
SELECT ROUND(AVG(lifetime_revenue), 2) AS average_customer_spend,
       COUNT(*)                       AS total_customers
FROM customer_spend;

-- ----------------------------------------------------------------------------
-- 14. First purchase date per customer (top 20 by lifetime revenue)
-- ----------------------------------------------------------------------------
SELECT customer_id,
       MIN(invoice_date)::date AS first_purchase_date,
       ROUND(SUM(total_price), 2) AS lifetime_revenue
FROM retail_transactions
WHERE customer_id IS NOT NULL
GROUP BY customer_id
ORDER BY lifetime_revenue DESC
LIMIT 20;

-- ----------------------------------------------------------------------------
-- 15. Last purchase date per customer (top 20 by lifetime revenue)
-- ----------------------------------------------------------------------------
SELECT customer_id,
       MAX(invoice_date)::date AS last_purchase_date,
       ROUND(SUM(total_price), 2) AS lifetime_revenue
FROM retail_transactions
WHERE customer_id IS NOT NULL
GROUP BY customer_id
ORDER BY lifetime_revenue DESC
LIMIT 20;

-- ----------------------------------------------------------------------------
-- 16. Customer lifetime revenue — full profile per customer
--     (first/last purchase, order count, days active, lifetime revenue)
-- ----------------------------------------------------------------------------
SELECT customer_id,
       MIN(invoice_date)::date                                    AS first_purchase_date,
       MAX(invoice_date)::date                                    AS last_purchase_date,
       (MAX(invoice_date)::date - MIN(invoice_date)::date)         AS days_between_first_last,
       COUNT(DISTINCT invoice_no)                                 AS orders,
       ROUND(SUM(total_price), 2)                                 AS lifetime_revenue
FROM retail_transactions
WHERE customer_id IS NOT NULL
GROUP BY customer_id
ORDER BY lifetime_revenue DESC;
