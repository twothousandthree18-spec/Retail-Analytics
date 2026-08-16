"""run_ml.py — Customer churn prediction layer (Phase 6).

Production-style CLI that mirrors the Phase 5 pipeline conventions
(stage table, structured logging, manifest, exit codes) but does not depend
on PostgreSQL: it reads the validated cleaned dataset directly.

Stages
------
    01  DATASET            load the cleaned dataset + validate schema
    02  FEATURES           build customer-level features (obs window)
    03  TARGET             derive the churn label (label window)
    04  BASELINE           majority-class baseline metrics
    05  TRAIN              fit candidate models with CV (training window W1)
    06  TEMPORAL TEST      apply the best model to the out-of-time window W2
    07  INTERPRETABILITY   feature importance
    08  PREDICTIONS        per-customer churn probabilities + risk category
    09  REPORT             manifest + markdown report

Usage
-----
    python pipeline/run_ml.py [--output DIR] [--temp-dir DIR] [--debug]

Environment:
    PIPELINE_TEMP_DIR   heavy/temporary workspace (default: system temp)
    OUTPUT_DIR          where reports/manifest land (default: <repo>/reports)

Exits 0 on success, 1 on failure. Never commits or pushes anything.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ml_features import (FEATURE_COLUMNS, WINDOW_W1, WINDOW_W2,  # noqa: E402
                         build_features, build_target, load_cleaned,
                         make_dataset)
from ml_models import (MODELS, RANDOM_STATE, baseline_metrics,  # noqa: E402
                       cv_evaluate, feature_importance, predict_customers,
                       select_best, temporal_metrics, train_models)
from logging_utils import PipelineLogger  # noqa: E402

STAGE_NAMES = [
    "DATASET", "FEATURES", "TARGET", "BASELINE", "TRAIN",
    "TEMPORAL TEST", "INTERPRETABILITY", "PREDICTIONS", "REPORT",
]
TOTAL_STAGES = len(STAGE_NAMES)
SUCCESS, FAILED = "SUCCESS", "FAILED"


class PipelineError(Exception):
    pass


def resolve_paths(args) -> tuple[Path, Path]:
    import os
    from ml_features import REPO_ROOT
    out_dir = Path(args.output or os.environ.get("OUTPUT_DIR")
                   or REPO_ROOT / "reports")
    temp_dir = Path(args.temp_dir or os.environ.get("PIPELINE_TEMP_DIR")
                    or Path.home() / "RetailAnalytics_Temp")
    return out_dir, temp_dir


def run_stage(index: int, name: str, fn, ctx: dict) -> tuple[str, float]:
    log = ctx["log"]
    log.stage(index, TOTAL_STAGES, name, "RUNNING")
    t0 = time.time()
    try:
        detail = fn(ctx)
        elapsed = time.time() - t0
        log.stage(index, TOTAL_STAGES, name, "PASS", detail)
        return "PASS", elapsed
    except PipelineError as e:
        elapsed = time.time() - t0
        log.stage(index, TOTAL_STAGES, name, "FAIL")
        raise
    except Exception as e:  # noqa: BLE001
        elapsed = time.time() - t0
        log.stage(index, TOTAL_STAGES, name, "FAIL")
        raise PipelineError(str(e)) from e


def stage_dataset(ctx) -> str:
    df = load_cleaned()
    if not {"CustomerID", "Invoice Date", "TotalPrice", "Quantity",
            "UnitPrice", "StockCode", "InvoiceNo", "Country", "Hour"}.issubset(df.columns):
        raise PipelineError("cleaned dataset missing required columns")
    ctx["df"] = df
    return (f"{len(df):,} rows, {df['CustomerID'].nunique():,} customers, "
            f"{df['dt'].min().date()}..{df['dt'].max().date()}")


def stage_features(ctx) -> str:
    feats = build_features(ctx["df"], WINDOW_W1)
    if len(feats) == 0:
        raise PipelineError("no eligible customers in the training window")
    ctx["features_w1"] = feats
    return f"{len(feats):,} customers x {len(FEATURE_COLUMNS)} features"


def stage_target(ctx) -> str:
    feats = ctx["features_w1"]
    y = build_target(ctx["df"], WINDOW_W1, feats)
    ctx["y_w1"] = y.to_numpy()
    rate = float(y.mean())
    return f"churn rate {rate:.1%} ({int(y.sum())}/{len(y)})"


def stage_baseline(ctx) -> str:
    X = ctx["features_w1"][FEATURE_COLUMNS]
    m = baseline_metrics(X, ctx["y_w1"])
    ctx["baseline"] = m
    return f"majority-class  acc={m['accuracy']:.3f} roc_auc={m['roc_auc']:.3f}"


def stage_train(ctx) -> str:
    from sklearn.model_selection import StratifiedKFold
    X = ctx["features_w1"][FEATURE_COLUMNS]
    y = ctx["y_w1"]
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    ctx["cv_metrics"], ctx["fitted"] = train_models(X, y, cv)
    best = select_best(ctx["cv_metrics"])
    ctx["best_name"] = best
    m = ctx["cv_metrics"][best]
    return (f"best={best}  roc_auc={m['roc_auc']:.3f} "
            f"pr_auc={m['pr_auc']:.3f} f1={m['f1']:.3f}")


def stage_temporal(ctx) -> str:
    df = ctx["df"]
    feats_w2 = build_features(df, WINDOW_W2)
    y_w2 = build_target(df, WINDOW_W2, feats_w2).to_numpy()
    X_w2 = feats_w2[FEATURE_COLUMNS]
    ctx["features_w2"] = feats_w2
    ctx["y_w2"] = y_w2
    best_model = ctx["fitted"][ctx["best_name"]]
    m = temporal_metrics(best_model, X_w2, y_w2)
    ctx["temporal"] = m
    return (f"W2 n={len(X_w2):,} churn={y_w2.mean():.1%} "
            f"roc_auc={m['roc_auc']:.3f} pr_auc={m['pr_auc']:.3f} f1={m['f1']:.3f}")


def stage_interpretability(ctx) -> str:
    best_model = ctx["fitted"][ctx["best_name"]]
    imp = feature_importance(best_model, FEATURE_COLUMNS)
    ctx["importance"] = imp
    top = imp.head(5)["feature"].tolist()
    return f"top: {', '.join(top)}"


def stage_predictions(ctx) -> str:
    # Predictions for the *training* window customers (where the label is known)
    # plus a forward-looking prediction for all customers active in W2.
    best_model = ctx["fitted"][ctx["best_name"]]
    pred_train = predict_customers(best_model,
                                   ctx["features_w1"][FEATURE_COLUMNS],
                                   ctx["features_w1"]["CustomerID"])
    pred_w2 = predict_customers(best_model,
                                ctx["features_w2"][FEATURE_COLUMNS],
                                ctx["features_w2"]["CustomerID"])
    ctx["predictions"] = {"train_window": pred_train, "temporal_window": pred_w2}
    hi = int((pred_w2["risk"] == "HIGH").sum())
    return f"{len(pred_w2):,} customers; {hi} HIGH risk (W2)"


def stage_report(ctx) -> str:
    out = ctx["output_dir"]
    out.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(ctx)
    (out / "ml_run.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "ml_run_report.md").write_text(render_report(ctx), encoding="utf-8")
    ctx["predictions"]["train_window"].to_csv(out / "ml_predictions_train.csv", index=False)
    ctx["predictions"]["temporal_window"].to_csv(out / "ml_predictions_temporal.csv", index=False)
    ctx["importance"].to_csv(out / "ml_feature_importance.csv", index=False)
    ctx["log"].info(f"manifest: {out / 'ml_run.json'}")
    ctx["log"].info(f"report:   {out / 'ml_run_report.md'}")
    return "written"


def build_manifest(ctx: dict) -> dict:
    return {
        "run_id": ctx["run_id"],
        "timestamp": ctx["timestamp"],
        "status": SUCCESS,
        "problem": "customer churn prediction",
        "target": "churn = no purchase in the label window following an "
                  "observation window (0/1)",
        "windows": {
            "W1_train_val": {"obs": [str(WINDOW_W1.obs_start), str(WINDOW_W1.obs_end)],
                             "label": [str(WINDOW_W1.label_start), str(WINDOW_W1.label_end)]},
            "W2_temporal_test": {"obs": [str(WINDOW_W2.obs_start), str(WINDOW_W2.obs_end)],
                                 "label": [str(WINDOW_W2.label_start), str(WINDOW_W2.label_end)]},
        },
        "models": {name: m for name, m in ctx["cv_metrics"].items()},
        "baseline": ctx["baseline"],
        "best_model": ctx["best_name"],
        "temporal_test": ctx["temporal"],
        "train_window_n": int(len(ctx["features_w1"])),
        "temporal_window_n": int(len(ctx["features_w2"])),
        "random_state": RANDOM_STATE,
    }

def render_report(ctx: dict) -> str:
    best = ctx["best_name"]
    lines = [
        "# ML Run Report — Customer Churn Prediction (Phase 6)",
        "",
        f"- **Run ID:** {ctx['run_id']}",
        f"- **Timestamp:** {ctx['timestamp']}",
        f"- **Status:** {SUCCESS}",
        f"- **Best model:** `{best}` (chosen by training-window CV ROC-AUC)",
        "",
        "## Windows",
        f"- W1 train/validation: obs {WINDOW_W1.obs_start}..{WINDOW_W1.obs_end}, "
        f"label {WINDOW_W1.label_start}..{WINDOW_W1.label_end} "
        f"({len(ctx['features_w1']):,} customers)",
        f"- W2 temporal test: obs {WINDOW_W2.obs_start}..{WINDOW_W2.obs_end}, "
        f"label {WINDOW_W2.label_start}..{WINDOW_W2.label_end} "
        f"({len(ctx['features_w2']):,} customers)",
        "",
        "## Training-window CV (W1, out-of-fold)",
        "",
        "| model | acc | prec | rec | F1 | ROC-AUC | PR-AUC |",
        "|---|---|---|---|---|---|---|",
    ]
    for name in MODELS:
        m = ctx["cv_metrics"][name]
        lines.append(
            f"| {name} | {m['accuracy']:.3f} | {m['precision']:.3f} | {m['recall']:.3f} "
            f"| {m['f1']:.3f} | {m['roc_auc']:.3f} | {m['pr_auc']:.3f} |")
    b = ctx["baseline"]
    lines += [
        "",
        "## Baseline (majority class)",
        f"Accuracy {b['accuracy']:.3f} · ROC-AUC {b['roc_auc']:.3f} · "
        f"PR-AUC {b['pr_auc']:.3f}",
        "",
        "## Temporal (out-of-time) test on W2 — no retraining",
        "",
    ]
    t = ctx["temporal"]
    lines.append(
        f"{best}: acc {t['accuracy']:.3f} · precision {t['precision']:.3f} · "
        f"recall {t['recall']:.3f} · F1 {t['f1']:.3f} · "
        f"ROC-AUC {t['roc_auc']:.3f} · PR-AUC {t['pr_auc']:.3f}")
    lines += [
        "",
        "## Top predictive features (association only, not causation)",
        "",
        "| rank | feature | importance |",
        "|---|---|---|",
    ]
    for i, row in ctx["importance"].head(10).iterrows():
        lines.append(f"| {i+1} | {row['feature']} | {row['importance']:.4f} |")
    lines += [
        "",
        "## Predictions",
        "- `ml_predictions_train.csv` — churn probability for every W1 customer "
        "(label known).",
        "- `ml_predictions_temporal.csv` — forward-looking probabilities for "
        "every W2 customer (label known, model never saw it).",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="report/manifest output dir (default: <repo>/reports)")
    parser.add_argument("--temp-dir", help="temporary workspace dir")
    parser.add_argument("--debug", action="store_true", help="print full tracebacks")
    args = parser.parse_args(argv)

    out_dir, temp_dir = resolve_paths(args)
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = {
        "log": PipelineLogger(out_dir / "ml_run.log"),
        "run_id": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "output_dir": out_dir,
        "temp_dir": temp_dir,
        "stages": [],
    }
    log = ctx["log"]
    log.banner("RETAIL ANALYTICS — CHURN ML LAYER (PHASE 6)", ctx["run_id"])
    stage_fns = [stage_dataset, stage_features, stage_target, stage_baseline,
                 stage_train, stage_temporal, stage_interpretability,
                 stage_predictions, stage_report]
    t_start = time.time()
    try:
        for i, fn in enumerate(stage_fns, start=1):
            status, elapsed = run_stage(i, STAGE_NAMES[i - 1], fn, ctx)
            ctx["stages"].append({"name": STAGE_NAMES[i - 1], "status": status,
                                  "seconds": round(elapsed, 2)})
    except PipelineError as e:
        ctx["stages"].append({"name": "REPORT", "status": "FAIL", "seconds": None})
        log.blank()
        log.error(f"stage failed: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        log.blank()
        log._emit("Pipeline stopped. Exit code: 1")
        return 1
    finally:
        log.close()

    log.blank()
    bar = "=" * 60
    log._emit(bar)
    for s in ctx["stages"]:
        log.stage(STAGE_NAMES.index(s["name"]) + 1, TOTAL_STAGES, s["name"],
                  s["status"], f"{s['seconds']:.1f}s")
    log._emit(bar)
    log._emit(f"PIPELINE STATUS: {SUCCESS}")
    log._emit(f"Total duration: {time.time() - t_start:.1f}s")
    log._emit(bar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
