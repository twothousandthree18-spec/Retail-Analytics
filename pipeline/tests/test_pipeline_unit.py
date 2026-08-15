"""Fast unit tests for the pipeline modules (no full pipeline execution).

Run from the repository root:

    .\\.venv\\Scripts\\python.exe -m unittest discover -s pipeline/tests
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pipeline.config as cfg  # noqa: E402
import pipeline.run_pipeline as rp  # noqa: E402
import pipeline.validators as v  # noqa: E402

GOOD_DB_URL = "postgresql://postgres:postgres@localhost:5432/retail_analysis"


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_missing_database_url_raises(self):
        with mock.patch.object(cfg, "load_dotenv"):
            os.environ.pop("DATABASE_URL", None)
            with self.assertRaises(ValueError):
                cfg.build_config()

    def test_database_url_from_env(self):
        with mock.patch.object(cfg, "load_dotenv"):
            os.environ["DATABASE_URL"] = GOOD_DB_URL
            self.assertEqual(cfg.build_config().database_url, GOOD_DB_URL)

    def test_cli_override_wins_over_env(self):
        with mock.patch.object(cfg, "load_dotenv"):
            os.environ["DATABASE_URL"] = GOOD_DB_URL
            c = cfg.build_config(db_url="postgresql://cli:cli@dbhost/retail")
            self.assertEqual(c.database_url, "postgresql://cli:cli@dbhost/retail")

    def test_input_data_path_env(self):
        with mock.patch.object(cfg, "load_dotenv"):
            os.environ["DATABASE_URL"] = GOOD_DB_URL
            os.environ["INPUT_DATA_PATH"] = str(REPO / "online_retail.csv")
            self.assertEqual(cfg.build_config().input_path, (REPO / "online_retail.csv").resolve())

    def test_output_dir_env(self):
        with mock.patch.object(cfg, "load_dotenv"):
            os.environ["DATABASE_URL"] = GOOD_DB_URL
            os.environ["OUTPUT_DIR"] = str(REPO / "reports")
            self.assertEqual(cfg.build_config().output_dir, (REPO / "reports").resolve())


class CsvSummaryTests(unittest.TestCase):
    def test_counts_raw_source(self):
        rows, cols = rp.csv_summary(cfg.SOURCE_CSV)
        self.assertEqual(rows, 541_909)
        self.assertEqual(cols, 8)


class DataQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = v.read_cleaned()

    def test_real_cleaned_data_passes_gate(self):
        dq = v.run_data_quality(self.df)
        self.assertIn(dq["status"], (v.PASS, v.WARNING))
        self.assertEqual(dq["summary"]["duplicate_rows"], 0)
        self.assertEqual(dq["summary"]["invalid_dates"], 0)
        self.assertEqual(dq["summary"]["cancellations_remaining"], 0)
        self.assertEqual(dq["summary"]["distinct_customers"], 4_339)

    def test_missing_required_column_fails(self):
        dq = v.run_data_quality(self.df.drop(columns=["CustomerID"]))
        self.assertEqual(dq["status"], v.FAIL)
        self.assertTrue(any(
            c["name"].startswith("Schema") and c["status"] == v.FAIL for c in dq["checks"]))

    def test_duplicate_rows_fail(self):
        dup = pd.concat([self.df, self.df.iloc[:5]], ignore_index=True)
        dq = v.run_data_quality(dup)
        self.assertEqual(dq["status"], v.FAIL)
        self.assertEqual(dq["summary"]["duplicate_rows"], 5)

    def test_empty_dataframe_fails(self):
        dq = v.run_data_quality(pd.DataFrame())
        self.assertEqual(dq["status"], v.FAIL)


class PythonMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = v.python_metrics(v.read_cleaned())

    def test_benchmark_values(self):
        self.assertEqual(self.m["revenue"], 10_619_986.68)
        self.assertEqual(self.m["orders"], 22_064)
        self.assertEqual(self.m["customers"], 4_339)
        self.assertEqual(self.m["products"], 3_947)
        self.assertEqual(self.m["units"], 5_438_062)
        self.assertEqual(self.m["aov"], 481.33)
        self.assertEqual(self.m["repeat_customers"], 2_845)
        self.assertEqual(self.m["customer_revenue"], 8_887_208.89)
        self.assertEqual(self.m["cohort_customers"], 4_339)

    def test_rfm_segments_cover_every_customer(self):
        self.assertEqual(sum(self.m["rfm"].values()), 4_339)
        self.assertEqual(len(self.m["rfm"]), 7)


class ExcelMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = v.excel_metrics(cfg.EXCEL_WORKBOOK)

    def test_workbook_kpis(self):
        self.assertEqual(self.m["revenue"], 10_619_986.68)
        self.assertEqual(self.m["orders"], 22_064)
        self.assertEqual(self.m["customers"], 4_339)
        self.assertEqual(self.m["units"], 5_438_062)
        self.assertAlmostEqual(self.m["aov"], 481.3264, places=2)

    def test_excel_products_are_description_based(self):
        self.assertEqual(self.m["products"], 4_190)


class PbiMetricsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = v.pbi_metrics(cfg.PBI_DATASET_DIR)

    def test_dataset_kpis(self):
        self.assertEqual(self.m["revenue"], 10_619_986.68)
        self.assertEqual(self.m["orders"], 22_064)
        self.assertEqual(self.m["customers"], 4_339)
        self.assertEqual(self.m["products"], 3_947)
        self.assertEqual(self.m["repeat_customers"], 2_845)
        self.assertEqual(self.m["cohort_customers"], 4_339)


_BENCH = {
    "revenue": 10_619_986.68, "orders": 22_064, "customers": 4_339,
    "products": 3_947, "products_desc": 4_190, "units": 5_438_062, "aov": 481.33,
    "repeat_customers": 2_845, "customer_revenue": 8_887_208.89,
    "cohort_customers": 4_339,
}


class ReconcileTests(unittest.TestCase):
    def test_real_cross_system_reconcile_passes(self):
        py = v.python_metrics(v.read_cleaned())
        excel = v.excel_metrics(cfg.EXCEL_WORKBOOK)
        pbi = v.pbi_metrics(cfg.PBI_DATASET_DIR)
        try:
            conn = rp._connect(cfg.build_config())
        except Exception as exc:  # noqa: BLE001
            self.skipTest(f"database unavailable: {exc}")
        try:
            sql = v.sql_metrics(conn)
        finally:
            conn.close()
        recon = v.reconcile(py, sql, excel, pbi)
        failed = [r for r in recon["rows"] if r["status"] == v.FAIL]
        self.assertEqual(recon["status"], v.PASS, failed)

    def test_reconcile_detects_mismatch(self):
        py = dict(_BENCH, rfm={})
        sql = dict(py)
        sql["revenue"] = 10_100_000.0
        self.assertEqual(v.reconcile(py, sql, None, None)["status"], v.FAIL)

    def test_reconcile_repeat_customers_excel_quirk_is_warning_not_fail(self):
        py = dict(_BENCH, rfm={})
        sql = dict(py)
        excel = dict(py, products=4_190, products_desc=4_190, repeat_customers=3_059, rfm={})
        pbi = dict(py)
        recon = v.reconcile(py, sql, excel, pbi)
        self.assertEqual(recon["status"], v.PASS)
        row = next(r for r in recon["rows"] if r["metric"] == "Repeat Customers")
        self.assertEqual(row["status"], v.WARNING)


class PipelineGateTests(unittest.TestCase):
    """Pipeline-level behaviour tested fast by mocking the notebook-heavy stage."""

    def _make_config(self, **kw) -> cfg.Config:
        defaults = dict(
            input_path=cfg.SOURCE_CSV,
            output_dir=Path(tempfile.mkdtemp(prefix="pipeline_test_out_",
                                             dir=self._test_runs())),
            database_url=GOOD_DB_URL,
            skip_powerbi=False,
            skip_excel=False,
            debug=False,
            temp_dir=Path(os.environ.get("PIPELINE_TEMP_DIR")
                          or Path(tempfile.gettempdir()) / cfg.TEMP_WORKSPACE),
        )
        defaults.update(kw)
        return cfg.Config(**defaults)

    def _test_runs(self) -> str:
        base = Path(os.environ.get("PIPELINE_TEMP_DIR")
                    or Path(tempfile.gettempdir()) / cfg.TEMP_WORKSPACE)
        d = base / "test_runs"
        d.mkdir(parents=True, exist_ok=True)
        return str(d)

    def _run(self, config: cfg.Config) -> int:
        log = rp.PipelineLogger(config.output_dir / "test.log")
        try:
            return rp.pipeline(config, log)
        finally:
            log.close()

    @staticmethod
    def _fast_clean(ctx: dict) -> str:
        ctx["clean_seconds"] = 0.0
        df = v.read_cleaned()
        ctx["df"] = df
        ctx["cleaned"] = {"path": str(cfg.CLEANED_CSV), "rows": len(df), "columns": len(df.columns)}
        return f"{len(df):,} rows"

    @staticmethod
    def _bad_clean(ctx: dict) -> str:
        ctx["clean_seconds"] = 0.0
        df = pd.DataFrame({"InvoiceNo": ["C1"], "StockCode": ["X"], "Quantity": [1]})
        ctx["df"] = df
        ctx["cleaned"] = {"path": "bad", "rows": 1, "columns": 3}
        return "1 rows"

    def test_data_quality_failure_stops_pipeline(self):
        config = self._make_config()
        with mock.patch.object(rp, "stage_clean", new=self._bad_clean):
            with mock.patch.object(rp, "stage_postgresql") as pg:
                code = self._run(config)
                pg.assert_not_called()
        self.assertEqual(code, 1)
        manifest = json.loads((config.output_dir / "pipeline_run.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "FAILED")
        self.assertEqual(manifest["failed_stage"], "DATA QUALITY")
        self.assertTrue((config.output_dir / "pipeline_run_report.md").exists())

    def test_database_unavailable_stops_cleanly(self):
        config = self._make_config(database_url="postgresql://u:p@localhost:59999/none")
        with mock.patch.object(rp, "stage_clean", new=self._fast_clean):
            code = self._run(config)
        self.assertEqual(code, 1)
        manifest = json.loads((config.output_dir / "pipeline_run.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "FAILED")
        self.assertEqual(manifest["failed_stage"], "POSTGRESQL LOAD")


if __name__ == "__main__":
    unittest.main()
