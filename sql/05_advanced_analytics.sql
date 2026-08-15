-- ============================================================================
--  05_advanced_analytics.sql — Advanced SQL Analytics
--  ============================================================================
--  Flagship file demonstrating intermediate/advanced PostgreSQL:
--    * Multiple CTEs for readable, staged queries
--    * Window functions: ROW_NUMBER(), RANK(), DENSE_RANK(), LAG(),
--      running totals via SUM() OVER (...), NTILE() for quartiles
--    * Time intelligence: month-over-month change, growth %, cumulative revenue
--    * Customer behaviour: first/last purchase, recency, frequency, lifetime value
--    * RFM segmentation that REPRODUCES the workbook's "RFM Customer Segmentation"
--      sheet (sheet 23) using the same cleaned data and the SAME segment rules —
--      this validates the Pandas/Excel result with an independent SQL engine.
--
--  RFM methodology (identical to the notebook):
--    * Recency   = days since the customer's last purchase (reference snapshot =
--                  the latest invoice date in the dataset).
--    * Frequency = distinct invoices placed by the customer.
--    * Monetary  = total spend across all the customer's orders.
--    * Quartile scores 1-4 (NTILE over 4 bins): R is INVERTED so the freshest
--      customers score 4; F and M score higher for more frequent/bigger spenders.
--    * Segment rules are evaluated top-down, first match wins (see CASE below).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Build the per-customer RFM table once, then reuse it across the file.
-- ----------------------------------------------------------------------------
DROP TABLE IF EXISTS customer_rfm;

CREATE TEMP TABLE customer_rfm AS
WITH base AS (
    -- Anonymous rows cannot be attributed to a customer and are excluded,
    -- exactly as in the notebook's RFM.
    SELECT customer_id, invoice_no, invoice_date, total_price
    FROM retail_transactions
    WHERE customer_id IS NOT NULL
),
reference AS (
    -- Same snapshot date convention as the Python RFM.
    SELECT MAX(invoice_date) AS snapshot FROM base
),
rfm AS (
    SELECT b.customer_id,
           (SELECT snapshot FROM reference)::date - MAX(b.invoice_date)::date
               AS recency_days,
           COUNT(DISTINCT b.invoice_no) AS frequency,
           ROUND(SUM(b.total_price), 2) AS monetary
    FROM base b
    GROUP BY b.customer_id
),
scored AS (
    SELECT customer_id,
           recency_days,
           frequency,
           monetary,
           -- Recency inverted: most recent quartile -> score 4.
           -- The explicit `customer_id` tie-breaker reproduces pandas
           -- rank(method="first") ordering so the quartile assignment matches
           -- the workbook's RFM sheet exactly (verified 100% segment match).
           5 - NTILE(4) OVER (ORDER BY recency_days ASC, customer_id ASC) AS r_score,
           -- Frequency: most frequent quartile -> score 4.
           NTILE(4) OVER (ORDER BY frequency ASC,   customer_id ASC)     AS f_score,
           -- Monetary: biggest spenders -> score 4.
           NTILE(4) OVER (ORDER BY monetary ASC,    customer_id ASC)     AS m_score
    FROM rfm
)
SELECT customer_id,
       recency_days,
       frequency,
       monetary,
       r_score,
       f_score,
       m_score,
       r_score + f_score + m_score AS rfm_score,
       CASE
           WHEN r_score >= 4 AND f_score >= 3 AND m_score >= 3 THEN 'Champions'
           WHEN r_score >= 3 AND f_score >= 3 AND m_score >= 3 THEN 'Loyal Customers'
           WHEN r_score >= 3 AND f_score >= 2 AND m_score >= 2 THEN 'Potential Loyalists'
           WHEN r_score >= 3 AND f_score = 1                  THEN 'New Customers'
           WHEN r_score <= 2 AND (f_score >= 3 OR m_score >= 3) THEN 'At Risk'
           WHEN r_score >= 2 AND (f_score >= 2 OR m_score >= 2) THEN 'Needs Attention'
           ELSE 'Hibernating'
       END AS segment
FROM scored;

-- Sanity check: one row per attributed customer (must equal the workbook's
-- RFM sheet row count, 4,339).
SELECT COUNT(*)                                AS rfm_customer_count,
       COUNT(DISTINCT customer_id)             AS distinct_customers
FROM customer_rfm;

-- ----------------------------------------------------------------------------
-- RFM segment distribution — must mirror the workbook's sheet 23.
-- ----------------------------------------------------------------------------
SELECT segment,
       COUNT(*)                                             AS customers,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2)   AS share_pct
FROM customer_rfm
GROUP BY segment
ORDER BY customers DESC;

-- ----------------------------------------------------------------------------
-- Segment profiles: average recency / frequency / monetary per segment
-- (shows the segments are behaviourally distinct).
-- ----------------------------------------------------------------------------
SELECT segment,
       COUNT(*)                       AS customers,
       ROUND(AVG(recency_days), 1)    AS avg_recency_days,
       ROUND(AVG(frequency), 2)       AS avg_frequency,
       ROUND(AVG(monetary), 2)        AS avg_monetary,
       ROUND(AVG(rfm_score), 2)       AS avg_rfm_score
FROM customer_rfm
GROUP BY segment
ORDER BY customers DESC;

-- ----------------------------------------------------------------------------
-- High-value customers becoming inactive (At Risk) — the workbook segment is
-- used here to directly answer: "Which customers are highly valuable but
-- becoming inactive?"
-- ----------------------------------------------------------------------------
SELECT customer_id,
       recency_days,
       frequency,
       ROUND(monetary, 2) AS lifetime_revenue
