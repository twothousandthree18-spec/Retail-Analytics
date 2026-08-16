"""Fast tests for the Phase 7 API + model export (no full pipeline run).

Run from the repository root:

    .\\.venv\\Scripts\\python.exe -m unittest discover -s tests
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "pipeline"))

from fastapi.testclient import TestClient  # noqa: E402

import api.main as api  # noqa: E402
import model_export as me  # noqa: E402


class ModelExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loaded = me.load_model(me.default_model_dir())

    def test_metadata_reproduces_final_model(self):
        md = self.loaded.metadata
        self.assertEqual(md["final_model"], "logistic")
        self.assertEqual(md["source"], "tuned_logistic")
        self.assertEqual(md["hyperparameters"], {"model__C": 0.1})
        self.assertEqual(md["random_state"], 42)

    def test_metadata_contains_verified_w2_metrics(self):
        w2 = self.loaded.metadata["w2_metrics"]
        self.assertAlmostEqual(w2["roc_auc"], 0.7332, places=4)
        self.assertAlmostEqual(w2["pr_auc"], 0.5945, places=4)
        self.assertAlmostEqual(w2["recall"], 0.7941, places=4)

    def test_feature_columns_match_pipeline(self):
        self.assertEqual(len(self.loaded.metadata["feature_columns"]), 18)

    def test_predict_single_subset(self):
        r = me.predict_single(
            self.loaded.model,
            {"recency_days": 120, "active_months": 2, "frequency": 2,
             "monetary": 150.0, "distinct_products": 5, "total_quantity": 20,
             "gap_mean_days": 60, "orders_last_30d": 0})
        self.assertGreaterEqual(r["churn_probability"], 0.0)
        self.assertLessEqual(r["churn_probability"], 1.0)
        self.assertIn(r["risk_band"], ("LOW", "MEDIUM", "HIGH"))
        self.assertIn(r["prediction"], (0, 1))

    def test_predict_single_unknown_feature_raises(self):
        with self.assertRaises(ValueError):
            me.predict_single(self.loaded.model, {"not_a_feature": 1})


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(api.app)

    def test_health(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["model"], "ready")

    def test_model_info(self):
        resp = self.client.get("/model")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["final_model"], "logistic")
        self.assertAlmostEqual(resp.json()["w2_metrics"]["roc_auc"], 0.7332,
                               places=4)

    def test_predict_ok(self):
        resp = self.client.post(
            "/predict",
            json={"features": {"recency_days": 120, "active_months": 2,
                               "frequency": 2}})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(set(body), {"churn_probability", "risk_band",
                                     "prediction"})

    def test_predict_unknown_feature_422(self):
        resp = self.client.post("/predict",
                                json={"features": {"nope": 1}})
        self.assertEqual(resp.status_code, 422)
        self.assertIn("unknown feature", resp.json()["detail"])

    def test_predict_empty_422(self):
        resp = self.client.post("/predict", json={"features": {}})
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
