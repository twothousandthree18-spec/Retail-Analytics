"""Automated tests for the Phase 6.1 tuning layer.

Fast unit tests cover the selection rules and the search-space structure on
synthetic metrics; one real-data smoke test tunes only the (cheap) logistic
model on W1 and verifies the temporal test still respects W2 as held-out.

Run from the repository root:

    .\\.venv\\Scripts\\python.exe -m unittest pipeline.tests.test_pipeline_ml_tune -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
from sklearn.model_selection import StratifiedKFold

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "pipeline"))

from pipeline.ml_features import (WINDOW_W1, WINDOW_W2,  # noqa: E402
                                  build_features, build_target, load_cleaned)
from pipeline.ml_models import RANDOM_STATE, temporal_metrics  # noqa: E402
from pipeline.ml_tuning import (SEARCH_SPACES, decide_final,  # noqa: E402
                                select_best_tuned, tune_models)

LOG = {"roc_auc": 0.753, "pr_auc": 0.696, "recall": 0.808, "f1": 0.731,
       "accuracy": 0.700, "precision": 0.667}
TUNED_BETTER = {"roc_auc": 0.770, "pr_auc": 0.720, "recall": 0.815, "f1": 0.740,
                "accuracy": 0.710, "precision": 0.675}
TUNED_LOW_RECALL = dict(TUNED_BETTER, recall=0.700)


class SearchSpaceTests(unittest.TestCase):
    def test_three_models_tuned(self):
        self.assertEqual(set(SEARCH_SPACES), {"logistic", "random_forest",
                                              "gradient_boosting"})

    def test_search_space_is_small(self):
        total = 0
        for _, grid in SEARCH_SPACES.values():
            combos = 1
            for values in grid.values():
                combos *= len(values)
            total += combos
        # 4 + 8 + 8 = 20 combinations — deliberately lightweight.
        self.assertEqual(total, 20)
        for _, grid in SEARCH_SPACES.values():
            self.assertLessEqual(sum(len(v) for v in grid.values()), 6)


class SelectionRuleTests(unittest.TestCase):
    def test_best_tuned_by_roc_auc(self):
        tuned = {
            "logistic": {"cv": LOG},
            "random_forest": {"cv": TUNED_BETTER},
        }
        self.assertEqual(select_best_tuned(tuned), "random_forest")

    def test_switch_when_improves_and_recall_ok(self):
        d = decide_final(LOG, "logistic", TUNED_BETTER)
        self.assertTrue(d["switch"])
        self.assertTrue(d["improves_roc"])
        self.assertTrue(d["recall_ok"])
        self.assertEqual(d["final_model"], "logistic")

    def test_keep_current_when_recall_harmed(self):
        d = decide_final(LOG, "logistic", TUNED_LOW_RECALL)
        self.assertFalse(d["switch"])
        self.assertEqual(d["final_model"], "logistic")

    def test_keep_current_when_no_improvement(self):
        d = decide_final(TUNED_BETTER, "logistic", LOG)
        self.assertFalse(d["switch"])
        self.assertEqual(d["final_model"], "logistic")


class RealDataSmokeTests(unittest.TestCase):
    """Tune only logistic (cheap) on real W1 data; W2 stays untouched."""

    @classmethod
    def setUpClass(cls):
        df = load_cleaned()
        w1 = build_features(df, WINDOW_W1)
        cls.X = w1[[c for c in w1.columns if c != "CustomerID"]]
        cls.y = build_target(df, WINDOW_W1, w1).to_numpy()

    def test_logistic_tuning_runs_and_metrics_in_range(self):
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
        tuned = tune_models(self.X, self.y, cv)
        self.assertIn("logistic", tuned)
        m = tuned["logistic"]["cv"]
        self.assertGreaterEqual(m["roc_auc"], 0.5)
        self.assertLessEqual(m["roc_auc"], 1.0)
        self.assertIn("model__C", tuned["logistic"]["best_params"])

    def test_tuned_logistic_w2_is_temporal(self):
        # Model fit on W1 must never train on W2 rows.
        df = load_cleaned()
        w2 = build_features(df, WINDOW_W2)
        X2 = w2[[c for c in w2.columns if c != "CustomerID"]]
        y2 = build_target(df, WINDOW_W2, w2).to_numpy()
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
        tuned = tune_models(self.X, self.y, cv)
        m = temporal_metrics(tuned["logistic"]["estimator"], X2, y2)
        self.assertGreaterEqual(m["roc_auc"], 0.5)
        self.assertEqual(len(y2), 2813)


if __name__ == "__main__":
    unittest.main()
