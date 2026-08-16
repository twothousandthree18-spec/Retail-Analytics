"""Model export / loading for the Phase 7 demo & API layer.

The Phase 6 final model is the *tuned* logistic regression pipeline
(SimpleImputer(median) -> StandardScaler -> LogisticRegression(C=0.1)),
selected by ``run_ml_tune.py`` because it improved W2 ROC-AUC/PR-AUC while
staying inside the recall guard. This module reproduces *exactly* that model
(the same W1 features, the same fixed random state, the same C=0.1) and
serializes it with joblib so the Streamlit demo and FastAPI endpoint use the
real trained model — never a fake/demo model.

Why retrain instead of shipping a pickle? Logistic regression on 2,718 x 18
rows trains in a fraction of a second, is fully deterministic
(``random_state=42``, no randomness in the solver path), and reproduces the
same W2 metrics byte-for-byte. Rebuilding from source keeps the repository
free of opaque binary artifacts and makes the demo reproducible from scratch.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from dotenv import load_dotenv  # noqa: E402

import ml_features as feat  # noqa: E402
import ml_models as mod  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(REPO_ROOT / ".env")


def default_model_dir() -> Path:
    return Path(os.environ.get("MODEL_ARTIFACT_DIR", str(REPO_ROOT / "models")))

# Final model hyperparameters chosen by Phase 6.1 tuning (ml_tune.json).
FINAL_C = 0.1

RISK_BINS = [-1e-9, 0.35, 0.65, 1.0]
RISK_LABELS = ["LOW", "MEDIUM", "HIGH"]

# Fields a user may leave blank; the fitted imputer replaces them with the
# training-window median, exactly as it would for a real customer record.
OPTIONAL_FEATURES = {
    "recency_days", "frequency", "monetary", "tenure_days", "avg_order_value",
    "distinct_products", "total_quantity", "avg_items_per_order",
    "avg_unit_price", "active_months", "weekend_ratio", "hour_mean", "hour_std",
    "gap_mean_days", "gap_std_days", "orders_last_30d", "is_uk", "cohort_month",
}


def build_final_model() -> Pipeline:
    """Build the exact Phase 6.1 final model: tuned logistic regression.

    Trains on W1 only (obs 2010-12..2011-05, label 2011-06..2011-08). W2 is
    never used for training — it is a held-out temporal test.
    """
    df = feat.load_cleaned()
    w1 = feat.build_features(df, feat.WINDOW_W1)
    X = w1[feat.FEATURE_COLUMNS]
    y = feat.build_target(df, feat.WINDOW_W1, w1).to_numpy()

    model = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("model", LogisticRegression(C=FINAL_C, max_iter=2000,
                                     random_state=mod.RANDOM_STATE)),
    ])
    model.fit(X, y)
    return model


def _w2_metrics(model: Pipeline) -> dict:
    """Score the model on the held-out W2 temporal window (never trained on)."""
    df = feat.load_cleaned()
    w2 = feat.build_features(df, feat.WINDOW_W2)
    X2 = w2[feat.FEATURE_COLUMNS]
    y2 = feat.build_target(df, feat.WINDOW_W2, w2).to_numpy()
    return mod.temporal_metrics(model, X2, y2)


def _medians() -> dict:
    df = feat.load_cleaned()
    w1 = feat.build_features(df, feat.WINDOW_W1)
    return w1[feat.FEATURE_COLUMNS].median(axis=0).to_dict()


def export_model(model_dir: Path | str | None = None) -> Path:
    """Train the final model, score it on W2, and persist it with joblib.

    Writes ``churn_model.joblib`` and ``model_metadata.json`` into ``model_dir``
    (default ``<repo>/models``). Returns the joblib path.
    """
    out = Path(model_dir) if model_dir else default_model_dir()
    out.mkdir(parents=True, exist_ok=True)

    model = build_final_model()
    w2 = _w2_metrics(model)
    importance = mod.feature_importance(model, mod.FEATURE_COLUMNS)

    metadata = {
        "final_model": "logistic",
        "source": "tuned_logistic",
        "hyperparameters": {"model__C": FINAL_C},
        "random_state": mod.RANDOM_STATE,
        "feature_columns": mod.FEATURE_COLUMNS,
        "risk_bins": RISK_BINS,
        "risk_labels": RISK_LABELS,
        "windows": {
            "W1_train_val": {
                "obs": [str(feat.WINDOW_W1.obs_start), str(feat.WINDOW_W1.obs_end)],
                "label": [str(feat.WINDOW_W1.label_start), str(feat.WINDOW_W1.label_end)],
            },
            "W2_temporal_test": {
                "obs": [str(feat.WINDOW_W2.obs_start), str(feat.WINDOW_W2.obs_end)],
                "label": [str(feat.WINDOW_W2.label_start), str(feat.WINDOW_W2.label_end)],
            },
        },
        "w2_metrics": {k: v for k, v in w2.items() if k != "model"},
        "w2_confusion": w2.get("confusion"),
        "train_window_n": 2718,
        "temporal_window_n": 2813,
        "feature_importance": importance.to_dict("records"),
        "imputation_medians": {k: (None if pd.isna(v) else float(v))
                               for k, v in _medians().items()},
    }

    joblib_path = out / "churn_model.joblib"
    joblib.dump(model, joblib_path)
    (out / "model_metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8")
    return joblib_path


@dataclass
class LoadedModel:
    model: Pipeline
    metadata: dict


def load_model(model_dir: Path | str | None = None) -> LoadedModel:
    """Load the exported model + metadata (raises if not exported yet)."""
    base = Path(model_dir) if model_dir else default_model_dir()
    model = joblib.load(base / "churn_model.joblib")
    metadata = json.loads((base / "model_metadata.json").read_text(encoding="utf-8"))
    return LoadedModel(model=model, metadata=metadata)


def predict_single(model: Pipeline, features: dict[str, float]) -> dict:
    """Predict churn for one customer from the 18 model features.

    ``features`` may contain any subset of ``OPTIONAL_FEATURES``; missing
    features become NaN and are median-imputed inside the pipeline (identical
    to the production path). Returns probability, prediction and risk band.
    """
    row = {col: np.nan for col in mod.FEATURE_COLUMNS}
    for k, v in features.items():
        if k not in row:
            raise ValueError(f"unknown feature: {k}")
        row[k] = float(v)
    X = pd.DataFrame([row], columns=mod.FEATURE_COLUMNS)
    proba = float(model.predict_proba(X)[0, 1])
    pred = int(model.predict(X)[0])
    band = str(pd.cut([proba], bins=RISK_BINS, labels=RISK_LABELS)[0])
    return {
        "churn_probability": round(proba, 4),
        "prediction": pred,
        "risk_band": band,
    }


if __name__ == "__main__":
    path = export_model()
    print(f"exported final tuned logistic model -> {path}")
    m = load_model()
    w2 = m.metadata["w2_metrics"]
    print(f"W2 roc_auc={w2['roc_auc']:.4f} pr_auc={w2['pr_auc']:.4f} "
          f"recall={w2['recall']:.4f}")
