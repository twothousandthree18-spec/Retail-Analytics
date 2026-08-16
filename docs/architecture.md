# System Architecture — Retail Analytics & Customer Intelligence Platform

The diagram below is written in **Mermaid** so it is fully editable and
reproducible. Render it on [mermaid.live](https://mermaid.live), in GitHub
markdown, or via VS Code's Markdown Preview.

## Data flow (high level)

```mermaid
flowchart LR
    subgraph SOURCES["Data Sources"]
        RAW["Raw Retail Data<br/>online_retail.csv<br/>541,909 rows"]
    end

    subgraph INGEST["Phase 1-2 — Ingest & Clean"]
        CLN["Python / Pandas<br/>data cleaning + validation<br/>-> cleaned_retail_data.csv (527,390)"]
    end

    subgraph STORE["Phase 3 — Storage"]
        PG[("PostgreSQL<br/>retail_transactions 527,390<br/>+ derived tables")]
    end

    subgraph SQL["Phase 3-4 — SQL & Analytics"]
        SQL1["SQL Analytics<br/>customers / RFM / cohorts"]
        PBI["Excel & Power BI<br/>6 dashboards, 29 DAX measures"]
    end

    subgraph ML["Phase 6 — Machine Learning"]
        FEAT["Feature engineering<br/>18 features, W1/W2 windows"]
        TRN["Model training + tuning<br/>logistic C=0.1 (final)"]
    end

    subgraph SERVE["Phase 7 — Serve"]
        API["Churn Prediction API<br/>FastAPI POST /predict"]
        DEMO["Interactive Demo<br/>Streamlit"]
    end

    subgraph DEC["Consume"]
        DEC1["Business Decisions<br/>retention campaigns, RFM targeting"]
    end

    RAW --> CLN --> PG --> SQL1 & PBI
    PG --> FEAT --> TRN
    TRN --> API & DEMO
    API & DEMO --> DEC1
    SQL1 -.  "validated by\nverify_pipeline.py" .-> FEAT
```

## Component map

| Layer | Technology | Key outputs |
|---|---|---|
| Ingest & cleaning | Python 3, Pandas | `cleaned_retail_data.csv` (527,390 rows) |
| Storage | PostgreSQL 13+ | `retail_transactions`, `customers`, `rfm_segments`, `cohort_retention` |
| SQL analytics | SQL (psycopg2) | RFM segments (4,339), cohort retention (91) |
| BI / reporting | Excel, Power BI | 6 dashboards, 29 DAX measures (validated) |
| ML / churn | scikit-learn | final tuned logistic (C=0.1), W2 ROC-AUC 0.7332 |
| Serve | FastAPI, Streamlit | `POST /predict`, interactive demo |
| Quality gate | custom `validators.py` | PASS/WARNING/FAIL on every check |

## ASCII fallback

```
Raw Retail CSV (541,909)
        │  Phase 1-2: Python/Pandas cleaning + validation
        ▼
Cleaned CSV (527,390) ──► PostgreSQL (transactions + derived tables)
                              │  Phase 3-4: SQL analytics (RFM, cohorts)
                              ▼
                    SQL / Excel / Power BI (dashboards, 29 DAX measures)
                              │  Phase 6: feature engineering (18 feats)
                              ▼
                    ML churn model (logistic C=0.1, W2 ROC-AUC 0.7332)
                              │  Phase 7: serve
                              ▼
              Churn Prediction API ──► Interactive Demo (Streamlit)
                              │
                              ▼
                    Business Decisions (retention, RFM targeting)
```

_Note: every arrow in the diagram corresponds to code in this repository.
Re-run the full chain with `pipeline/run_pipeline.py` → `pipeline/run_ml.py` →
`pipeline/run_ml_tune.py`._
