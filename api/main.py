"""FastAPI service â€” Retail Customer Churn Predictor (Phase 7).

Thin prediction API over the same exported Phase 6 final tuned model used by
the Streamlit demo. No database access; no credentials.

Endpoints
---------
    GET  /health     liveness + model readiness
    GET  /model      model metadata (features, windows, W2 metrics)
    POST /predict    churn prediction from customer features

Run:
    uvicorn api.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipeline"))

from model_export import (  # noqa: E402
    OPTIONAL_FEATURES,
    default_model_dir,
    load_model,
    predict_single,
)

app = FastAPI(
    title="Retail Customer Churn Predictor API",
    description="Serves the Phase 6 final tuned model (logistic, C=0.1) for "
                "customer churn prediction. No leakage: model trained on W1, "
                "tested out-of-time on W2.",
    version="1.0.0",
)


class PredictRequest(BaseModel):
    features: dict[str, float] = Field(
        ..., description="Subset of the 18 model features (missing ones are "
                         "median-imputed, same as production).")


class PredictResponse(BaseModel):
    churn_probability: float
    risk_band: str
    prediction: int


def _model():
    try:
        return load_model(default_model_dir())
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Model artifact not found. Run "
                   "`python pipeline/model_export.py` first.") from exc


@app.get("/health")
def health() -> dict:
    try:
        load_model(default_model_dir())
        return {"status": "ok", "model": "ready"}
    except FileNotFoundError:
        return {"status": "degraded", "model": "missing"}


@app.get("/model", response_model=dict)
def model_info() -> dict:
    m = _model().metadata
    return {
        "final_model": m["final_model"],
        "source": m["source"],
        "hyperparameters": m["hyperparameters"],
        "windows": m["windows"],
        "w2_metrics": m["w2_metrics"],
        "feature_columns": m["feature_columns"],
        "risk_labels": m["risk_labels"],
    }


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    unknown = set(req.features) - OPTIONAL_FEATURES
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"unknown feature(s): {sorted(unknown)}")
    if not req.features:
        raise HTTPException(
            status_code=422,
            detail="at least one feature is required")
    m = _model()
    try:
        result = predict_single(m.model, req.features)
    except Exception as exc:  # noqa: BLE001 - surface cleanly to the client
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PredictResponse(**result)
