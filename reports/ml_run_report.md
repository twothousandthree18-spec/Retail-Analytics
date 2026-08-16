# ML Run Report — Customer Churn Prediction (Phase 6)

- **Run ID:** 2026-08-15
- **Timestamp:** 2026-08-15T13:34:26
- **Status:** SUCCESS
- **Best model:** `logistic` (chosen by training-window CV ROC-AUC)

## Windows
- W1 train/validation: obs 2010-12-01..2011-05-31, label 2011-06-01..2011-08-31 (2,718 customers)
- W2 temporal test: obs 2011-03-01..2011-08-31, label 2011-09-01..2011-11-30 (2,813 customers)

## Training-window CV (W1, out-of-fold)

| model | acc | prec | rec | F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|
| logistic | 0.700 | 0.667 | 0.808 | 0.731 | 0.753 | 0.696 |
| random_forest | 0.688 | 0.666 | 0.764 | 0.712 | 0.749 | 0.694 |
| gradient_boosting | 0.666 | 0.650 | 0.730 | 0.688 | 0.723 | 0.668 |

## Baseline (majority class)
Accuracy 0.504 · ROC-AUC 0.500 · PR-AUC 0.504

## Temporal (out-of-time) test on W2 — no retraining

logistic: acc 0.647 · precision 0.536 · recall 0.795 · F1 0.640 · ROC-AUC 0.733 · PR-AUC 0.593

## Top predictive features (association only, not causation)

| rank | feature | importance |
|---|---|---|
| 1 | active_months | 0.1797 |
| 2 | total_quantity | 0.1241 |
| 3 | distinct_products | 0.1197 |
| 4 | recency_days | 0.1009 |
| 5 | gap_mean_days | 0.0818 |
| 6 | frequency | 0.0760 |
| 7 | avg_order_value | 0.0758 |
| 8 | tenure_days | 0.0664 |
| 9 | orders_last_30d | 0.0523 |
| 10 | hour_std | 0.0496 |

## Predictions
- `ml_predictions_train.csv` — churn probability for every W1 customer (label known).
- `ml_predictions_temporal.csv` — forward-looking probabilities for every W2 customer (label known, model never saw it).

