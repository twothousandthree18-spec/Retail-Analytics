# PHASE 7 FINAL REPORT — Production, Deployment & Portfolio Finalization

**Project:** End-to-End Retail Analytics & Customer Intelligence Platform
**Repo:** `C:\Users\Abdul Rehman\Documents\GitHub\Maimoona Data Analysis`
**Date:** 2026-08-15
**Status:** COMPLETE — no commits or pushes made in this phase

---

## 1. Overview

Phase 7 turned the validated Phase 1–6 analytics project into a production-
style, recruiter-ready portfolio deliverable. The churn model from Phase 6
(final tuned Logistic Regression, C=0.1) was serialized and is served through
an **interactive Streamlit demo** and a **FastAPI prediction endpoint**, backed
by an automated **data-quality/monitoring report**, **CI/CD workflows**, a
**deployment guide**, an **architecture diagram**, a professional **README**,
and portfolio/interview **documentation**.

Everything builds on the already-frozen Phase 6 model and verified numbers —
no Phase 1–6 functionality was modified or redesigned.

---

## 2. What Phase 7 delivers

| Deliverable | Location | Status |
|---|---|---|
| Model export module (final tuned model, joblib + metadata) | `pipeline/model_export.py`, `models/` | DONE — reproduces W2 metrics exactly |
| Interactive demo (Streamlit) | `app/churn_demo.py` | DONE — boots HTTP 200, uses real model |
| Prediction API (FastAPI) | `api/main.py` | DONE — POST /predict, GET /health, GET /model |
| API + model-export tests | `tests/test_api_export.py` | DONE — 10/10 pass |
| Data-quality monitoring report | `reports/data_quality_report.md` + `.html` | DONE — real values, reconciliation PASS |
| CI workflow (fast, on push/PR) | `.github/workflows/ci.yml` | DONE |
| Optional full-pipeline validation workflow | `.github/workflows/full-pipeline.yml` | DONE |
| Deployment guide | `deployment/README.md` | DONE (honest: no live cloud deployment) |
| Architecture diagram (Mermaid + ASCII) | `docs/architecture.md` | DONE |
| Professional README | `README.md` | DONE — verified numbers only |
| Case study | `docs/retail_analytics_case_study.md` | DONE |
| Resume/LinkedIn/portfolio summary | `docs/project_summary.md` | DONE |
| Interview preparation | `docs/interview_questions.md` | DONE |
| Security hygiene | `.gitignore`, `.env.example` | DONE — no secrets, no private paths |

---

## 3. Verified project metrics (unchanged from frozen phases)

| Metric | Value |
|---|---|
| Cleaned transaction lines | 527,390 |
| Customers (attributed) | 4,339 |
| Total revenue | £10,619,986.68 |
| Orders | 22,064 |
| Average order value | £481.33 |
| Repeat customers | 2,845 (65.57%) |
| Products (stock codes) | 3,947 |
| Units sold | 5,438,062 |
| Customer revenue (attributed) | £8,887,208.89 |

---

## 4. Final churn model (Phase 6, frozen — used as-is)

- **Model:** Logistic Regression, tuned **C=0.1**, `max_iter=2000`,
  `random_state=42`, pipeline = SimpleImputer(median) → StandardScaler →
  LogisticRegression.
- **Validation:** W1 trains/validates (2,718 customers); **W2 held out**
  (2,813 customers) — true out-of-time test.
- **W2 metrics (verified this phase):** ROC-AUC **0.7332**, PR-AUC **0.5945**,
  Recall **0.7941**, Precision 0.5358, F1 0.6399, Accuracy 0.6466.
- **High-risk W2:** 1,114 / 2,813 (39.6%).
- **Top drivers (association, not causation):** `active_months` (0.198),
  `distinct_products` (0.137), `recency_days` (0.115), `gap_mean_days` (0.091),
  `total_quantity` (0.076).
- **Reproducibility:** `pipeline/model_export.py` reproduces the model and the
  W2 metrics byte-for-byte (`models/churn_model.joblib` +
  `models/model_metadata.json`).

---

## 5. Interactive demo (Streamlit)

`app/churn_demo.py` — run with `streamlit run app/churn_demo.py`.

- Header: **"Retail Customer Churn Predictor"**.
- 8 user-facing feature sliders (recency, active months, frequency, monetary,
  distinct products, total quantity, gap mean, recent orders); remaining
  features default to the training-window median (same median imputation as
  production).
