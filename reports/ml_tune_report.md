# ML Tuning Report — Phase 6.1 Lightweight Hyperparameter Search

- **Run ID:** 2026-08-15
- **Status:** SUCCESS
- **Best tuned model (W1 CV ROC-AUC):** `logistic`
- **Final model:** `logistic` (source: tuned_logistic)

## 1. Tuning method
Small GridSearchCV (5-fold stratified, W1 only) per existing Phase 6 model, refit on ROC-AUC. **W2 is not used anywhere during tuning.**

## 2. Search space

| model | hyperparameters | combinations |
|-------|-----------------|--------------|
| logistic | C in [0.01, 0.1, 1.0, 10.0] | 4 |
| random_forest | n_estimators in [200, 400], max_depth in [8, 12], min_samples_leaf in [2, 5] | 8 |
| gradient_boosting | n_estimators in [150, 250], max_depth in [3, 4], learning_rate in [0.05, 0.1] | 8 |

## 3. W1 CV comparison (current vs tuned)

| model | acc | prec | rec | F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|
| current_logistic | 0.700 | 0.667 | 0.808 | 0.731 | 0.753 | 0.696 |
| tuned_logistic | 0.699 | 0.667 | 0.807 | 0.730 | 0.755 | 0.707 |
| current_random_forest | 0.688 | 0.666 | 0.764 | 0.712 | 0.749 | 0.694 |
| tuned_random_forest | 0.694 | 0.671 | 0.773 | 0.718 | 0.753 | 0.702 |
| current_gradient_boosting | 0.666 | 0.650 | 0.730 | 0.688 | 0.723 | 0.668 |
| tuned_gradient_boosting | 0.685 | 0.662 | 0.766 | 0.710 | 0.742 | 0.690 |

## 4. W2 temporal test (never trained on W2)

| model | acc | prec | rec | F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|---|
| current logistic | 0.647 | 0.536 | 0.795 | 0.640 | 0.733 | 0.593 |
| tuned logistic | 0.647 | 0.536 | 0.794 | 0.640 | 0.733 | 0.595 |

## 5. Final-model decision

- Switch? **True**  improves_roc=True, improves_pr=True, recall_ok=True
- **Final model:** `logistic`  (source: tuned_logistic)
- Final-model hyperparameters: {'model__C': 0.1}
- Reason: tuned 'logistic' improves W2 (roc_auc 0.7332 vs 0.7328, pr_auc 0.5945 vs 0.5932) with recall 0.7941 vs 0.7950

## 6. Interpretability (final model, association not causation)

| rank | feature | importance |
|---|---|---|
| 1 | active_months | 0.1981 |
| 2 | distinct_products | 0.1366 |
| 3 | recency_days | 0.1151 |
| 4 | gap_mean_days | 0.0911 |
| 5 | total_quantity | 0.0761 |
| 6 | hour_std | 0.0634 |
| 7 | orders_last_30d | 0.0611 |
| 8 | tenure_days | 0.0511 |
| 9 | avg_order_value | 0.0477 |
| 10 | hour_mean | 0.0399 |

## 7. Prediction outputs (regenerated with the final model)

- `ml_predictions_train.csv` — 2,718 W1 customers
- `ml_predictions_temporal.csv` — 2,813 W2 customers
- `ml_feature_importance.csv` — full 18-feature importance table

