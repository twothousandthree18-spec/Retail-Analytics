# Data Analysis Class — June 2026

Course notebooks and materials for learning Python for data analysis.

## Folder Structure

```
├── 01_Python_Foundations/        # Python basics: types, variables, loops, conditionals, strings, lists, dicts, functions
├── 02_NumPy_and_Arrays/          # NumPy arrays: creation, slicing, filtering, broadcasting, stats, random
├── 03_Pandas_Data_Analysis/      # Pandas: DataFrames, Excel/CSV I/O, filtering, grouping, quiz app, banking
├── 04_File_Handling_and_IO/      # File I/O: read/write/append, JSON, CSV module, error handling, OS ops
├── data/                         # Shared datasets used across exercises
└── README.md
```

## Notebooks

| # | Notebook | Topics |
|---|----------|--------|
| 1 | `01_Python_Foundations/01_Python_Foundations.ipynb` | Data types, variables, input, f-strings, operators, conditionals, string methods, loops, lists, dicts, tuples, sets, list comprehensions, functions |
| 2 | `02_NumPy_and_Arrays/02_NumPy_and_Arrays.ipynb` | Array creation, properties, reshape, slicing, broadcasting, filtering, statistics, random |
| 3 | `03_Pandas_Data_Analysis/03_Pandas_Data_Analysis.ipynb` | Reading Excel/CSV, DataFrame exploration, filtering, missing data, sorting, grouping, quiz app, banking system |
| 4 | `04_File_Handling_and_IO/04_File_Handling_and_IO.ipynb` | File read/write/append, JSON, CSV module, error handling, OS module, user registration system |

## Data Files

- `03_Pandas_Data_Analysis/` — VendorProducts.xlsx, bank.csv, Questions.csv, StudentAgeData.xlsx/.csv, FetcheData.html
- `04_File_Handling_and_IO/` — introduction.txt, welcome.txt, UsersDatabase.txt
- `data/` — industry.csv, Analysis.xlsx

## Scripts

- `01_Python_Foundations/If_Elif.py` — Conditionals: arithmetic calculator + coffee machine
- `01_Python_Foundations/StringFormatting.py` — f-string formatting with user input

## Retail Analytics Project

An end-to-end data analysis project on the online retail dataset (527,390 cleaned
transaction lines), built in two layers:

### 1. Python / Pandas pipeline (Excel report)
`OnlineRetail cleaning.ipynb` cleans the raw data and produces
`Retail_Analysis_Report.xlsx` with **26 sheets**, including:
`Summary Dashboard`, `Sales Analysis`, `Customer Analysis`, `Product Analysis`,
`Time Analysis`, and the `RFM Customer Segmentation` sheet (Recency / Frequency /
Monetary quartile scores + 7 customer segments for 4,339 customers). Phase 4
appends three cohort sheets without touching the originals: `Customer Cohort
Analysis`, `Cohort Customer Counts` and `Cohort Revenue Analysis` (built by
`reports/build_cohort_excel.py` at the OOXML level — the original 23 sheets are
preserved byte-for-byte).

The notebook also exports the cleaned dataset to `data/cleaned_retail_data.csv`
(last cell), which is the single source of truth for the SQL layer.

### 2. PostgreSQL + Advanced SQL analytics layer
The `sql/` folder re-analyses the same cleaned data in PostgreSQL and
independently **reproduces/validates** the Python results:

- `sql/schema.sql` — `retail_transactions` table + indexes
- `sql/load_data.py` — reproducible bulk loader (credential-safe via `DATABASE_URL`)
- `sql/01_sales_analysis.sql` … `sql/06_cohort_retention_analysis.sql` — 38 business
  questions answered with CTEs, window functions and time intelligence
- `sql/05_advanced_analytics.sql` — RFM segmentation reproduced in SQL
- `sql/06_cohort_retention_analysis.sql` — Phase 4: customer cohorts by
  first-purchase month with a retention matrix (M0..M12), revenue-by-age and
  lifecycle summaries
- `sql/cohort_validation.py` — SQL vs pandas reconcile of the cohort tables (12/12 PASS)
- `sql/generate_insights_report.py` — machine-generated `sql/insights_report.md`
- `sql/verify_pipeline.py` — automated verification (currently **all checks pass**)

Key results (validated identically in both engines): total revenue **£10,619,986.68**,
total orders **22,064**, total customers **4,339**, average order value **£481.33**,
UK = 84.55% of revenue, 1,130 customers generate 80% of revenue, and SQL/pandas
RFM segments agree **100% customer-by-customer**.

**Phase 4 cohort findings** (SQL = pandas, to the penny): 4,339 customers across
13 cohorts (Dec 2010 – Dec 2011); M1 retention **22.7%**, 6-month retention
**27.2%**, months 3–10 plateau at 26–30%; the founding Dec-2010 cohort retains
**87.5%** of customers, generates **£5,087 / customer** and **50.7%** of cohort
revenue. `reports/cohort_insights_report.md` is the machine-generated narrative.

### 3. Power BI retail analytics layer

The `powerbi/` folder adds a recruiter-facing Power BI deliverable built **on top
of the validated SQL layer** (no re-cleaning, no fabricated figures):

- `powerbi/Retail_Analysis.pbit` — Power BI template: star-schema model
  (FactSales + 4 dimensions) **plus the Phase 4 cohort tables** (CohortRetention,
  CohortSummary), 4 relationships, **35 DAX measures** (incl. 6 cohort measures),
  parameterised M queries that load straight from `powerbi/dataset/`.
- `powerbi/scripts/export_pbi_dataset.py` + `validate_pbi.py` — regenerate and
  reconcile the dataset against PostgreSQL (37 checks, all PASS).
- `powerbi/pages.md`, `powerbi/previews/` — page build spec + static previews of
  all 6 report pages rendered with real data, including the new **Customer
  Retention** page (retention heatmap, decay curve, cohort lifecycle). No Power
  BI Desktop in the authoring environment, so pages are built from spec rather
  than shipped untested.
- `powerbi/PHASE3_REPORT.md` — full deliverables, model verification and
  validation report. Open the `.pbit`, point `DatasetFolder` at
  `powerbi/dataset/`, and Mark as date table on DimDate.

See `sql/README.md` for setup, usage and details.

### Setup (SQL layer only)

```bash
cp .env.example .env          # then fill in your DATABASE_URL
pip install -r sql/requirements.txt
python sql/load_data.py       # load the cleaned CSV into PostgreSQL
python sql/verify_pipeline.py # run all checks
```
