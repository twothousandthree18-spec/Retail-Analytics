# Phase 6 Report — Predictive Analytics / Customer Churn (Machine Learning)

**Date:** 15 Aug 2026 · **Status:** COMPLETE — all validation checks PASS

**Final model (after Phase 6.1 tuning):** tuned Logistic Regression (C = 0.1).

## 1. Objective

Add a production-quality, customer-focused predictive layer on top of the
**already validated** analysis. The chosen problem is **customer churn
prediction**: identify which customers are likely to stop buying so the
business can intervene before they are lost. Everything is computed from real
artifacts — the same `data/cleaned_retail_data.csv` used by the Phase 4/5
pipeline. No fabricated labels, no invented figures, no leakage.

## 2. What was delivered

| Deliverable | Location | Status |
|-------------|----------|--------|
| Feature + target engineering (no-leakage windows) | `pipeline/ml_features.py` | validated |
| Model layer (baseline, 3 models, CV, temporal test) | `pipeline/ml_models.py` | validated |
| CLI runner (9 stages, manifest, exit codes) | `pipeline/run_ml.py` | run OK |
| Hyperparameter tuning runner (search + decision manifest) | `pipeline/run_ml_tune.py` | run OK |
| Automated ML tests (16) | `pipeline/tests/test_pipeline_ml.py` | ALL PASS |
| Automated tuning tests (8) | `pipeline/tests/test_pipeline_ml_tune.py` | ALL PASS |
| Run manifest (machine-readable) | `reports/ml_run.json` | written |
| Run report (this run's numbers) | `reports/ml_run_report.md` | written |
| Run log | `reports/ml_run.log` | written |
| Per-customer predictions (W1) | `reports/ml_predictions_train.csv` | written |
| Forward-looking predictions (W2) | `reports/ml_predictions_temporal.csv` | written |
| Feature importance table | `reports/ml_feature_importance.csv` | written |
| Tuning run manifest (machine-readable) | `reports/ml_tune.json` | written |
| Tuning run report | `reports/ml_tune_report.md` | written |
| Tuning comparison table (current vs tuned) | `reports/ml_tune_comparison.csv` | written |

## 3. Problem definition

**Target (binary):** a customer *churns* when they made at least one purchase
during an **observation window** (features are built from this window) but made
**no purchase** during the following **label window** (the target is derived
exclusively from this window).

**Why this is the right problem for this dataset:** 4,339 customers with 13
months of purchase history give a natural train/test design. Churn is balanced
(~50% / ~40%), so the problem is learnable, and churn is directly actionable
(retention campaigns), unlike forecasting total revenue on a heavily skewed
invoicing dataset.

**No leakage by construction:** features come only from the observation window,
the label only from the strictly-later label window, and the temporal test set
was never used in training.

## 4. Data

- **Source:** `data/cleaned_retail_data.csv` (527,390 rows) — the validated Phase
  4/5 source. Rows without `CustomerID` (134,658) are dropped: a customer-level
  problem cannot impute identity, and no invented labels are created.
- **Used:** 392,732 purchase rows across 4,339 customers, dates 2010-12-01 ..
  2011-12-09. Invoice dates parsed with the verified `%y/%m/%d` format.

## 5. Features (18, all customer-level, observation-window only)

| Group | Features |
|-------|----------|
| Recency / tenure | `recency_days` (days since last purchase), `tenure_days` (since first), `cohort_month` |
| Frequency / value | `frequency` (orders), `monetary` (spend), `avg_order_value`, `distinct_products`, `total_quantity`, `avg_items_per_order`, `avg_unit_price` |
| Engagement / behaviour | `active_months`, `weekend_ratio`, `hour_mean`, `hour_std` |
| Purchase cadence | `gap_mean_days`, `gap_std_days`, `orders_last_30d` |
| Context | `is_uk` |

No label-period data enters any feature. `gap_*` and `hour_std` are missing for
single-order customers and are median-imputed inside every model pipeline.

## 6. Target definition

`churn = 1` if the customer has **zero** purchases in the label window, else `0`.
Eligibility: at least one purchase in the observation window.

## 7. Methodology (time-aware, honest)

**W1 (train / validation):** obs 2010-12-01..2011-05-31, label 2011-06-01..2011-08-31
→ **2,718 customers, churn rate 50.4%.**

**W2 (temporal holdout test):** obs 2011-03-01..2011-08-31, label 2011-09-01..2011-11-30
→ **2,813 customers, churn rate 39.5%.** The model is trained *only* on W1 and
then applied to W2 without retraining — a genuine out-of-time generalization
test, the strictest no-leakage check available for this dataset.

**Selection:** 5-fold stratified cross-validation on W1 (out-of-fold metrics)
ranks candidates; the best model is refit on all of W1 and scored on W2.

**Baseline:** a `DummyClassifier` (always predict the majority class, ROC-AUC
0.50) so every learned model is compared against the cheap default.

**Reproducibility:** `random_state = 42` everywhere; the test suite proves two
identical runs produce identical predictions.

## 8. Models & metrics

### W1 out-of-fold cross-validation (2,718 customers)

Tuned (Phase 6.1, GridSearchCV 5-fold on W1 only):

| model | acc | precision | recall | F1 | ROC-AUC | PR-AUC |
|-------|-----|-----------|--------|-----|---------|--------|
| **logistic (C=0.1)** | 0.699 | 0.667 | 0.807 | 0.730 | **0.755** | **0.707** |
| random_forest (tuned) | 0.694 | 0.671 | 0.773 | 0.718 | 0.753 | 0.702 |
| gradient_boosting (tuned) | 0.685 | 0.662 | 0.766 | 0.710 | 0.742 | 0.690 |
| baseline (majority) | 0.504 | 0.504 | 1.000 | 0.670 | 0.500 | 0.504 |

**Winner: logistic regression** (highest ROC-AUC). It also has the best F1,
beats the baseline's ROC-AUC by +0.255, and is the most interpretable.

### W2 temporal (out-of-time) test — no retraining (2,813 customers)

Final tuned logistic:

| metric | value |
|--------|-------|
| Accuracy | 0.647 |
| Precision | 0.536 |
| Recall | 0.794 |
| F1 | 0.640 |
| **ROC-AUC** | **0.733** |
| PR-AUC | 0.595 |
| Confusion | TN 936 · FP 765 · FN 229 · TP 883 |

The model generalizes to a later, unseen time period: ROC-AUC stays at 0.73
(vs 0.76 in-sample) and it catches **79.4%** of actual churners in the new
period — a small drop only, i.e. the pattern is stable over time.

### Before (default settings) vs after tuning (final model)

Phase 6.1 ran a small GridSearchCV over the existing model families **on W1
only** (W2 never touched during tuning), then applied the best tuned model to
W2 without retraining.

| metric | default logistic | **tuned logistic (C=0.1)** |
|--------|-----------------|----------------------------|
| W1 ROC-AUC (CV) | 0.7531 | **0.7551** |
| W1 PR-AUC (CV) | 0.6962 | **0.7073** |
| W2 ROC-AUC | 0.7328 | **0.7332** |
| W2 PR-AUC | 0.5932 | **0.5945** |
| W2 recall | 0.7950 | 0.7941 |
| W2 HIGH-risk customers | 1,121 (39.9%) | **1,114 (39.6%)** |

The gain is modest but genuine (both W1 and W2 ROC-AUC and PR-AUC improve) and
recall stays within the 0.05 guard-band of the default model, so the switch was
accepted (`improves_roc=True, improves_pr=True, recall_ok=True`). Full
before/after numbers are in `reports/ml_tune.json` and
`reports/ml_tune_report.md`.

## 9. Interpretability (association, not causation)

Top predictors of churn (final tuned logistic, normalized coefficient
magnitudes):

1. `active_months` (0.198) — fewer active months → higher churn risk
2. `distinct_products` (0.137) — narrow product range → higher risk
3. `recency_days` (0.115) — longer gap since last purchase → higher risk
4. `gap_mean_days` (0.091) — irregular, spread-out purchases → higher risk
5. `total_quantity` (0.076) — lighter volume buyers churn more
6. `hour_std` (0.063) — steadier purchase timing → higher risk
7. `orders_last_30d` (0.061) — no recent orders → higher risk
8. `tenure_days` (0.051) — newer customers churn more
9. `avg_order_value` (0.048) — low spend-per-order → higher risk
10. `hour_mean` (0.040) — off-peak purchase timing → higher risk

**Business meaning:** the model is telling us churn risk concentrates in
**light, infrequent, narrow-basket, quiet-lately** customers. Recency and
purchase cadence dominate — classic, intuitive churn signals that marketing can
act on directly. The full 18-feature table is in
`reports/ml_feature_importance.csv`.

## 10. Predictions output

- `ml_predictions_train.csv` — churn probability + predicted class + risk band
  (LOW < 0.35, MEDIUM, HIGH ≥ 0.65) for every W1 customer (label known).
- `ml_predictions_temporal.csv` — the same forward-looking output for every W2
  customer (2,813 rows), where the label was *never* seen during training.
  **1,114 customers (39.6%) are flagged HIGH risk** and are the retention
  priority list.

## 11. Validation & tests

- `py_compile` on all new modules: OK.
- **16 automated ML tests** (feature schema, no-null CustomerID,
  recency ≠ tenure, features confined to observation window, disjoint windows,
  churn rates = 1369/2718 and 1112/2813, baseline is a coin flip, learned model
  beats baseline, all models trained, metrics in range, temporal test on unseen
  W2, interpretability covers all 18 features, predictions are probabilities,
  identical rerun): **ALL PASS**.
- **8 automated tuning tests** (search space valid, W2 never used in tuning,
  tuned vs current decision logic, reproducibility, manifest fields): **ALL
  PASS**.
- **Reproducibility:** two independent tuning runs produce byte-identical
  prediction and feature-importance CSVs (SHA-256 verified).
- Full regression suite (Phase 4/5 + ML + tuning): unit 20 OK / 1 skipped,
  integration 2 OK, ML 16 OK, tuning 8 OK, plus SQL verification scripts
  (`verify_pipeline.py`, `cohort_validation.py`, `validate_pbi.py`) — all
  **PASS**. No existing behaviour broken.

## 12. Reproduction

```bash
.venv\Scripts\python.exe pipeline\run_ml.py --output reports
.venv\Scripts\python.exe pipeline\run_ml_tune.py --output reports
.venv\Scripts\python.exe -m unittest pipeline.tests.test_pipeline_ml
.venv\Scripts\python.exe -m unittest pipeline.tests.test_pipeline_ml_tune
```

Dependencies: the existing `.venv` (pandas, scikit-learn, numpy, matplotlib,
psycopg2) — scikit-learn 1.9.0 was installed for this phase. No PostgreSQL is
required for the ML layer; it reads the validated CSV directly.

## 13. Limitations

- **13 months of data:** only two temporally-disjoint test periods are possible;
  W2 is a strong but single out-of-time sample.
- Churn is defined at 3-month granularity and only for customers who purchased
  at least once in the observation window (no acquisition churn modelling).
- Predictors describe *association*, not causation; `is_uk` and a few behaviour
  features carry little signal at this resolution.
- Tuning is deliberately lightweight (small GridSearchCV, 20 combinations over
  3 families) to keep the run fast and reproducible; gains over the default
  logistic are modest but genuine, and recall stays within the accepted
  guard-band.
