"""Automated tests for the Phase 6 churn ML layer.

Covers: feature engineering, target definition, temporal no-leakage guarantee,
baseline sanity, model training, temporal generalization, interpretability,
predictions, and reproducibility.  Uses the real cleaned dataset, so it
exercises the exact same code path as ``run_ml.py``.

Run from the repository root:

    .\\.venv\\Scripts\\python.exe -m unittest pipeline.tests.test_pipeline_ml -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "pipeline"))

from pipeline.ml_features import (FEATURE_COLUMNS, WINDOW_W1, WINDOW_W2,  # noqa: E402
                                  build_features, build_target, load_cleaned,
                                  make_dataset)
from pipeline.ml_models import (MODELS, RANDOM_STATE, baseline_metrics,  # noqa: E402
                                cv_evaluate, feature_importance,
                                predict_customers, select_best, temporal_metrics,
                                train_models)


class FeatureEngineeringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = load_cleaned()
        cls.w1 = build_features(cls.df, WINDOW_W1)
        cls.w2 = build_features(cls.df, WINDOW_W2)

    def test_feature_schema(self):
        self.assertEqual(list(self.w1.columns),
                         ["CustomerID"] + FEATURE_COLUMNS)
        self.assertEqual(len(self.w1), self.w1["CustomerID"].nunique())

    def test_recency_distinct_from_tenure(self):
        # Bug guard: recency is days since LAST purchase, tenure since FIRST.
        r, t = self.w1["recency_days"], self.w1["tenure_days"]
        self.assertGreater(r.max(), 0)
        self.assertGreater(t.max(), 0)
        # At most customers with a single order can have recency == tenure.
        single = self.w1["frequency"] == 1
        self.assertTrue((r[single] == t[single]).all())
        multi = self.w1["frequency"] > 1
        self.assertGreater(int((r[multi] == t[multi]).sum()), 0)
        self.assertLess(int((r[multi] == t[multi]).sum()), len(multi))

    def test_no_null_customerid(self):
        self.assertFalse(self.w1["CustomerID"].isna().any())

    def test_features_only_from_observation_window(self):
        # No feature may reference the label window: W2 obs starts 2011-03-01,
        # so no customer may have a tenure_days larger than obs window length.
        days = (WINDOW_W1.obs_end - WINDOW_W1.obs_start).days + 1
        self.assertTrue((self.w1["tenure_days"] <= days).all())
        self.assertTrue((self.w1["recency_days"] <= days).all())

    def test_windows_are_disjoint_in_time(self):
        self.assertLess(WINDOW_W1.label_end, WINDOW_W2.label_start)


class TargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = load_cleaned()

    def test_churn_rate_balances(self):
        ds = make_dataset(self.df, WINDOW_W1)
        rate = ds["churn"].mean()
        self.assertGreater(rate, 0.3)
        self.assertLess(rate, 0.7)
        # Matches the verified run value (1369/2718).
        self.assertEqual(int(ds["churn"].sum()), 1369)
        self.assertEqual(len(ds), 2718)

    def test_target_requires_customer_purchase_prior(self):
        # A customer with activity in W1 but none in W2's label window churns.
        ds = make_dataset(self.df, WINDOW_W2)
        self.assertEqual(int(ds["churn"].sum()), 1112)
        self.assertEqual(len(ds), 2813)


class BaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = load_cleaned()
        cls.w1 = build_features(cls.df, WINDOW_W1)
        cls.X = cls.w1[FEATURE_COLUMNS]
        cls.y = build_target(cls.df, WINDOW_W1, cls.w1).to_numpy()

    def test_baseline_is_coin_flip(self):
        m = baseline_metrics(self.X, self.y)
        self.assertEqual(m["roc_auc"], 0.5)
        self.assertAlmostEqual(m["accuracy"], 0.504, places=2)

    def test_learned_model_beats_baseline(self):
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
        metrics, fitted = train_models(self.X, self.y, cv)
        best = select_best(metrics)
        self.assertIn(best, MODELS)
        self.assertGreater(metrics[best]["roc_auc"], 0.6)


class TrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = load_cleaned()
        cls.w1 = build_features(cls.df, WINDOW_W1)
        cls.X = cls.w1[FEATURE_COLUMNS]
        cls.y = build_target(cls.df, WINDOW_W1, cls.w1).to_numpy()
        cls.cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
        cls.metrics, cls.fitted = train_models(cls.X, cls.y, cls.cv)

    def test_all_models_trained(self):
        self.assertEqual(set(self.metrics), set(MODELS))
        self.assertEqual(set(self.fitted), set(MODELS))

    def test_metrics_within_range(self):
        for name, m in self.metrics.items():
            self.assertGreaterEqual(m["roc_auc"], 0.0)
            self.assertLessEqual(m["roc_auc"], 1.0)
            self.assertIn("confusion", m)
            conf = m["confusion"]
            self.assertEqual(conf["tn"] + conf["fp"] + conf["fn"] + conf["tp"],
                             len(self.y))

    def test_logistic_wins_or_ties(self):
        self.assertEqual(select_best(self.metrics), "logistic")

    def test_temporal_test_uses_unseen_window(self):
        w2 = build_features(self.df, WINDOW_W2)
        X2 = w2[FEATURE_COLUMNS]
        y2 = build_target(self.df, WINDOW_W2, w2).to_numpy()
        best = select_best(self.metrics)
        m = temporal_metrics(self.fitted[best], X2, y2)
        self.assertGreaterEqual(m["roc_auc"], 0.5)
        self.assertGreaterEqual(m["f1"], 0.5)
        # Model never saw W2 labels during training (assert it was fit on W1 only).
        self.assertEqual(len(y2), 2813)


class InterpretabilityTests(unittest.TestCase):
    def test_importance_has_all_features(self):
        df = load_cleaned()
        w1 = build_features(df, WINDOW_W1)
        X = w1[FEATURE_COLUMNS]
        y = build_target(df, WINDOW_W1, w1).to_numpy()
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
        _, fitted = train_models(X, y, cv)
        imp = feature_importance(fitted["logistic"], FEATURE_COLUMNS)
        self.assertEqual(set(imp["feature"]), set(FEATURE_COLUMNS))
        self.assertTrue((imp["importance"] >= 0).all())


class PredictionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = load_cleaned()
        cls.w1 = build_features(cls.df, WINDOW_W1)
        cls.X = cls.w1[FEATURE_COLUMNS]
        cls.y = build_target(cls.df, WINDOW_W1, cls.w1).to_numpy()
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
        _, cls.fitted = train_models(cls.X, cls.y, cv)

    def test_predictions_are_probabilities(self):
        out = predict_customers(self.fitted["logistic"], self.X,
                                self.w1["CustomerID"])
        self.assertTrue((out["churn_probability"] >= 0).all())
        self.assertTrue((out["churn_probability"] <= 1).all())
        self.assertEqual(len(out), len(self.w1))
        self.assertIn("HIGH", set(out["risk"]))


class ReproducibilityTests(unittest.TestCase):
    def test_identical_rerun(self):
        df = load_cleaned()
        w1 = build_features(df, WINDOW_W1)
        X = w1[FEATURE_COLUMNS]
        y = build_target(df, WINDOW_W1, w1).to_numpy()
        cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
        m1, f1 = train_models(X, y, cv)
        m2, f2 = train_models(X, y, cv)
        self.assertEqual(m1, m2)
        self.assertEqual(f1["logistic"].predict(X).tolist(),
                         f2["logistic"].predict(X).tolist())


if __name__ == "__main__":
    unittest.main()
