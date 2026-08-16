"""Churn model training, evaluation and interpretability (Phase 6).

Conventions mirror the Phase 5 pipeline: deterministic seeds, explicit model
registry, honest metrics for a binary classification problem, and feature
importance reported with the caveat that it is association, not causation.

Baseline: a DummyClassifier (most-frequent) so every learned model is compared
against "predict everyone churns" — the cheap default a business would otherwise
use.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score,
                             precision_score, recall_score, roc_auc_score,
                             average_precision_score)
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

RANDOM_STATE = 42
SEED = 42

FEATURE_COLUMNS = [
    "recency_days", "frequency", "monetary", "tenure_days", "avg_order_value",
    "distinct_products", "total_quantity", "avg_items_per_order",
    "avg_unit_price", "active_months", "weekend_ratio", "hour_mean", "hour_std",
    "gap_mean_days", "gap_std_days", "orders_last_30d", "is_uk", "cohort_month",
]

MODELS = {
    "logistic": Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("model", LogisticRegression(max_iter=2000, random_state=RANDOM_STATE)),
    ]),
    "random_forest": Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("model", RandomForestClassifier(
            n_estimators=400, max_depth=10, min_samples_leaf=5,
            random_state=RANDOM_STATE, n_jobs=-1)),
    ]),
    "gradient_boosting": Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("model", GradientBoostingClassifier(
            n_estimators=250, max_depth=4, learning_rate=0.06,
            subsample=0.8, random_state=RANDOM_STATE)),
    ]),
}


def baseline_metrics(X: pd.DataFrame, y: np.ndarray) -> dict:
    """Metrics for the 'predict the majority class' baseline (DummyClassifier)."""
    dummy = DummyClassifier(strategy="most_frequent", random_state=RANDOM_STATE)
    dummy.fit(X, y)
    pred = dummy.predict(X)
    proba = dummy.predict_proba(X)[:, 1]
    return _score("dummy_baseline", y, pred, proba, None)


def _score(name: str, y_true: np.ndarray, y_pred: np.ndarray,
           y_prob: np.ndarray, model) -> dict:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return {
        "model": name,
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_prob)), 4),
        "pr_auc": round(float(average_precision_score(y_true, y_prob)), 4),
        "confusion": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def cv_evaluate(name: str, model, X: pd.DataFrame, y: np.ndarray,
                cv: StratifiedKFold) -> dict:
    """Out-of-fold evaluation on the training window (honest, no test leakage)."""
    pred = cross_val_predict(model, X, y, cv=cv, method="predict")
    proba = cross_val_predict(model, X, y, cv=cv, method="predict_proba")[:, 1]
    return _score(name, y, pred, proba, model)


def train_models(X_train: pd.DataFrame, y_train: np.ndarray,
                 cv: StratifiedKFold) -> tuple[dict, dict]:
    """Train all models on the training window; return (cv_metrics, fitted).

    Cross-validation metrics rank the candidates; the best model is then
    refit on the full training window and returned for the temporal test.
    """
    cv_metrics: dict[str, dict] = {}
    fitted: dict[str, object] = {}
    for name, model in MODELS.items():
        metrics = cv_evaluate(name, model, X_train, y_train, cv)
        cv_metrics[name] = metrics
        model.fit(X_train, y_train)  # refit on full training window
        fitted[name] = model
    return cv_metrics, fitted


def select_best(cv_metrics: dict[str, dict]) -> str:
    """Best candidate by ROC-AUC on the training-window CV."""
    return max(cv_metrics, key=lambda n: cv_metrics[n]["roc_auc"])


def temporal_metrics(model, X_test: pd.DataFrame, y_test: np.ndarray) -> dict:
    """Apply a fitted model to the out-of-time window (W2) and score it."""
    pred = model.predict(X_test)
    proba = model.predict_proba(X_test)[:, 1]
    return _score(type(model).__name__ if hasattr(model, "predict_proba")
                  else "best_model", y_test, pred, proba, model)


def feature_importance(best_model, feature_names: list[str]) -> pd.DataFrame:
    """Extract feature importance from the fitted model where available.

    Returns a DataFrame with the raw importances (association only — not
    causal). For linear pipelines, uses the scaled coefficients.
    """
    model = best_model
    if isinstance(model, Pipeline):
        model = model.named_steps["model"]
    if isinstance(model, (RandomForestClassifier, GradientBoostingClassifier)):
        imp = model.feature_importances_
        table = pd.DataFrame({"feature": feature_names, "importance": imp})
        return table.sort_values("importance", ascending=False).reset_index(drop=True)
    if isinstance(model, LogisticRegression):
        coef = np.abs(model.coef_[0])
        table = pd.DataFrame({"feature": feature_names,
                              "importance": coef / coef.sum(),
                              "coefficient": model.coef_[0]})
        return table.sort_values("importance", ascending=False).reset_index(drop=True)
    raise ValueError(f"no interpretability for {type(model).__name__}")


def predict_customers(model, X: pd.DataFrame, customer_ids: pd.Series) -> pd.DataFrame:
    """Predict churn probability for every customer in ``X``."""
    proba = model.predict_proba(X)[:, 1]
    pred = model.predict(X)
    out = pd.DataFrame({
        "CustomerID": customer_ids.to_numpy(),
        "churn_probability": np.round(proba, 6),
        "churn_prediction": pred.astype(int),
        "risk": pd.cut(proba, bins=[-1e-9, 0.35, 0.65, 1.0],
                       labels=["LOW", "MEDIUM", "HIGH"]).astype(str),
    })
    return out
