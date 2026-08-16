# End-to-End Retail Analytics & Customer Intelligence Platform

A complete, production-minded analytics project on the **Online Retail dataset**
(UCI) — from raw transactional CSV to validated dashboards and a **deployed
customer-churn machine-learning model**. Every number in this README is
verified by an automated validation suite that reconciles independent Python,
SQL and Power BI implementations against each other.

```
Raw Retail Data → Python/Pandas → Data Quality → PostgreSQL
      → SQL/Excel/Power BI → Customer Analytics (RFM + Cohorts)
      → ML → Churn Prediction API → Interactive Demo → Business Decision
```

## Verified results (reconciled across Python, SQL and Power BI)

| Metric | Value |
|---|---|
| Cleaned transaction lines | **527,390** |
| Customers (attributed) | **4,339** |
| Total revenue | **£10,619,986.68** |
| Total orders | **22,064** |
| Average order value | **£481.33** |
| Repeat customers | **2,845 (65.57%)** |
| Churn model — W2 ROC-AUC | **0.7332** |
| Churn model — W2 recall | **0.7941** |

---

## Project layers

| Phase | Layer | What it does | Deliverables |
|---|---|---|---|
| 1–2 | Python / Pandas pipeline | Clean raw 541,909-row CSV; compute KPIs; validate | `data/cleaned_retail_data.csv`, Excel report (26 sheets, RFM segmentation) |
| 3–4 | PostgreSQL + SQL | Reproduce analytics in SQL: sales, RFM, cohorts | `sql/*.sql`, `rfm_segments`, `cohort_retention` tables |
| 3–4 | Excel & Power BI | Recruiter-facing dashboards on validated data | `Retail_Analysis.pbit`, 5 report pages, 29 DAX measures |
| 5 | Production pipeline | End-to-end `run_pipeline.py` with data-quality gate + reconciliation | `pipeline/`, `reports/` run manifests |
| 6 | Machine learning | Churn prediction: features, model family, tuning | `run_ml.py`, `run_ml_tune.py`, final tuned logistic (C=0.1) |
| 7 | Serve & deploy | FastAPI endpoint, Streamlit demo, CI, deployment docs | `api/`, `app/`, `.github/workflows/`, `deployment/` |

### 1. Data cleaning & customer analytics (Python / pandas / Excel)
`OnlineRetail cleaning.ipynb` cleans the raw data and produces
`Retail_Analysis_Report.xlsx` with **26 sheets** — Summary Dashboard, Sales,
Customer, Product, Time analysis and RFM Customer Segmentation (Recency /
Frequency / Monetary quartiles + 7 customer segments for 4,339 customers), plus
cohort sheets. The cleaned dataset exports to `data/cleaned_retail_data.csv`.

### 2. SQL analytics layer (PostgreSQL)
`sql/` re-analyses the same cleaned data **independently** in PostgreSQL and
reconciles it with the Python results:
- `sql/schema.sql` + `sql/load_data.py` — reproducible, credential-safe load
- `sql/01…06_*.sql` — **38 business questions** using CTEs, window functions,
  time intelligence; RFM segmentation reproduced in SQL
- `sql/06_cohort_retention_analysis.sql` — customer cohorts with M0–M12
  retention matrix, revenue-by-age, lifecycle summaries
- `sql/verify_pipeline.py` / `sql/cohort_validation.py` — automated
  reconciliation (RFM agrees 100% customer-by-customer; cohorts 12/12 PASS)

**Phase 4 findings:** 13 monthly cohorts; M1 retention 22.7%, 6-month retention
27.2%, months 3–10 plateau at 26–30%; the founding Dec-2010 cohort retains
87.5% of customers and generates 50.7% of cohort revenue.

### 3. Power BI layer
`powerbi/` ships a star-schema model (FactSales + 4 dimensions + cohort tables,
4 relationships, 29 DAX measures), parameterised M queries, a page build spec
and static previews of all report pages — generated with **real data** and
reconciled against PostgreSQL (24 checks, all PASS). See
`powerbi/PHASE3_REPORT.md`.

