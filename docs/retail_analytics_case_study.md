# Retail Analytics Case Study

> **Title:** End-to-End Retail Analytics & Customer Intelligence Platform
> **Dataset:** UCI Online Retail — 541,909 raw transaction lines (Dec 2010 – Dec 2011)
> **Technologies:** Python 3, Pandas, NumPy, PostgreSQL, SQL, Power BI, Excel,
> scikit-learn, FastAPI, Streamlit, GitHub Actions
> **Status:** Complete, fully validated (every metric reconciled across engines)

---

## Problem

A UK-based online gift retailer holds a year of transaction data but has no
systematic view of **who its customers are**, **how they behave over time**, and
**which of them are about to leave**. Business questions pile up:

1. What are the real KPIs — revenue, orders, customers, average order value?
2. Who are the most valuable customers (RFM), and how do cohorts evolve?
3. **Which customers are at risk of churning in the next 3 months?**

Without a single source of truth, different analysts would give different
answers. The project's central requirement: **every answer must be verifiable**.

## Approach

### Principle: independent cross-validation
Each layer re-computes the analytics **from scratch** and the layers are forced
to agree:

- **Python/pandas** cleans the raw CSV (541,909 → 527,390 rows) with an
  explicit quality gate.
- **PostgreSQL/SQL** re-derives every KPI from the same cleaned file using CTEs,
  window functions and time intelligence.
- **Power BI** builds a star-schema model *on top of the validated SQL layer*
  (no re-cleaning, no fabricated figures).
- A reconciliation suite (`sql/verify_pipeline.py`, `sql/cohort_validation.py`,
  `powerbi/scripts/validate_pbi.py`) compares all three — RFM segments agree
  100% customer-by-customer; KPIs agree to the penny.

### Phase 6: churn prediction (the ML piece)
- **Target:** churns = purchased in the observation window, then bought nothing
  for the following 3 months.
- **Features (18):** recency, frequency, monetary, tenure, product breadth,
  purchase timing, inter-order gaps, recency-of-orders, country, cohort month.
- **Temporal validation (honest evaluation):** W1 (Dec 2010 – Aug 2011) is used
  for training + tuning; **W2 (Mar – Nov 2011) is held out entirely** and used
  only for final evaluation — a true out-of-time test that simulates deployment.
- **Models:** logistic, random forest, gradient boosting + a "predict the
  majority" DummyClassifier baseline. Tuning on W1 only, with a **recall guard**
  (recall within 5pp of the best-tuned model) so the final choice doesn't just
  chase ROC-AUC at the expense of catching churners.
- **Final model:** tuned Logistic Regression (C=0.1) — simple, stable,
  interpretable, and no worse than the heavy models.

### Phase 7: production & serving
- **Data-quality gate** in `pipeline/validators.py` (PASS/WARNING/FAIL) with a
  live Python-vs-PostgreSQL reconciliation report.
- **Interactive demo** (Streamlit) that scores a user-entered customer profile
  with the *actual* tuned model.
- **Prediction API** (FastAPI `POST /predict`) returning probability + risk band.
- **CI** (GitHub Actions) + deployment guide.

## Results (all verified)

| Metric | Value |
|---|---|
| Cleaned transactions | 527,390 |
| Customers (attributed) | 4,339 |
| Total revenue | £10,619,986.68 |
| Orders / AOV | 22,064 / £481.33 |
| Repeat customers | 2,845 (65.57%) |
| RFM segments (Python vs SQL) | 100% agreement (4,339/4,339) |
| Cohort retention tables (SQL vs pandas) | 12/12 PASS |
| Power BI dataset vs PostgreSQL | 24/24 checks PASS |
| **Churn model — W2 ROC-AUC** | **0.7332** |
| **Churn model — W2 PR-AUC** | **0.5945** |
| **Churn model — W2 recall** | **0.7941** |
| **High-risk customers flagged (W2)** | **1,114 / 2,813 (39.6%)** |

### What the model tells us
Top drivers of predicted churn (association, not causation): low `active_months`,
few `distinct_products`, long `recency_days`, long average gap between orders
(`gap_mean_days`), low `total_quantity`. Interpretation: customers who bought
once or twice, months ago, from a narrow product set are the ones to target
with re-engagement offers.

## Business value
- **Single source of truth** — no more analyst disagreement.
- **Retention targeting** — 1,114 high-risk customers identified for outreach;
  at 79% recall the model finds most true churners before they leave.
- **Explainable** — coefficients let the business know *why* a customer is
  flagged, supporting (not dictating) campaign decisions.
- **Reproducible** — one command runs the entire chain: `pipeline/run_pipeline.py`.

## Limitations (stated honestly)
- Recall 79.4% means ~20% of true churners are missed; precision vs recall is a
  business trade-off (the API lets the threshold be tuned).
- Data is a single retailer, one year; model generalisation to other
  populations is untested.
- Cohort/retention analysis is descriptive, not causal.

## What I'd do with more time
- Deploy the API behind auth on a real cloud host with uptime monitoring.
- Add a scheduled retraining job + drift monitoring on the prediction
  distribution.
- Extend features (returns, customer support interactions, channel data).
