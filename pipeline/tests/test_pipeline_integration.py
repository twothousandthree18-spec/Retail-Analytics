"""Fast end-to-end CLI tests for failure handling (exit codes, no silent pass).

Each test shells out to ``pipeline/run_pipeline.py`` exactly as a user would.
These tests do NOT execute the notebook, so they stay fast: the failure cases
they exercise are all detected before or without a full cleaning run.

Run from the repository root:

    .\\.venv\\Scripts\\python.exe -m unittest discover -s pipeline/tests
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PIPELINE = REPO / "pipeline" / "run_pipeline.py"
GOOD_DB_URL = "postgresql://postgres:postgres@localhost:5432/retail_analysis"


def _test_runs_dir() -> str:
    """Test scratch lives under the configured temp workspace when set."""
    base = Path(os.environ.get("PIPELINE_TEMP_DIR") or tempfile.gettempdir())
    d = base / "RetailAnalytics_Temp" / "test_runs"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


class CliFailureTests(unittest.TestCase):
    def _run(self, *args, remove_env=(), **env_set):
        env = os.environ.copy()
        for k in remove_env:
            env.pop(k, None)
        env.update({k: str(v) for k, v in env_set.items()})
        # Isolate failure artifacts from the real reports/ directory.
        env["OUTPUT_DIR"] = tempfile.mkdtemp(prefix="pipeline_cli_test_",
                                             dir=_test_runs_dir())
        proc = subprocess.run(
            [sys.executable, str(PIPELINE), *args],
            cwd=str(REPO), env=env, capture_output=True, text=True, timeout=600)
        return proc

    def test_missing_input_dataset_exits_1(self):
        proc = self._run("--input", str(REPO / "does_not_exist.csv"), "--db-url", GOOD_DB_URL)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("missing source dataset", proc.stderr + proc.stdout)

    def test_missing_database_url_exits_1(self):
        proc = self._run("--input", str(REPO / "online_retail.csv"),
                         remove_env=("DATABASE_URL",))
        self.assertEqual(proc.returncode, 1)
        self.assertIn("DATABASE_URL is not set", proc.stderr + proc.stdout)


if __name__ == "__main__":
    unittest.main()
