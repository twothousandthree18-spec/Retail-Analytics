"""Slow end-to-end tests: full pipeline executions (opt-in).

These tests run the real pipeline end to end, including the ~5 minute notebook
cleaning stage. They are skipped unless explicitly requested so the fast suite
stays fast:

    $env:RUN_SLOW_TESTS=1; .\\.venv\\Scripts\\python.exe -m unittest discover -s pipeline/tests

Covered scenarios (per the Phase 5 requirements):
  * happy path - a complete run exits 0 and every stage succeeds;
  * idempotency - two consecutive complete runs produce consistent outputs and
    never duplicate data.

(Data-quality gating and database-unavailability are covered by the fast unit
and CLI tests in this directory.)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import psycopg2

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

import pipeline.run_pipeline as rp  # noqa: E402

GOOD_DB_URL = "postgresql://postgres:postgres@localhost:5432/retail_analysis"
PIPELINE = REPO / "pipeline" / "run_pipeline.py"


@unittest.skipUnless(os.environ.get("RUN_SLOW_TESTS") == "1",
                     "set RUN_SLOW_TESTS=1 to run the full-pipeline tests")
class FullPipelineTests(unittest.TestCase):
    def _run_cli(self, *extra, db_url=GOOD_DB_URL):
        env = os.environ.copy()
        env["DATABASE_URL"] = db_url
        env["PIPELINE_TEMP_DIR"] = os.environ.get("PIPELINE_TEMP_DIR") or str(
            Path(tempfile.gettempdir()) / "RetailAnalytics_Temp")
        return subprocess.run(
            [sys.executable, str(PIPELINE), *extra],
            cwd=str(REPO), env=env, capture_output=True, text=True, timeout=3600)

    def _manifest(self) -> dict:
        return json.loads((REPO / "reports" / "pipeline_run.json").read_text(encoding="utf-8"))

    def _assert_success_manifest(self, manifest: dict):
        self.assertEqual(manifest["status"], "SUCCESS")
        self.assertEqual(manifest["database"]["rows"], 527_390)
        self.assertEqual(manifest["cleaned"]["rows"], 527_390)
        self.assertEqual(manifest["excel"]["sheet_count"], 26)
        self.assertEqual(manifest["powerbi"]["files"]["FactSales.csv"], 527_390)
        self.assertEqual(manifest["reconciliation"]["status"], "PASS")
        self.assertEqual([s["status"] for s in manifest["stages"]],
                         ["PASS"] * 9)

    def test_happy_path_full_run(self):
        proc = self._run_cli()
        self.assertEqual(proc.returncode, 0, proc.stderr[-4000:])
        self._assert_success_manifest(self._manifest())

    def test_idempotent_second_run(self):
        proc1 = self._run_cli()
        self.assertEqual(proc1.returncode, 0, proc1.stderr[-4000:])
        m1 = self._manifest()
        self._assert_success_manifest(m1)

        proc2 = self._run_cli()
        self.assertEqual(proc2.returncode, 0, proc2.stderr[-4000:])
        m2 = self._manifest()
        self._assert_success_manifest(m2)

        self.assertNotEqual(m1["run_id"], m2["run_id"])
        self.assertEqual(m1["cleaned"], m2["cleaned"])
        self.assertEqual(m1["database"]["rows"], m2["database"]["rows"])
        self.assertEqual(m1["excel"]["sheet_count"], m2["excel"]["sheet_count"])
        self.assertEqual(m1["powerbi"]["files"], m2["powerbi"]["files"])
        self.assertEqual(m1["data_quality"]["summary"], m2["data_quality"]["summary"])
        self.assertEqual(m1["metrics"], m2["metrics"])
        self.assertEqual(m1["reconciliation"]["status"], m2["reconciliation"]["status"])

        conn = psycopg2.connect(GOOD_DB_URL, connect_timeout=15)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM retail_transactions")
                rows = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM cohort_retention")
                cohort = cur.fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(rows, 527_390)
        self.assertEqual(cohort, 91)


if __name__ == "__main__":
    unittest.main()