- Output: churn probability, risk band (LOW / MEDIUM / HIGH), predicted class,
  top-5 key signals with **association-only** wording ("associated with higher
  predicted churn risk"), and a recommended interpretation per band.
- Uses the **actual exported model** via `@st.cache_resource`; if the artifact
  is missing it is rebuilt from source (no fake model).
- Smoke-tested: server boots, HTTP 200.

---

## 6. Prediction API (FastAPI)

`api/main.py` — run with `uvicorn api.main:app --host 0.0.0.0 --port 8000`.

| Endpoint | Request | Response |
|---|---|---|
| `GET /health` | — | `{"status": "ok", "model": "ready"}` |
| `GET /model` | — | model metadata (features, windows, W2 metrics) |
| `POST /predict` | `{"features": {...}}` | `{"churn_probability", "risk_band", "prediction"}` |

- Subset of the 18 features accepted; missing ones median-imputed in-pipeline.
- Validation: unknown features → 422, empty features → 422, clean errors.
- Tested via FastAPI TestClient (10 tests, all pass) — the API adds real value
  as a programmatic scoring surface for integrations (e.g. CRM hooks), separate
  from the human-facing demo.

---

## 7. Data quality / monitoring

`reports/generate_data_quality_report.py` produces
`reports/data_quality_report.md` and a compact self-contained `.html`, computed
**live from the validated artifacts** (nothing invented).

- 14 automated checks (schema, missing, duplicates, numerics, dates, business
  rules) → overall status **WARNING** (all WARNING items are deliberate,
  validated retention policies — zero critical failures).
- Cross-system reconciliation: Python vs PostgreSQL — **PASS, 16 metrics, all
  agree** (revenue to the penny, orders, customers, products, units, AOV,
  repeat customers, customer revenue).
- Includes latest pipeline run manifest status for traceability.

---

## 8. CI/CD (GitHub Actions)

- **`.github/workflows/ci.yml`** — fast checks on every push/PR: compile,
  unit tests, ML model tests, API smoke tests, data-quality report. Never runs
  the 10-minute pipeline on a per-commit basis.
- **`.github/workflows/full-pipeline.yml`** — optional full validation
  (manual `workflow_dispatch` or `v*` tag): boots PostgreSQL, runs the full
  pipeline, ML + tuning, SQL verification, DQ report, slow tests.

---

## 9. Deployment readiness

`deployment/README.md` documents (with honest limitations):

- Local run: env setup, full pipeline, model export, demo, API, DQ report.
- Env vars table (DATABASE_URL, INPUT_DATA_PATH, OUTPUT_DIR,
  PIPELINE_TEMP_DIR, MODEL_ARTIFACT_DIR, churn thresholds).
- Cloud deployment steps for Streamlit Community Cloud/Render and the
  containerised FastAPI (Dockerfile recipe), hosted PostgreSQL.
- **Stated limitation:** no live cloud deployment is running in this repo; the
  Dockerfile and instructions are ready-to-use but not cloud-tested.
- `data/cleaned_retail_data.csv` and `models/` are gitignored — any deployment
  must restore the data or re-run the pipeline first.

---

## 10. Documentation

- `README.md` — upgraded to "End-to-End Retail Analytics & Customer
  Intelligence Platform": verified metrics table, layer-by-layer walkthrough,
  quick start, repo layout. (Previously the course-oriented README.)
- `docs/architecture.md` — Mermaid diagram + ASCII fallback covering the full
  flow Raw CSV → cleaning → PostgreSQL → SQL/Excel/Power BI → RFM+cohorts →
  ML → Churn Prediction API → Demo → Business Decision.
- `docs/retail_analytics_case_study.md` — problem/approach/results/limitations
  with verified numbers.
- `docs/project_summary.md` — one-page resume/LinkedIn/GitHub/portfolio text.
- `docs/interview_questions.md` — 26 practice Q&A grouped by topic.

---

## 11. Files changed in Phase 7

**Created:**
- `pipeline/model_export.py`
- `app/churn_demo.py`
- `api/main.py`
- `tests/test_api_export.py`
- `reports/generate_data_quality_report.py`
- `reports/data_quality_report.md`, `reports/data_quality_report.html`
- `.github/workflows/ci.yml`, `.github/workflows/full-pipeline.yml`
- `deployment/README.md`
- `docs/architecture.md`, `docs/retail_analytics_case_study.md`,
  `docs/project_summary.md`, `docs/interview_questions.md`
- `requirements.txt`
- `models/churn_model.joblib`, `models/model_metadata.json` (gitignored —
  regenerable via `pipeline/model_export.py`)

**Modified:**
- `README.md` (professional upgrade)
- `.gitignore` (added `.env` hardening, `models/`, `.streamlit/`)
- `.env.example` (sanitized private paths; added `MODEL_ARTIFACT_DIR`, churn
  thresholds)

**Installed (venv only, not committed):** streamlit, fastapi, uvicorn,
pydantic, httpx.

---

## 12. Validation & QA performed (Phase 7)

| Check | Result |
|---|---|
| `pipeline/model_export.py` W2 metrics | ROC-AUC 0.7332, PR-AUC 0.5945, recall 0.7941 — matches frozen model |
| `tests/test_api_export.py` | 10/10 pass |
| Streamlit demo boot | HTTP 200, model loads |
| `reports/generate_data_quality_report.py` | reconciliation PASS (16 metrics) |
| `sql/verify_pipeline.py` | ALL CHECKS PASSED (RFM 100% agreement 4,339/4,339) |
| `sql/cohort_validation.py` | ALL CHECKS PASSED (12 checks) |
| `powerbi/scripts/validate_pbi.py` | ALL CHECKS PASSED (24 checks) |
| Unit tests (Phase 1–5) | 20/20 OK |
| Integration tests | 2/2 OK |
| ML tests (Phase 6) | 16/16 OK |
| Tuning tests | 8/8 OK |

Slow full-pipeline tests were not re-run (regression confidence established
via the validators above; the full pipeline is available in the optional
`full-pipeline.yml` workflow).

---

## 13. Limitations & remaining items

- **No live cloud deployment.** Deployment is documented and ready
  (Dockerfile + platform steps) but not deployed — intentionally, to stay
  honest in a portfolio.
- **Model artifact and cleaned data are gitignored** — a deployment/CI run must
  regenerate them (`pipeline/run_pipeline.py` → `pipeline/model_export.py`).
- **Churn threshold is fixed** at 0.35/0.65 (LOW/MEDIUM/HIGH); threshold tuning
  is a business decision exposed as env vars in `.env.example`.
- **Feature drift / retraining monitoring** not automated — recommended follow-up.
- **API auth** not implemented (documented) — fine for demo, required for any
  public deployment.
- Nothing committed or pushed in Phase 7 (final git status/diff confirmed
  below); next steps await explicit instruction.