FROM customer_rfm
WHERE segment = 'At Risk'
ORDER BY monetary DESC
LIMIT 20;

-- ----------------------------------------------------------------------------
-- Top customers per country using ROW_NUMBER() OVER (PARTITION BY ...)
-- ----------------------------------------------------------------------------
WITH customer_country AS (
    SELECT customer_id,
           country,
           SUM(total_price) AS revenue
    FROM retail_transactions
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id, country
),
ranked AS (
    SELECT country,
           customer_id,
           revenue,
           ROW_NUMBER() OVER (PARTITION BY country ORDER BY revenue DESC) AS rn
    FROM customer_country
)
SELECT country,
       customer_id,
       ROUND(revenue, 2) AS revenue
FROM ranked
WHERE rn = 1
ORDER BY revenue DESC
LIMIT 20;

-- ----------------------------------------------------------------------------
-- Customer ranking by spending — RANK() vs DENSE_RANK() vs ROW_NUMBER()
-- (RANK leaves gaps after ties; DENSE_RANK does not; ROW_NUMBER never ties.)
-- ----------------------------------------------------------------------------
WITH spend AS (
    SELECT customer_id,
           ROUND(SUM(total_price), 2) AS revenue
    FROM retail_transactions
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
)
SELECT RANK()       OVER (ORDER BY revenue DESC) AS rank,
       DENSE_RANK() OVER (ORDER BY revenue DESC) AS dense_rank,
       ROW_NUMBER() OVER (ORDER BY revenue DESC) AS row_num,
       customer_id,
       revenue
FROM spend
ORDER BY revenue DESC, customer_id
LIMIT 20;

-- ----------------------------------------------------------------------------
-- Top products by revenue using RANK()
-- ----------------------------------------------------------------------------
WITH product_revenue AS (
    SELECT stock_code,
           SUM(total_price) AS revenue
    FROM retail_transactions
    GROUP BY stock_code
)
SELECT RANK() OVER (ORDER BY revenue DESC) AS rank,
       p.stock_code,
       (SELECT MAX(description) FROM retail_transactions t
        WHERE t.stock_code = p.stock_code) AS product,
       ROUND(p.revenue, 2)                 AS revenue
FROM product_revenue p
ORDER BY rank
LIMIT 20;

-- ----------------------------------------------------------------------------
-- Time intelligence: monthly revenue, previous month via LAG(), MoM growth %
-- and a running cumulative total via SUM() OVER (...)
-- ----------------------------------------------------------------------------
WITH monthly AS (
    SELECT DATE_TRUNC('month', invoice_date) AS month,
           SUM(total_price)                  AS revenue
    FROM retail_transactions
    GROUP BY 1
),
with_growth AS (
    SELECT month,
           revenue,
           LAG(revenue) OVER (ORDER BY month)                     AS prev_revenue,
           SUM(revenue) OVER (ORDER BY month
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)  AS cumulative_revenue
    FROM monthly
)
SELECT TO_CHAR(month, 'YYYY-MM') AS month,
       ROUND(revenue, 2)                                   AS revenue,
       ROUND(prev_revenue, 2)                              AS prev_month_revenue,
       ROUND(100.0 * (revenue - prev_revenue) / NULLIF(prev_revenue, 0), 2)
                                                           AS mom_growth_pct,
       ROUND(cumulative_revenue, 2)                        AS cumulative_revenue
FROM with_growth
ORDER BY month;

-- ----------------------------------------------------------------------------
-- Customer behaviour: full lifecycle per customer (first/last purchase,
-- recency in days, purchase frequency, lifetime revenue).
-- ----------------------------------------------------------------------------
WITH lifecycle AS (
    SELECT customer_id,
           MIN(invoice_date)::date          AS first_purchase_date,
           MAX(invoice_date)::date          AS last_purchase_date,
           COUNT(DISTINCT invoice_no)       AS frequency,
           SUM(total_price)                 AS monetary
    FROM retail_transactions
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
)
SELECT customer_id,
       first_purchase_date,
       last_purchase_date,
       (SELECT MAX(invoice_date)::date FROM retail_transactions) - last_purchase_date
           AS days_since_last_purchase,
       frequency,
       ROUND(monetary, 2) AS lifetime_revenue
FROM lifecycle
ORDER BY monetary DESC
LIMIT 20;

-- ----------------------------------------------------------------------------
-- Revenue concentration: how many customers are needed to reach 80% of total
-- revenue, and the share of revenue held by the top 10% of customers.
-- ----------------------------------------------------------------------------
WITH spend AS (
    SELECT customer_id,
           SUM(total_price) AS revenue
    FROM retail_transactions
    WHERE customer_id IS NOT NULL
    GROUP BY customer_id
),
ordered AS (
    SELECT revenue,
           SUM(revenue)  OVER (ORDER BY revenue DESC
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running,
           SUM(revenue)  OVER ()                                  AS total,
           ROW_NUMBER() OVER (ORDER BY revenue DESC)             AS rn
    FROM spend
)
SELECT (SELECT COUNT(*) FROM ordered)                                               AS total_customers,
       (SELECT MIN(rn) FROM ordered WHERE running >= 0.8 * total)                   AS customers_for_80pct_revenue,
       (SELECT ROUND(100.0 * running / total, 2) FROM ordered
        WHERE rn = (SELECT CEIL(COUNT(*) * 0.10)::int FROM ordered))                AS top10pct_customers_share_pct;
