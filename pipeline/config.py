"""Pipeline configuration — resolve inputs from CLI flags and environment.

Environment variables supported (never store credentials in source):

    DATABASE_URL      PostgreSQL connection string (required for stages 4-9).
    INPUT_DATA_PATH   Path to the raw source dataset (default: <repo>/online_retail.csv).
    OUTPUT_DIR        Directory for run manifests, reports and logs (default: <repo>/reports).
    PIPELINE_TEMP_DIR Root directory for heavy/temporary pipeline processing
                      (notebook scratch, temp workbooks, test workspaces).
                      Default: <system temp>/RetailAnalytics_Temp. Point this at a
                      large drive (e.g. D:\\RetailAnalytics_Temp) so temporary work
                      never fills the drive holding the repository.

CLI flags override environment variables. `.env` is loaded from the repo root if
present; `.env` itself must never be committed.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---- temporary workspace layout (heavy processing only) ----
TEMP_WORKSPACE = "RetailAnalytics_Temp"
TEMP_SUBDIRS = ["pipeline_runs", "test_runs", "workspaces", "generated", "postgres_temp"]

# ---- project fixed paths ----

# ---- project fixed paths ----
NOTEBOOK = REPO_ROOT / "OnlineRetail cleaning.ipynb"
SOURCE_CSV = REPO_ROOT / "online_retail.csv"
CLEANED_CSV = REPO_ROOT / "data" / "cleaned_retail_data.csv"
EXCEL_WORKBOOK = REPO_ROOT / "Retail_Analysis_Report.xlsx"
SQL_DIR = REPO_ROOT / "sql"
PBI_SCRIPTS_DIR = REPO_ROOT / "powerbi" / "scripts"
PBI_DATASET_DIR = REPO_ROOT / "powerbi" / "dataset"
REPORTS_DIR = REPO_ROOT / "reports"

# Every SQL analytics script executed by stage 05 (schema first, then 01..06).
SQL_SCRIPTS = [
    "schema.sql",
    "01_sales_analysis.sql",
    "02_customer_analysis.sql",
    "03_product_analysis.sql",
    "04_time_analysis.sql",
    "05_advanced_analytics.sql",
    "06_cohort_retention_analysis.sql",
]

# Power BI dataset files produced by stage 06 with their validated baseline
# row counts (used as a structural integrity check; the existing
# powerbi/scripts/validate_pbi.py performs the deep reconciliation).
PBI_DATASET_FILES = {
    "FactSales.csv": 527_390,
    "DimDate.csv": 730,
    "DimCustomer.csv": 4_339,
    "DimProduct.csv": 3_947,
    "DimCountry.csv": 38,
    "CohortRetention.csv": 91,
    "CohortSummary.csv": 13,
}

COHORT_CSVS = ("CohortRetention.csv", "CohortSummary.csv")

# Expected workbook sheet count after the Phase 4 cohort sheets are appended.
EXPECTED_EXCEL_SHEETS = 26


@dataclass
class Config:
    input_path: Path
    output_dir: Path
    database_url: str
    skip_powerbi: bool
    skip_excel: bool
    debug: bool
    temp_dir: Path

    def __post_init__(self) -> None:
        self.input_path = Path(self.input_path).resolve()
        self.output_dir = Path(self.output_dir).resolve()
        self.temp_dir = Path(self.temp_dir).resolve()


def build_config(
    *,
    input_path: str | None = None,
    db_url: str | None = None,
    skip_powerbi: bool = False,
    skip_excel: bool = False,
    debug: bool = False,
) -> Config:
    """Resolve the effective configuration from env vars and CLI overrides."""
    load_dotenv(REPO_ROOT / ".env")

    raw_input = input_path or os.environ.get("INPUT_DATA_PATH") or str(SOURCE_CSV)
    out_dir = os.environ.get("OUTPUT_DIR") or str(REPORTS_DIR)
    temp_dir = os.environ.get("PIPELINE_TEMP_DIR") or str(
        Path(tempfile.gettempdir()) / TEMP_WORKSPACE)

    url = db_url or os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError(
            "DATABASE_URL is not set.\n"
            "  Copy .env.example to .env and fill in the connection string, or pass --db-url."
        )

    return Config(
        input_path=Path(raw_input),
        output_dir=Path(out_dir),
        database_url=url,
        skip_powerbi=skip_powerbi,
        skip_excel=skip_excel,
        debug=debug,
        temp_dir=Path(temp_dir),
    )


def temp_subdir(config: Config, name: str) -> Path:
    """Return (and create) one of the configured temporary sub-workspaces."""
    if name not in TEMP_SUBDIRS:
        raise ValueError(f"unknown temporary workspace: {name!r} "
                         f"(valid: {', '.join(TEMP_SUBDIRS)})")
    path = config.temp_dir / name
    path.mkdir(parents=True, exist_ok=True)
    return path