### 4. Production pipeline & data quality
`pipeline/run_pipeline.py` orchestrates the whole chain with a **quality gate**:
schema checks, missing-value policy, duplicate detection, date validation,
business rules, and a **Python-vs-PostgreSQL reconciliation** (16 metrics, all
PASS). Status is persisted per run in `reports/pipeline_run*.json`.
`reports/generate_data_quality_report.py` produces a stakeholder report
(Markdown + compact HTML) from the live validated artifacts.

### 5. Machine learning — customer churn (Phase 6)
Built on the SQL-validated customer table, predicting 3-month churn.
- **18 engineered features** (recency, frequency, monetary, tenure, product
  breadth, purchase timing, gaps, recency-of-orders…)
- **Temporal validation:** W1 (Dec 2010–Aug 2011) trains/validates; **W2
  (Mar–Nov 2011) held out** as a true out-of-time test
- Model family: logistic, random forest, gradient boosting + DummyClassifier
  baseline; tuning on **W1 only** with a recall guard
- **Final model: tuned Logistic Regression (C=0.1)** — W2 ROC-AUC **0.7332**,
  PR-AUC **0.5945**, recall **0.7941**, identifying **1,114 / 2,813 (39.6%)**
  W2 customers as high-risk
- Interpretability: `reports/ml_feature_importance.csv` + SHAP-style
  coefficient explanations; top drivers are `active_months`, `distinct_products`,
  `recency_days`, `gap_mean_days`, `total_quantity`

> Association, not causation: features indicate which signals move predicted
> churn risk; the model supports business decisions rather than dictating them.

### 6. Serving, API & deployment (Phase 7)
- **Interactive demo:** `streamlit run app/churn_demo.py` — enter a customer
  profile, get probability + risk band + key signals + a recommended
  interpretation, from the **real** tuned model.
- **Prediction API:** `uvicorn api.main:app` — `POST /predict` returns
  `{"churn_probability", "risk_band", "prediction"}`; `GET /health`, `GET /model`.
- **CI/CD:** `.github/workflows/ci.yml` (fast checks on every push) and
  `full-pipeline.yml` (opt-in full validation).
- **Deployment:** `deployment/README.md` — local run, env vars, cloud steps,
  Dockerfile; honest about limitations (no live cloud deployment running).

---

## Repository layout

```
├── pipeline/            # Phase 5 production pipeline + Phase 6 ML
│   ├── run_pipeline.py  # end-to-end orchestration (9 stages)
│   ├── validators.py    # data-quality gate + reconciliation
│   ├── ml_features.py / ml_models.py / ml_tuning.py
│   ├── run_ml.py / run_ml_tune.py
│   ├── model_export.py  # Phase 7: serialize final tuned model
│   └── tests/           # unit / integration / ML / tuning / slow
├── sql/                 # schema, loaders, 38-question analytics, verification
├── powerbi/             # .pbit template, dataset export, page spec, previews
├── app/                 # Streamlit churn demo
├── api/                 # FastAPI service
├── deployment/          # deployment guide (+ Dockerfile recipe)
├── reports/             # run manifests, reports, data-quality report, ML outputs
├── docs/                # architecture, case study, project summary, interview prep
├── .github/workflows/   # CI + full-pipeline validation
├── requirements.txt     # Phase 7 app/API deps
├── .env.example         # environment template (never commit .env)
└── README.md
```

> The course notebooks that accompany this project live under `01_…_04_` —
> see below.

---

## Quick start

```bash
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt -r sql/requirements.txt
cp .env.example .env                              # set DATABASE_URL

python pipeline/run_pipeline.py   # clean -> PostgreSQL -> SQL -> PBI dataset -> validate
python pipeline/run_ml.py         # train model family
python pipeline/run_ml_tune.py    # tune -> final model
python pipeline/model_export.py   # export artifact for demo/API

streamlit run app/churn_demo.py                # interactive demo
uvicorn api.main:app --host 0.0.0.0 --port 8000 # prediction API
python reports/generate_data_quality_report.py  # monitoring report
```

## Course notebooks (original companion material)
`01_Python_Foundations/` … `04_File_Handling_and_IO/` are the course notebooks
this project grew out of (Python basics, NumPy, Pandas, file I/O).

---

_Validation status is always reproducible: run the tests and
`sql/verify_pipeline.py` — see each layer's README for details._
