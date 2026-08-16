"""run_ml_tune.py — Phase 6.1 lightweight hyperparameter tuning runner.

Runs a small GridSearchCV for each existing Phase 6 model inside W1 only,
compares the tuned models against the current Phase 6 models on W1 CV and the
W2 temporal test, applies the final-model rule (``ml_tuning.decide_final``),
then regenerates interpretability and prediction outputs for the final model.

Stages
------
    01  DATASET            load the cleaned dataset
    02  FEATURES           build W1 features (observation window)
    03  TARGET             derive churn labels (label window)
    04  BASELINE           majority-class baseline
    05  TUNE               GridSearchCV on W1 only (3 models)
    06  COMPARE            tuned vs current models, W1 CV table
    07  TEMPORAL TEST      apply current + tuned best to W2 (never trained)
    08  SELECT             apply the final-model rule
    09  INTERPRETABILITY   feature importance of the final model
    10  PREDICTIONS        regenerate per-customer probabilities (final model)
    11  REPORT             manifest + comparison report + CSV outputs

W2 is never used for hyperparameter selection: it appears only in stage 07
as a held-out temporal test.

Usage
-----
    python pipeline/run_ml_tune.py [--output DIR] [--temp-dir DIR] [--debug]

Environment: PIPELINE_TEMP_DIR, OUTPUT_DIR (same conventions as run_ml.py).
Exits 0 on success, 1 on failure. Never commits or pushes anything.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import ml_features as feat  # noqa: E402
import ml_models as mod  # noqa: E402
import ml_tuning as tune  # noqa: E402
from logging_utils import PipelineLogger  # noqa: E402

STAGE_NAMES = [
    "DATASET", "FEATURES", "TARGET", "BASELINE", "TUNE", "COMPARE",
    "TEMPORAL TEST", "SELECT", "INTERPRETABILITY", "PREDICTIONS", "REPORT",
]
TOTAL_STAGES = len(STAGE_NAMES)
SUCCESS, FAILED = "SUCCESS", "FAILED"


class PipelineError(Exception):
    pass


def resolve_paths(args) -> tuple[Path, Path]:
    out_dir = Path(args.output or os.environ.get("OUTPUT_DIR")
                   or feat.REPO_ROOT / "reports")
    temp_dir = Path(args.temp_dir or os.environ.get("PIPELINE_TEMP_DIR")
                    or Path.home() / "RetailAnalytics_Temp")
    return out_dir, temp_dir


def run_stage(index, name, fn, ctx):
    log = ctx["log"]
    log.stage(index, TOTAL_STAGES, name, "RUNNING")
    t0 = time.time()
    try:
        detail = fn(ctx)
        elapsed = time.time() - t0
        log.stage(index, TOTAL_STAGES, name, "PASS", detail)
        return "PASS", elapsed
    except PipelineError:
        log.stage(index, TOTAL_STAGES, name, "FAIL")
        raise
    except Exception as e:  # noqa: BLE001
        log.stage(index, TOTAL_STAGES, name, "FAIL")
        raise PipelineError(str(e)) from e


def stage_dataset(ctx) -> str:
    df = feat.load_cleaned()
    ctx["df"] = df
    return f"{len(df):,} rows, {df['CustomerID'].nunique():,} customers"


def stage_features(ctx) -> str:
    w1 = feat.build_features(ctx["df"], feat.WINDOW_W1)
    ctx["w1"] = w1
    ctx["X_w1"] = w1[feat.FEATURE_COLUMNS]
    ctx["ids_w1"] = w1["CustomerID"]
    return f"{len(w1):,} customers x {len(feat.FEATURE_COLUMNS)} features"


def stage_target(ctx) -> str:
    y = feat.build_target(ctx["df"], feat.WINDOW_W1, ctx["w1"])
    ctx["y_w1"] = y.to_numpy()
    return f"churn rate {y.mean():.1%} ({int(y.sum())}/{len(y)})"


def stage_baseline(ctx) -> str:
    m = mod.baseline_metrics(ctx["X_w1"], ctx["y_w1"])
    ctx["baseline"] = m
    return f"majority-class roc_auc={m['roc_auc']:.3f}"


def stage_tune(ctx) -> str:
    from sklearn.model_selection import StratifiedKFold
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=mod.RANDOM_STATE)
    ctx["cv"] = cv
    ctx["tuned"] = tune.tune_models(ctx["X_w1"], ctx["y_w1"], cv)
    summary = ", ".join(f"{n}={r['cv']['roc_auc']:.3f}" for n, r in ctx["tuned"].items())
    return f"W1-only CV  {summary}"


def stage_compare(ctx) -> str:
    # Current (untuned) Phase 6 models: W1 CV metrics + full-W1 fitted models.
    ctx["current_metrics"], ctx["current_fitted"] = mod.train_models(
        ctx["X_w1"], ctx["y_w1"], ctx["cv"])
    rows = []
    for name in tune.SEARCH_SPACES:
        cur = ctx["current_metrics"][name]
        tnd = ctx["tuned"][name]["cv"]
        rows.append({"model": f"current_{name}", **{k: cur[k] for k in
                     ("accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc")}})
        rows.append({"model": f"tuned_{name}", **{k: tnd[k] for k in
                     ("accuracy", "precision", "recall", "f1", "roc_auc", "pr_auc")}})
    ctx["w1_comparison"] = rows
    return "6 rows (current + tuned x 3 models) W1 CV"


def stage_temporal(ctx) -> str:
    w2 = feat.build_features(ctx["df"], feat.WINDOW_W2)
    ctx["ids_w2"] = w2["CustomerID"]
    X_w2 = w2[feat.FEATURE_COLUMNS]
    y_w2 = feat.build_target(ctx["df"], feat.WINDOW_W2, w2).to_numpy()
    ctx["X_w2"], ctx["y_w2"] = X_w2, y_w2

    best_tuned_name = tune.select_best_tuned(ctx["tuned"])
    ctx["best_tuned_name"] = best_tuned_name
    ctx["temporal"] = {
        "current_logistic": mod.temporal_metrics(ctx["current_fitted"]["logistic"],
                                                 X_w2, y_w2),
        "tuned_best": mod.temporal_metrics(ctx["tuned"][best_tuned_name]["estimator"],
                                           X_w2, y_w2),
    }
    t = ctx["temporal"]["tuned_best"]
    return (f"best tuned={best_tuned_name}  W2 roc_auc={t['roc_auc']:.3f} "
            f"pr_auc={t['pr_auc']:.3f} (model never saw W2)")


def stage_select(ctx) -> str:
    decision = tune.decide_final(
        ctx["temporal"]["current_logistic"],
        ctx["best_tuned_name"],
        ctx["temporal"]["tuned_best"])
    ctx["decision"] = decision
    if decision["switch"]:
        ctx["final_model"] = ctx["tuned"][decision["final_model"]]["estimator"]
        ctx["final_source"] = f"tuned_{decision['final_model']}"
    else:
        ctx["final_model"] = ctx["current_fitted"]["logistic"]
        ctx["final_source"] = "current_logistic"
    return (f"final={decision['final_model']}  "
            f"switch={decision['switch']}  ({decision['reason']})")


def stage_interpretability(ctx) -> str:
    imp = mod.feature_importance(ctx["final_model"], mod.FEATURE_COLUMNS)
    ctx["importance"] = imp
    top = ", ".join(imp.head(5)["feature"].tolist())
    return f"final={ctx['decision']['final_model']}  top: {top}"


def stage_predictions(ctx) -> str:
    ctx["pred_train"] = mod.predict_customers(ctx["final_model"], ctx["X_w1"],
                                              ctx["ids_w1"])
    ctx["pred_w2"] = mod.predict_customers(ctx["final_model"], ctx["X_w2"],
                                           ctx["ids_w2"])
    hi = int((ctx["pred_w2"]["risk"] == "HIGH").sum())
    return f"{len(ctx['pred_w2']):,} W2 customers; {hi} HIGH risk"


def stage_report(ctx) -> str:
    out = ctx["output_dir"]
    out.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(ctx)
    (out / "ml_tune.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "ml_tune_report.md").write_text(render_report(ctx), encoding="utf-8")

    pd = ctx.get("_pd")
    if pd is None:
        import pandas as _pd
        pd = _pd
    pd.DataFrame(ctx["w1_comparison"]).to_csv(out / "ml_tune_comparison.csv", index=False)
    # Regenerate the final-model outputs (same filenames as Phase 6).
    ctx["pred_train"].to_csv(out / "ml_predictions_train.csv", index=False)
    ctx["pred_w2"].to_csv(out / "ml_predictions_temporal.csv", index=False)
    ctx["importance"].to_csv(out / "ml_feature_importance.csv", index=False)
    ctx["log"].info(f"manifest: {out / 'ml_tune.json'}")
    ctx["log"].info(f"report:   {out / 'ml_tune_report.md'}")
    ctx["log"].info("regenerated: ml_predictions_{train,temporal}.csv, "
                    "ml_feature_importance.csv")
    return "written"


def build_manifest(ctx: dict) -> dict:
    d = ctx["decision"]
    return {
        "run_id": ctx["run_id"],
        "timestamp": ctx["timestamp"],
        "status": SUCCESS,
        "purpose": "Phase 6.1 lightweight hyperparameter tuning",
        "selection_rule": "best tuned model by W1 CV ROC-AUC; final model by "
                          "W2 ROC-AUC/PR-AUC improvement within recall guard",
        "windows": {
            "W1_train_val": {"obs": [str(feat.WINDOW_W1.obs_start), str(feat.WINDOW_W1.obs_end)],
                             "label": [str(feat.WINDOW_W1.label_start), str(feat.WINDOW_W1.label_end)]},
            "W2_temporal_test": {"obs": [str(feat.WINDOW_W2.obs_start), str(feat.WINDOW_W2.obs_end)],
                                 "label": [str(feat.WINDOW_W2.label_start), str(feat.WINDOW_W2.label_end)]},
        },
        "search_space": {name: grid for name, (_, grid) in tune.SEARCH_SPACES.items()},
        "tuned_w1_cv": {n: r["cv"] for n, r in ctx["tuned"].items()},
        "tuned_best_params": {n: r["best_params"] for n, r in ctx["tuned"].items()},
        "current_w1_cv": {n: {k: v for k, v in m.items() if k != "confusion"}
                          for n, m in ctx["current_metrics"].items()},
        "baseline": ctx["baseline"],
        "best_tuned_by_cv": ctx["best_tuned_name"],
        "w2_temporal": ctx["temporal"],
        "decision": d,
        "final_model": d["final_model"],
        "final_source": ctx["final_source"],
        "final_model_params": (
            ctx["tuned"][d["final_model"]]["best_params"]
            if d["switch"] else None),
    }


def render_report(ctx: dict) -> str:
    d = ctx["decision"]
    lines = [
        "# ML Tuning Report — Phase 6.1 Lightweight Hyperparameter Search",
        "",
        f"- **Run ID:** {ctx['run_id']}",
        f"- **Status:** {SUCCESS}",
        f"- **Best tuned model (W1 CV ROC-AUC):** `{ctx['best_tuned_name']}`",
        f"- **Final model:** `{d['final_model']}` "
        f"(source: {ctx['final_source']})",
        "",
        "## 1. Tuning method",
        "Small GridSearchCV (5-fold stratified, W1 only) per existing Phase 6 "
        "model, refit on ROC-AUC. **W2 is not used anywhere during tuning.**",
        "",
        "## 2. Search space",
        "",
        "| model | hyperparameters | combinations |",
        "|-------|-----------------|--------------|",
    ]
    for name, (_, grid) in tune.SEARCH_SPACES.items():
        combo = 1
        for v in grid.values():
            combo *= len(v)
        params = ", ".join(f"{k.split('__')[-1]} in {v}" for k, v in grid.items())
        lines.append(f"| {name} | {params} | {combo} |")
    lines += ["", "## 3. W1 CV comparison (current vs tuned)", "",
              "| model | acc | prec | rec | F1 | ROC-AUC | PR-AUC |", "|---|---|---|---|---|---|---|"]
    for row in ctx["w1_comparison"]:
        lines.append(f"| {row['model']} | {row['accuracy']:.3f} | {row['precision']:.3f} | "
                     f"{row['recall']:.3f} | {row['f1']:.3f} | {row['roc_auc']:.3f} | "
                     f"{row['pr_auc']:.3f} |")
    t = ctx["temporal"]
    lines += ["", "## 4. W2 temporal test (never trained on W2)", "",
              "| model | acc | prec | rec | F1 | ROC-AUC | PR-AUC |", "|---|---|---|---|---|---|---|"]
    for label, m in (("current logistic", t["current_logistic"]),
                     (f"tuned {ctx['best_tuned_name']}", t["tuned_best"])):
        lines.append(f"| {label} | {m['accuracy']:.3f} | {m['precision']:.3f} | "
                     f"{m['recall']:.3f} | {m['f1']:.3f} | {m['roc_auc']:.3f} | "
                     f"{m['pr_auc']:.3f} |")
    lines += ["", "## 5. Final-model decision", "",
              f"- Switch? **{d['switch']}**  "
              f"improves_roc={d['improves_roc']}, improves_pr={d['improves_pr']}, "
              f"recall_ok={d['recall_ok']}",
              f"- **Final model:** `{d['final_model']}`  "
              f"(source: {ctx['final_source']})",
              f"- Final-model hyperparameters: "
              f"{ctx['tuned'][d['final_model']]['best_params'] if d['switch'] else 'current defaults (C=1.0)'}",
              f"- Reason: {d['reason']}",
              "",
              "## 6. Interpretability (final model, association not causation)",
              "",
              "| rank | feature | importance |",
              "|---|---|---|",
              ]
    for i, row in ctx["importance"].head(10).iterrows():
        lines.append(f"| {i+1} | {row['feature']} | {row['importance']:.4f} |")
    lines += ["", "## 7. Prediction outputs (regenerated with the final model)",
              "",
              f"- `ml_predictions_train.csv` — {len(ctx['pred_train']):,} W1 customers",
              f"- `ml_predictions_temporal.csv` — {len(ctx['pred_w2']):,} W2 customers",
              "- `ml_feature_importance.csv` — full 18-feature importance table",
              "",
              ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="report/manifest output dir")
    parser.add_argument("--temp-dir", help="temporary workspace dir")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    out_dir, _ = resolve_paths(args)
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx = {
        "log": PipelineLogger(out_dir / "ml_tune.log"),
        "run_id": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "output_dir": out_dir,
    }
    log = ctx["log"]
    log.banner("RETAIL ANALYTICS — CHURN ML TUNING (PHASE 6.1)", ctx["run_id"])
    stage_fns = [stage_dataset, stage_features, stage_target, stage_baseline,
                 stage_tune, stage_compare, stage_temporal, stage_select,
                 stage_interpretability, stage_predictions, stage_report]
    t_start = time.time()
    ctx["stages"] = []
    try:
        for i, fn in enumerate(stage_fns, start=1):
            status, elapsed = run_stage(i, STAGE_NAMES[i - 1], fn, ctx)
            ctx["stages"].append({"name": STAGE_NAMES[i - 1], "status": status,
                                  "seconds": round(elapsed, 2)})
    except PipelineError as e:
        log.blank()
        log.error(f"stage failed: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
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
