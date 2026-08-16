# Interview Preparation — Retail Analytics & Customer Intelligence Platform

Practice questions grouped by topic, with the answers grounded in **this
project** (use the verified numbers). Great for data analyst, data scientist
and data-engineering interviews.

---

## 1. Data & data cleaning
1. **Walk me through how you cleaned the data.**
   Raw 541,909 rows → 527,390 cleaned. Removed cancellations by invoice prefix
   (not by negative quantity), kept negative-quantity / non-positive-price rows
   per a validated policy, handled missing CustomerID (134,658 rows excluded
   from customer-level analytics but retained for transaction-level work), and
   parsed dates with a strict format. Every rule is checked by a quality gate.
2. **Why not just drop rows with negative quantity?**
   Because cancellations are identified by `C`/`A` invoice prefixes; a negative
   quantity isn't proof of a cancellation. Dropping on quantity alone would lose
   valid data and is not reproducible. The cleaning policy is explicit and
   validated.
3. **How did you handle missing data?**
   `CustomerID` (134,658 rows, ~25%) — retained, excluded from customer-level
   metrics. `Description` (1,454 rows) — retained as NULL. ML features use
   median imputation inside the pipeline for any NaN.
4. **How did you validate data quality?**
   `pipeline/validators.py` runs schema, missing, duplicate, numeric, date and
   business-rule checks → PASS/WARNING/FAIL, then reconciles Python KPIs against
   PostgreSQL (16 metrics, all agree).

## 2. SQL
5. **Give an example of a window function you used.** Rankings for RFM
   quartile scores, and rolling/row-number queries for cohort month assignment.
6. **How did you reproduce RFM in SQL?** Recency = days since last order,
   Frequency = order count, Monetary = total spend per customer; NTILE (or
   percentile) quartiles → 4×4×4 grid → 7 business segments. SQL result matched
   pandas 100% customer-by-customer.
7. **What were the cohort retention numbers?** 13 monthly cohorts; M1 retention
   22.7%, 6-month 27.2%; Dec-2010 cohort retains 87.5% and drives 50.7% of
   cohort revenue.

## 3. RFM & customer analytics
8. **What is RFM and why does it matter?** Recency/Frequency/Monetary —
   segments customers by value and engagement; enables targeted campaigns
   (e.g., at-risk vs loyal).
9. **How is "customer" defined?** A distinct `CustomerID` (4,339 attributed
   customers). Revenue per attributed customer sums to £8,887,208.89 of the
   £10,619,986.68 total (difference = unattributed rows).

## 4. Power BI
10. **How did you model the data in Power BI?** Star schema: FactSales +
    DimDate, DimCustomer, DimProduct, DimCountry + Measures table; 4
    relationships; 29 DAX measures. Loaded via parameterised M from a dataset
    folder, then validated against PostgreSQL (24/24 PASS).
11. **Why not connect Power BI straight to the raw CSV?** Because the SQL layer
    is the validated source of truth; Power BI should *consume* the vetted
    dataset, not re-clean ad hoc.

## 5. ML & churn
12. **Explain your temporal validation.** W1 = train/tune, W2 = held-out
    out-of-time test. This mimics deployment better than a random split because
    we predict the *future*.
13. **Why logistic regression as the final model?** Simple, stable,
    interpretable, fast; tuned C=0.1 gave W2 ROC-AUC 0.7332, PR-AUC 0.5945,
    recall 0.7941 — competitive with the tree models while being easy to explain
    to the business.
14. **What is the difference between ROC-AUC and PR-AUC, and why report both?**
    ROC-AUC = rank discrimination across all thresholds (class imbalance can
    make it look good); PR-AUC = precision-recall trade-off, more sensitive to
    the positive (churn) class. With ~40% churn rate both are informative.
15. **Why a recall guard in tuning?** Optimising ROC-AUC alone can pick a model
    that rarely predicts churn; the guard keeps recall within 5pp of the best
    tuned recall so we don't miss churners.
16. **How do you interpret the model — and the caveat?** Coefficients →
    which features are associated with higher predicted churn (e.g., low
    `active_months`, high `recency_days`). Association, not causation; supports
    decisions, doesn't dictate them.

## 6. Pipeline & architecture
17. **Describe the pipeline end-to-end.** Raw CSV → clean/validate (pandas) →
    PostgreSQL load → SQL analytics (RFM, cohorts) → Power BI dataset → ML
    features → churn model → FastAPI + Streamlit. One command:
    `pipeline/run_pipeline.py`.
18. **How is the pipeline made reproducible?** Fixed random seed (42), explicit
    cleaning policy, run manifests with status + timestamps, credential-safe
    `.env`, and tests that can run with or without a database.
19. **How do you keep the repo safe from secrets?** `.env` is gitignored; only
    `.env.example` is committed; `DATABASE_URL` read from environment.

## 7. Production / deployment
20. **What does the API return?** `POST /predict` →
    `{"churn_probability", "risk_band", "prediction"}`; `GET /health`,
    `GET /model` for metadata.
21. **Why provide both a demo and an API?** Demo = business-facing exploration;
    API = programmatic scoring / integration. Both use the *same* exported model.
22. **How would you deploy this?** Streamlit Community Cloud/Render for the
    demo; containerised FastAPI (Dockerfile in `deployment/`) on any host;
    hosted PostgreSQL. Details in `deployment/README.md` — with honest
    limitations (no live deployment running in this repo).
23. **What does your CI run?** `.github/workflows/ci.yml` — fast checks
    (compile, unit tests, ML tests, API smoke tests, DQ report). A separate
    `full-pipeline.yml` (manual/tag) runs the entire chain with a real DB.

## 8. Behavioural / judgment
24. **Tell me about a time a result didn't match.** The full slow pipeline once
    failed at the PostgreSQL load stage during a regression run; I repaired the
    stack, rebuilt the derived tables, and re-ran the whole validation suite —
    all checks passed before freezing the phase.
25. **Why did you make the demo vs. writing a report?** A recruiter-facing
    portfolio needs a *clickable* artifact; a live model beats a static chart.
26. **What would you do differently next time?** Deploy for real with auth +
    monitoring, add drift detection, and use a cloud data warehouse for larger
    datasets.
