-- ============================================================================
--  Retail Analysis — PostgreSQL Schema
--  ============================================================================
--  Defines the single analytical table `retail_transactions` that backs every
--  SQL script in this folder. It represents the project's CLEAN analytical
--  dataset: the exact dataframe the notebook exports to
--  `data/cleaned_retail_data.csv` (cancellations removed, duplicates dropped,
--  TotalPrice already calculated) — no second, independent cleaning step.
--
--  Notes on business logic (preserved from the notebook):
--    * Cancelled invoices (InvoiceNo starting with "C") are already excluded
--      from the source data, so none should appear here.
--    * `quantity` may be negative and `unit_price` may be 0 / negative. These
--      are genuine adjustment / return rows in the source and are intentionally
--      kept so that SQL totals match the Excel analysis exactly.
--    * `customer_id` is NULL for anonymous rows; those rows are retained in the
--      transactions table (only customer-level analysis filters them out).
--    * `invoice_date` is reconstructed from the notebook's "%y/%m/%d %H:%M:%S"
--      string columns using the same explicit format used by the RFM layer, so
--      time intelligence is calculated on true calendar dates.
-- ============================================================================

CREATE TABLE IF NOT EXISTS retail_transactions (
    transaction_id   BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    invoice_no       VARCHAR(20)     NOT NULL,
    stock_code       VARCHAR(20)     NOT NULL,
    description      TEXT,
    quantity         INTEGER         NOT NULL,
    invoice_date     TIMESTAMP       NOT NULL,
    unit_price       NUMERIC(12,2)   NOT NULL,
    customer_id      BIGINT,
    country          VARCHAR(100)    NOT NULL,
    total_price      NUMERIC(12,2)   NOT NULL
);

COMMENT ON TABLE  retail_transactions IS 'Cleaned online retail transaction lines (source: OnlineRetail cleaning.ipynb -> data/cleaned_retail_data.csv). Cancellations already removed upstream.';
COMMENT ON COLUMN retail_transactions.transaction_id IS 'Surrogate primary key; the source dataset has no natural unique key per line.';
COMMENT ON COLUMN retail_transactions.invoice_no   IS 'Invoice identifier (string; a small number are non-numeric, e.g. "A563185").';
COMMENT ON COLUMN retail_transactions.stock_code   IS 'Product stock code.';
COMMENT ON COLUMN retail_transactions.description  IS 'Product description; NULL for rows with no description in the source.';
COMMENT ON COLUMN retail_transactions.quantity     IS 'Units ordered; may be negative for adjustment/return lines.';
COMMENT ON COLUMN retail_transactions.invoice_date IS 'Timestamp reconstructed from the notebook string columns (%y/%m/%d + %H:%M:%S).';
COMMENT ON COLUMN retail_transactions.unit_price   IS 'Unit price; may be 0 or negative for adjustment lines.';
COMMENT ON COLUMN retail_transactions.customer_id  IS 'Customer identifier; NULL for anonymous rows.';
COMMENT ON COLUMN retail_transactions.country      IS 'Customer country (title-cased upstream).';
COMMENT ON COLUMN retail_transactions.total_price  IS 'Line total = quantity * unit_price, as computed by the notebook.';

-- ============================================================================
--  Indexes
--  ============================================================================
--  Each index backs the most common analytical access pattern in the SQL layer.
--  Justification (no speculative indexes):
--    * invoice_no      -> order counting / order-level aggregations (DISTINCT invoice_no).
--    * customer_id     -> customer analytics (top customers, RFM, lifetime value).
--    * invoice_date    -> all time-intelligence queries (monthly / yearly / MoM).
--    * stock_code      -> product analytics (revenue / quantity / ranking).
--    * country         -> geographic analytics (revenue, orders, AOV by country).
--    * (customer_id, invoice_date) -> per-customer purchase history scans used by RFM
--      (first/last purchase date, recency) without touching every row of the table.
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_retail_invoice_no    ON retail_transactions (invoice_no);
CREATE INDEX IF NOT EXISTS idx_retail_customer_id   ON retail_transactions (customer_id);
CREATE INDEX IF NOT EXISTS idx_retail_invoice_date  ON retail_transactions (invoice_date);
CREATE INDEX IF NOT EXISTS idx_retail_stock_code    ON retail_transactions (stock_code);
CREATE INDEX IF NOT EXISTS idx_retail_country       ON retail_transactions (country);
CREATE INDEX IF NOT EXISTS idx_retail_customer_date ON retail_transactions (customer_id, invoice_date);
