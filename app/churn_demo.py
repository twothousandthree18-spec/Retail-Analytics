"""Streamlit demo — Retail Customer Churn Predictor (Phase 7).

Interactive front-end for the Phase 6 final tuned model (logistic, C=0.1).
Loads the exported model artifact produced by ``pipeline/model_export.py``;
if the artifact is missing it is built automatically on first run.

Run:
    streamlit run app/churn_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "pipeline"))

from model_export import (  # noqa: E402
    RISK_BINS,
    RISK_LABELS,
    build_final_model,
    default_model_dir,
    load_model,
    predict_single,
)
import ml_models as mod  # noqa: E402
import ml_features as feat  # noqa: E402

# ---------------------------------------------------------------------------
# Model loading (cached — built once, reused across sessions)
# ---------------------------------------------------------------------------

RISK_COLORS = {"LOW": "#2e7d32", "MEDIUM": "#f9a825", "HIGH": "#c62828"}
DIRECTIONS = {
    "recency_days": "days since the last purchase",
    "frequency": "number of orders in the observation window",
    "monetary": "total spend in the observation window (£)",
    "tenure_days": "days since the first purchase",
    "avg_order_value": "average revenue per order (£)",
    "distinct_products": "distinct products purchased",
    "total_quantity": "total units purchased",
    "avg_items_per_order": "average units per order",
    "avg_unit_price": "revenue-weighted average unit price (£)",
    "active_months": "distinct calendar months with purchases",
    "weekend_ratio": "share of purchases on weekends (0–1)",
    "hour_mean": "mean purchase hour (0–23)",
    "hour_std": "variability of purchase hour",
    "gap_mean_days": "average days between orders",
    "gap_std_days": "variability of the gap between orders",
    "orders_last_30d": "orders in the 30 days before the observation end",
    "is_uk": "1 = United Kingdom, 0 = other",
    "cohort_month": "calendar month of first purchase (0 = obs start)",
}

# User-facing subset: every feature maps 1:1 to a Phase 6 model feature.
SUBSET = [
    ("recency_days", 0, 180, 60, 30),
    ("active_months", 1, 12, 6, 1),
    ("frequency", 1, 40, 8, 1),
    ("monetary", 10.0, 5000.0, 800.0, 50.0),
    ("distinct_products", 1, 150, 30, 1),
    ("total_quantity", 1, 1000, 100, 10),
    ("gap_mean_days", 1, 120, 30, 1),
    ("orders_last_30d", 0, 15, 2, 1),
]

# Constant, low-information features fixed to sensible median values.
FIXED = {
    "avg_order_value": None,
    "avg_items_per_order": None,
    "avg_unit_price": None,
    "hour_mean": None,
    "hour_std": None,
    "gap_std_days": None,
    "weekend_ratio": None,
    "is_uk": 1,
    "cohort_month": None,
    "tenure_days": None,
}


@st.cache_resource(show_spinner="Loading the Phase 6 churn model…")
def get_model():
    try:
        return load_model(default_model_dir())
    except FileNotFoundError:
        st.info("Model artifact not found — building the final tuned model "
                "(logistic, C=0.1) from the validated dataset…")
        build_final_model()
        # export writes metadata + joblib; reload gives both halves.
        from model_export import export_model
        export_model(default_model_dir())
        return load_model(default_model_dir())


def _fixed_values(model: "object"):
    med = model.metadata.get("imputation_medians", {})
    out = dict(FIXED)
    for k in out:
        if out[k] is None and k in med and med[k] is not None:
            out[k] = med[k]
    return out


def _risk_text(prob: float) -> str:
    for label, hi in zip(RISK_LABELS, RISK_BINS[1:]):
        if prob < hi:
            return label
    return RISK_LABELS[-1]


def _top_signals(model, features: dict, prob: float) -> list[dict]:
    """Contribution of each entered feature via the model coefficients.

    Association, not causation: a positive contribution means the value is
    associated with a *higher* predicted churn risk.
    """
    imp = {r["feature"]: r for r in model.metadata["feature_importance"]}
    base = _fixed_values(model)
    X = pd.DataFrame([features], columns=mod.FEATURE_COLUMNS)
    scaled = model.model.named_steps["scale"].transform(
        model.model.named_steps["impute"].transform(X))
    coef = model.model.named_steps["model"].coef_[0]
    contrib = {f: scaled[0, i] * coef[i]
               for i, f in enumerate(mod.FEATURE_COLUMNS)}
    signals = []
    for f, v in features.items():
        if f in base and abs(v - base[f]) < 1e-9:
            continue
        c = contrib[f]
        direction = "higher" if c > 0 else "lower"
        signals.append({
            "feature": f,
            "label": DIRECTIONS.get(f, f),
            "value": v,
            "contribution": c,
            "direction": direction,
        })
    signals.sort(key=lambda s: abs(s["contribution"]), reverse=True)
    return signals[:5]


def _fmt(v, unit: str = "") -> str:
    if isinstance(v, float):
        if unit == "£":
            return f"£{v:,.0f}"
        return f"{v:,.0f}"
    return f"{v:,}{unit}"


def main() -> None:
    st.set_page_config(page_title="Retail Customer Churn Predictor",
                       page_icon="📊", layout="wide")

    st.title("Retail Customer Churn Predictor")
    st.caption("End-to-End Retail Analytics & Customer Intelligence Platform — Phase 6 churn model")
    st.markdown(
        "A customer **churns** when they buy in the observation window but then "
        "buy nothing for the following three months. This tool predicts that "
        "risk for a hypothetical customer using the **actual trained Phase 6 "
        "model** — tuned Logistic Regression (C = 0.1), W2 ROC-AUC 0.7332.")

    model = get_model()

    st.markdown("---")
    left, right = st.columns([1, 1])

    with left:
        st.subheader("Customer profile")
        st.caption("Enter the customer's purchase behaviour in the observation "
                   "window (fields left unchanged default to the training "
                   "median).")
        features: dict[str, float] = {}
        for name, lo, hi, default, step in SUBSET:
            features[name] = st.slider(
                f"{name.replace('_', ' ').title()}",
                min_value=float(lo), max_value=float(hi),
                value=float(default), step=float(step),
                help=DIRECTIONS[name])
        for k, v in _fixed_values(model).items():
            if v is not None:
                features[k] = float(v)

        predict = st.button("Predict churn risk", type="primary", use_container_width=True)

    if predict:
        with right:
            with st.spinner("Scoring customer…"):
                result = predict_single(model.model, features)
            prob = result["churn_probability"]
            band = _risk_text(prob)
            color = RISK_COLORS[band]

            st.subheader("Prediction")
            st.markdown(
                f"### Churn probability: **{prob * 100:.1f}%**")
            st.markdown(
                f"### Risk band: :{color if False else ''}"
                f"<span style='color:{color}'><b>{band}</b></span>",
                unsafe_allow_html=True)
            st.markdown(f"Predicted class: **{result['prediction']}** "
                        f"({'churn' if result['prediction'] else 'no churn'})")

            st.markdown("---")
            st.subheader("Key signals")
            st.caption("How the entered values compare with the training "
                       "population, in terms of predicted churn risk "
                       "(**association**, not causation).")
            signals = _top_signals(model, features, prob)
            for s in signals:
                st.markdown(
                    f"- **{s['label'].title()}** = {_fmt(s['value'])} — "
                    f"associated with **{s['direction']}** predicted churn risk")
            if not signals:
                st.markdown("_No strong signals for this profile._")

            st.markdown("---")
            st.subheader("Recommended interpretation")
            if band == "HIGH":
                st.warning(
                    "This customer is at high predicted risk of churning. "
                    "Possible action: prioritize for retention outreach or a "
                    "targeted re-engagement campaign. The model supports "
                    "decision-making; it does not automatically determine the "
                    "business action.")
            elif band == "MEDIUM":
                st.info(
                    "Moderate predicted churn risk. Consider a low-cost "
                    "nudge (e.g. a personalized offer) to reinforce the "
                    "relationship.")
            else:
                st.success(
                    "Low predicted churn risk. No immediate outreach is "
                    "suggested; keep monitoring.")

            st.markdown("---")
            st.caption(
                "Model: tuned Logistic Regression (C=0.1) trained on W1 "
                "(2,718 customers) and tested out-of-time on W2 (2,813 "
                "customers, ROC-AUC 0.7332, PR-AUC 0.5945, recall 79.4%). "
                "Features describe association with churn, not causation.")


if __name__ == "__main__":
    main()
