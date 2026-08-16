"""Lightweight, disciplined hyperparameter tuning for the Phase 6 churn models.

Constraints honoured here:

* Only the existing Phase 6 models are tuned (logistic regression, random
  forest, gradient boosting) on the *existing* 18 features.
* Cross-validation runs **only inside W1**. W2 is never used for model
  selection or hyperparameter selection.
* The search is small and computationally reasonable (a handful of values per
  hyperparameter, deterministic 5-fold stratified CV).
* The final-model rule (in ``decide_final``) keeps the existing logistic model
  unless tuning improves W2 ROC-AUC and/or PR-AUC without materially hurting
  recall — tuning never forces a change on its own.
"""

from __future__ import annotations

import pandas as pd
from sklearn.ensemble import (GradientBoostingClassifier,
                              RandomForestClassifier)
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml_models import RANDOM_STATE

# Secondary evaluation reported but ROC-AUC drives selection.
SCORERS = {
    "roc_auc": "roc_auc",
    "pr_auc": "average_precision",
    "accuracy": "accuracy",
    "precision": "precision",
    "recall": "recall",
    "f1": "f1",
}

# Tolerated recall loss (percentage points) vs the current model before we
# refuse to switch — the "materially harming recall" guard.
RECALL_TOLERANCE_PP = 0.05


def _logistic_pipe() -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("model", LogisticRegression(max_iter=2000, random_state=RANDOM_STATE)),
    ])


def _rf_pipe() -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("model", RandomForestClassifier(n_jobs=1, random_state=RANDOM_STATE)),
    ])


def _gb_pipe() -> Pipeline:
    return Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("model", GradientBoostingClassifier(random_state=RANDOM_STATE)),
    ])


# Small, deliberately restricted search spaces (24 combinations total).
SEARCH_SPACES: dict[str, tuple[Pipeline, dict]] = {
    "logistic": (
        _logistic_pipe(),
        {"model__C": [0.01, 0.1, 1.0, 10.0]},
    ),
    "random_forest": (
        _rf_pipe(),
        {
            "model__n_estimators": [200, 400],
            "model__max_depth": [8, 12],
            "model__min_samples_leaf": [2, 5],
        },
    ),
    "gradient_boosting": (
        _gb_pipe(),
        {
            "model__n_estimators": [150, 250],
            "model__max_depth": [3, 4],
            "model__learning_rate": [0.05, 0.1],
        },
    ),
}


def tune_models(X: pd.DataFrame, y: pd.Series | list, cv) -> dict:
    """Grid-search each model on W1 only. Returns per-model results.

    Each result dict has: ``best_params``, ``estimator`` (refit on all of W1 by
    GridSearchCV), and ``cv`` (mean out-of-fold metrics for the best config).
    """
    results: dict[str, dict] = {}
    for name, (pipe, grid) in SEARCH_SPACES.items():
        gs = GridSearchCV(pipe, grid, cv=cv, scoring=SCORERS, refit="roc_auc",
                          n_jobs=-1, return_train_score=False)
        gs.fit(X, y)
        metrics = {m: float(gs.cv_results_[f"mean_test_{m}"][gs.best_index_])
                   for m in SCORERS}
        results[name] = {
            "best_params": gs.best_params_,
            "estimator": gs.best_estimator_,
            "cv": metrics,
        }
    return results


def select_best_tuned(tuned: dict) -> str:
    """Best tuned model by W1 CV ROC-AUC (PR-AUC breaks ties)."""
    def key(name: str) -> tuple[float, float]:
        cv = tuned[name]["cv"]
        return cv["roc_auc"], cv["pr_auc"]
    return max(tuned, key=key)


def decide_final(current_logistic_w2: dict, tuned_name: str,
                 tuned_w2: dict) -> dict:
    """Apply the final-model rule on W2 (never on W1-only metrics).

    Switch to the tuned model only if W2 ROC-AUC and/or PR-AUC improves and
    recall does not fall by more than ``RECALL_TOLERANCE_PP``.
    """
    improves_roc = tuned_w2["roc_auc"] > current_logistic_w2["roc_auc"]
    improves_pr = tuned_w2["pr_auc"] > current_logistic_w2["pr_auc"]
    recall_ok = tuned_w2["recall"] >= current_logistic_w2["recall"] - RECALL_TOLERANCE_PP
    switch = (improves_roc or improves_pr) and recall_ok
    return {
        "switch": bool(switch),
        "final_model": tuned_name if switch else "logistic",
        "improves_roc": bool(improves_roc),
        "improves_pr": bool(improves_pr),
        "recall_ok": bool(recall_ok),
        "reason": (
            f"tuned '{tuned_name}' improves W2 (roc_auc {tuned_w2['roc_auc']:.4f} vs "
            f"{current_logistic_w2['roc_auc']:.4f}, pr_auc {tuned_w2['pr_auc']:.4f} vs "
            f"{current_logistic_w2['pr_auc']:.4f}) with recall {tuned_w2['recall']:.4f} "
            f"vs {current_logistic_w2['recall']:.4f}"
            if switch else
            "tuning did not improve W2 ROC-AUC/PR-AUC within the recall guard; "
            "retaining the current logistic regression model"
        ),
    }
