"""run_pipeline.py — Automated end-to-end retail analytics pipeline (Phase 5).

Single orchestrator that reproduces every major analytical output of the
project from one command:

    python pipeline/run_pipeline.py

Stages
------
    01  INGESTION          locate + verify the configured source dataset
    02  CLEANING           execute the validated cleaning notebook (in-memory)
    03  DATA QUALITY       schema / missing / duplicates / numeric / dates / rules
    04  POSTGRESQL LOAD    load the cleaned dataset into PostgreSQL (truncate+reload)
    05  SQL ANALYTICS      execute schema.sql + sql/01..06
    06  POWER BI DATASET   regenerate the Power BI-ready dataset from PostgreSQL
    07  EXCEL REPORT       append the Phase 4 cohort sheets to the workbook (26 sheets)
    08  FULL VALIDATION    existing validation suites + cross-system reconciliation
    09  FINAL REPORT       run manifest + human-readable report

Options
-------
    --input <path>     source dataset (default: online_retail.csv / INPUT_DATA_PATH)
    --db-url <url>     override DATABASE_URL
    --skip-powerbi     do not regenerate / validate the Power BI dataset
    --skip-excel       do not regenerate the Excel cohort sheets
    --debug            print full tracebacks on failure

Exits 0 on success, 1 on failure. Never commits or pushes anything.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parent))

import config as cfg  # noqa: E402
import validators  # noqa: E402
from logging_utils import PipelineLogger  # noqa: E402
from notebook_runner import execute_notebook  # noqa: E402

STAGE_NAMES = [
    "INGESTION", "CLEANING", "DATA QUALITY", "POSTGRESQL LOAD",
    "SQL ANALYTICS", "POWER BI DATASET", "EXCEL REPORT",
    "FULL VALIDATION", "FINAL REPORT",
]
TOTAL_STAGES = len(STAGE_NAMES)

SUCCESS, FAILED = "SUCCESS", "FAILED"


class PipelineError(Exception):
    """A stage failed with a user-facing reason."""


class SkippedStage(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class StageFailure(Exception):
    def __init__(self, stage_index: int, stage_name: str, reason: str) -> None:
        self.stage_index = stage_index
        self.stage_name = stage_name
        self.reason = reason
        super().__init__(reason)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def run_id() -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    n = 1
    existing = list(cfg.REPORTS_DIR.glob(f"pipeline_run_{today}-*.json")) if cfg.REPORTS_DIR.exists() else []
    if existing:
        seqs = [int(p.stem.rsplit("-", 1)[1]) for p in existing if p.stem.rsplit("-", 1)[1].isdigit()]
        n = max(seqs, default=0) + 1
    return f"{today}-{n:03d}"


def csv_summary(path: Path) -> tuple[int, int]:
    """Stream a CSV to count rows/columns without loading it into memory."""
    import csv
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        ncols = len(header) if header is not None else 0
        nrows = sum(1 for _ in reader)
    return nrows, ncols


def run_script(script: Path, env: dict, cwd: Path, args: list[str] | None = None,
               timeout: int = 1800, logger: PipelineLogger | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(script)] + (args or [])
    if logger is not None:
        logger.detail(f"running: {' '.join(str(a) for a in cmd)}")
    return subprocess.run(cmd, env=env, cwd=str(cwd), capture_output=True,
                          text=True, timeout=timeout)


def _tail(text: str, n: int = 3) -> str:
    lines = [l for l in text.splitlines() if l.strip()]
    return " | ".join(lines[-n:]) if lines else ""


def make_env(config: cfg.Config) -> dict:
    env = os.environ.copy()
    env["DATABASE_URL"] = config.database_url
    env["PIPELINE_TEMP_DIR"] = str(config.temp_dir)
    return env


def _scratch_env(config: cfg.Config, name: str) -> dict:
    """Environment overrides that push heavy scratch (openpyxl/nbclient
    temporaries) into a D:-backed temporary workspace instead of the OS temp."""
    sub = cfg.temp_subdir(config, name)
    return {"TMP": str(sub), "TEMP": str(sub), "TMPDIR": str(sub)}


def _connect(config: cfg.Config):
    try:
        return psycopg2.connect(config.database_url, connect_timeout=15)
    except Exception as exc:  # noqa: BLE001
        raise PipelineError(f"could not connect to PostgreSQL: {exc}") from exc


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------

def stage_ingest(ctx: dict) -> str:
    config = ctx["config"]
    path = config.input_path
    if not path.exists():
        raise PipelineError(
            f"missing source dataset: {path}\n"
            "  The pipeline refuses to substitute another dataset. "
            "Point --input at the raw CSV (default: online_retail.csv).")
    rows, cols = csv_summary(path)
    size = path.stat().st_size
    ctx["raw"] = {"path": str(path), "rows": rows, "columns": cols, "size_bytes": size}
    ctx["log"].info(f"source: {path.name} | size: {size:,} bytes")
    ctx["log"].info(f"rows: {rows:,} | columns: {cols}")
    return f"{rows:,} rows"


def stage_clean(ctx: dict) -> str:
    config = ctx["config"]
    log = ctx["log"]
    if config.input_path.resolve() != cfg.SOURCE_CSV.resolve():
        shutil.copy2(config.input_path, cfg.SOURCE_CSV)
        log.warning(f"configured input differs from default; copied {config.input_path.name} -> {cfg.SOURCE_CSV.name}")
    if not cfg.NOTEBOOK.exists():
        raise PipelineError(f"cleaning notebook not found: {cfg.NOTEBOOK}")
    t0 = time.time()
    # The notebook executes in-process; push openpyxl/nbclient scratch to the
    # D:-backed temp workspace so heavy temporaries never touch the repo drive.
    scratch = _scratch_env(config, "workspaces")
    saved = {k: os.environ.get(k) for k in scratch}
    for k, v in scratch.items():
        os.environ[k] = v
    try:
        execute_notebook(cfg.NOTEBOOK, cfg.REPO_ROOT)
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    ctx["clean_seconds"] = time.time() - t0
    if not cfg.CLEANED_CSV.exists():
        raise PipelineError(f"cleaning finished but cleaned dataset missing: {cfg.CLEANED_CSV}")
    df = validators.read_cleaned(cfg.CLEANED_CSV)
    ctx["df"] = df
    ctx["cleaned"] = {"path": str(cfg.CLEANED_CSV), "rows": len(df), "columns": len(df.columns)}
    log.info(f"cleaned dataset: {len(df):,} rows x {len(df.columns)} columns")
    return f"{len(df):,} rows"


def stage_data_quality(ctx: dict) -> str:
    log = ctx["log"]
    dq = validators.run_data_quality(ctx["df"])
    ctx["data_quality"] = dq
    s = dq["summary"]
    log.info(f"rows={dq['rows']:,} | columns={dq['columns']} | "
             f"missing critical={s['missing_critical']} | duplicate rows={s['duplicate_rows']} | "
             f"invalid dates={s['invalid_dates']} | cancellations remaining={s['cancellations_remaining']}")
    for c in dq["checks"]:
        log.detail(f"[{c['status']}] {c['name']}" + (f" - {c['detail']}" if c["detail"] else ""))
    if dq["status"] == validators.FAIL:
        raise PipelineError("data quality gate FAILED - refusing to continue")
    return dq["status"]


def stage_postgresql(ctx: dict) -> str:
    config = ctx["config"]
    log = ctx["log"]
    proc = run_script(cfg.SQL_DIR / "load_data.py", make_env(config), cfg.REPO_ROOT,
                      args=["--truncate"], logger=log)
    if proc.returncode != 0:
        raise PipelineError(f"PostgreSQL load failed:\n{_tail(proc.stderr or proc.stdout, 8)}")
    conn = _connect(config)
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM retail_transactions")
        ctx["db_rows"] = cur.fetchone()[0]
    conn.close()
    log.info(f"retail_transactions rows after load: {ctx['db_rows']:,}")
    return f"{ctx['db_rows']:,} rows"


def stage_sql_analytics(ctx: dict) -> str:
    config = ctx["config"]
    log = ctx["log"]
    conn = _connect(config)
    results = []
    try:
        for name in cfg.SQL_SCRIPTS:
            path = cfg.SQL_DIR / name
            t0 = time.time()
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    sql = fh.read()
                with conn.cursor() as cur:
                    cur.execute(sql)
                conn.commit()
                results.append({"name": name, "status": "PASS", "seconds": round(time.time() - t0, 2)})
                log.detail(f"OK {name} ({time.time() - t0:.1f}s)")
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                results.append({"name": name, "status": "FAIL", "seconds": round(time.time() - t0, 2)})
                log.detail(f"FAIL {name}: {str(exc).strip().splitlines()[0]}")
                raise PipelineError(f"SQL script failed: {name}\n{str(exc).strip()[:500]}") from exc
    finally:
        conn.close()
    ctx["sql_analytics"] = results
    return f"{len(results)} scripts"


def stage_powerbi_dataset(ctx: dict) -> str:
    config = ctx["config"]
    log = ctx["log"]
    if config.skip_powerbi:
        raise SkippedStage("--skip-powerbi")
    proc = run_script(cfg.PBI_SCRIPTS_DIR / "export_pbi_dataset.py", make_env(config),
                      cfg.REPO_ROOT, logger=log)
    if proc.returncode != 0:
        raise PipelineError(f"Power BI dataset export failed:\n{_tail(proc.stderr or proc.stdout, 8)}")
    files = {}
    for name, expected in cfg.PBI_DATASET_FILES.items():
        p = cfg.PBI_DATASET_DIR / name
        if not p.exists():
            raise PipelineError(f"expected dataset file missing after export: {name}")
        rows = sum(1 for _ in open(p, encoding="utf-8")) - 1
        files[name] = rows
        if rows != expected:
            raise PipelineError(f"row-count mismatch for {name}: expected {expected:,}, got {rows:,}")
        log.detail(f"{name}: {rows:,} rows")
    ctx["powerbi"] = {"files": files}
    return f"{len(files)} files"


def stage_excel_report(ctx: dict) -> str:
    config = ctx["config"]
    log = ctx["log"]
    if config.skip_excel:
        raise SkippedStage("--skip-excel")
    if not cfg.EXCEL_WORKBOOK.exists():
        raise PipelineError(f"workbook missing (cleaning stage should have produced it): {cfg.EXCEL_WORKBOOK}")

    missing = [c for c in cfg.COHORT_CSVS if not (cfg.PBI_DATASET_DIR / c).exists()]
    if missing:
        if config.skip_powerbi:
            raise PipelineError(
                "cohort CSVs required to build the Excel cohort sheets are missing "
                f"({', '.join(missing)}) and the Power BI stage was skipped. "
                "Run without --skip-powerbi.")
        log.warning(f"cohort CSVs missing ({', '.join(missing)}); bootstrapping the Power BI dataset first")
        proc = run_script(cfg.PBI_SCRIPTS_DIR / "export_pbi_dataset.py", make_env(config),
                          cfg.REPO_ROOT, logger=log)
        if proc.returncode != 0:
            raise PipelineError(f"dataset bootstrap failed:\n{_tail(proc.stderr or proc.stdout, 8)}")

    proc = run_script(cfg.REPORTS_DIR / "build_cohort_excel.py", make_env(config),
                      cfg.REPO_ROOT, logger=log)
    if proc.returncode != 0:
        raise PipelineError(f"Excel cohort-sheet build failed:\n{_tail(proc.stderr or proc.stdout, 8)}")

    import openpyxl
    wb = openpyxl.load_workbook(cfg.EXCEL_WORKBOOK, read_only=True)
    sheets = wb.sheetnames
    wb.close()
    ctx["excel"] = {"path": str(cfg.EXCEL_WORKBOOK), "sheet_count": len(sheets), "sheets": sheets}
    if len(sheets) != cfg.EXPECTED_EXCEL_SHEETS:
        raise PipelineError(f"expected {cfg.EXPECTED_EXCEL_SHEETS} sheets, found {len(sheets)}")
    if "RFM Customer Segmentation" not in sheets:
        raise PipelineError("RFM sheet missing from workbook")
    for cohort_sheet in ("Customer Cohort Analysis", "Cohort Customer Counts", "Cohort Revenue Analysis"):
        if cohort_sheet not in sheets:
            raise PipelineError(f"cohort sheet missing: {cohort_sheet}")
    return f"{len(sheets)} sheets"


def stage_full_validation(ctx: dict) -> str:
    config = ctx["config"]
    log = ctx["log"]
    env = make_env(config)
    results = {}

    for label, script in [
        ("verify_pipeline", cfg.SQL_DIR / "verify_pipeline.py"),
        ("cohort_validation", cfg.SQL_DIR / "cohort_validation.py"),
    ]:
        proc = run_script(script, env, cfg.REPO_ROOT, logger=log)
        ok = proc.returncode == 0
        results[label] = {"pass": ok, "exit": proc.returncode, "tail": _tail(proc.stdout, 2)}
        log.detail(f"{label}: {'PASS' if ok else 'FAIL'} (exit {proc.returncode}) - {results[label]['tail']}")
        if not ok:
            raise PipelineError(f"validation failed: {label}\n{_tail(proc.stderr or proc.stdout, 8)}")

    if not config.skip_powerbi:
        proc = run_script(cfg.PBI_SCRIPTS_DIR / "validate_pbi.py", env, cfg.REPO_ROOT, logger=log)
        ok = proc.returncode == 0
        results["validate_pbi"] = {"pass": ok, "exit": proc.returncode, "tail": _tail(proc.stdout, 2)}
        log.detail(f"validate_pbi: {'PASS' if ok else 'FAIL'} (exit {proc.returncode}) - {results['validate_pbi']['tail']}")
        if not ok:
            raise PipelineError(f"Power BI validation failed\n{_tail(proc.stderr or proc.stdout, 8)}")

    # ---- cross-system reconciliation ----
    py = validators.python_metrics(ctx["df"])
    conn = _connect(config)
    try:
        sql = validators.sql_metrics(conn)
    finally:
        conn.close()
    excel = None
    if not config.skip_excel and "excel" in ctx:
        excel = validators.excel_metrics(cfg.EXCEL_WORKBOOK)
    pbi = None
    if not config.skip_powerbi:
        pbi = validators.pbi_metrics(cfg.PBI_DATASET_DIR)

    recon = validators.reconcile(py, sql, excel, pbi)
    ctx["reconciliation"] = recon
    ctx["metrics"] = {"python": py, "sql": sql,
                      "excel": excel if excel is not None else {"note": "skipped"},
                      "pbi": pbi if pbi is not None else {"note": "skipped"}}
    n_fail = sum(1 for r in recon["rows"] if r["status"] == validators.FAIL)
    for r in recon["rows"]:
        log.detail(f"[{r['status']}] {r['metric']}: py={r['python']} sql={r['sql']} "
                   f"excel={r['excel']} pbi={r['pbi']}" + (f" ({r['note']})" if r["note"] else ""))
    if recon["status"] != validators.PASS:
        raise PipelineError(f"cross-system reconciliation FAILED ({n_fail} metric rows)")
    ctx["validation"] = results
    return f"{len(recon['rows'])} metrics reconciled"


def stage_final_report(ctx: dict) -> str:
    config = ctx["config"]
    log = ctx["log"]
    ctx["total_seconds"] = time.time() - ctx["_t_start"]
    ctx["stages"].append({"name": "FINAL REPORT", "status": "PASS", "seconds": 0.0})
    manifest = build_manifest(ctx, SUCCESS)
    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "pipeline_run.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    (config.output_dir / "pipeline_run_report.md").write_text(
        render_report(manifest), encoding="utf-8")
    log.info(f"manifest: {config.output_dir / 'pipeline_run.json'}")
    log.info(f"report:   {config.output_dir / 'pipeline_run_report.md'}")
    return "written"


# ---------------------------------------------------------------------------
# manifest + report rendering
# ---------------------------------------------------------------------------

def build_manifest(ctx: dict, status: str) -> dict:
    return {
        "run_id": ctx["run_id"],
        "timestamp": ctx["timestamp"],
        "status": status,
        "duration_seconds": round(ctx["total_seconds"], 2),
        "input": ctx.get("raw"),
        "cleaned": ctx.get("cleaned"),
        "data_quality": {
            k: v for k, v in (ctx.get("data_quality") or {}).items() if k != "checks"
        },
        "database": {"table": "retail_transactions", "rows": ctx.get("db_rows")},
        "sql_analytics": ctx.get("sql_analytics"),
        "excel": {k: v for k, v in (ctx.get("excel") or {}).items() if k != "sheets"},
        "powerbi": ctx.get("powerbi"),
        "validation": ctx.get("validation"),
        "reconciliation": {
            "status": (ctx.get("reconciliation") or {}).get("status"),
            "metric_count": len((ctx.get("reconciliation") or {}).get("rows", [])),
        },
        "metrics": ctx.get("metrics") or {},
        "stages": ctx.get("stages"),
        "failed_stage": ctx.get("failed_stage"),
    }


def render_report(m: dict) -> str:
    def table(rows):
        if not rows:
            return ""
        widths = [max(len(str(r[i])) for r in rows + [list(rows[0])]) for i in range(len(rows[0]))]
        line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
        out = [line]
        for r in rows:
            out.append("| " + " | ".join(str(c).ljust(w) for c, w in zip(r, widths)) + " |")
            out.append(line)
        return "\n".join(out)

    def d(v) -> dict:
        return v if isinstance(v, dict) else {}

    L = []
    L.append(f"# Retail Analytics Pipeline — Run Report\n")
    L.append(f"- **Run ID:** {m['run_id']}")
    L.append(f"- **Timestamp:** {m['timestamp']}")
    L.append(f"- **Duration:** {m['duration_seconds']:.1f}s")
    L.append(f"- **Final status:** **{m['status']}**")
    if m.get("failed_stage"):
        L.append(f"- **Failed stage:** {m['failed_stage']}")

    L.append("\n## Data\n")
    raw, cl = d(m.get("input")), d(m.get("cleaned"))
    L.append(table([
        ["Metric", "Value"],
        ["Raw rows", f"{raw.get('rows', 'n/a'):,}" if isinstance(raw.get('rows'), int) else "n/a"],
        ["Cleaned rows", f"{cl.get('rows', 'n/a'):,}" if isinstance(cl.get('rows'), int) else "n/a"],
        ["Cleaned columns", str(cl.get("columns", "n/a"))],
        ["Customers (distinct)", str(d(m.get("metrics")).get("python", {}).get("customers", "n/a"))],
        ["Products (stock codes)", str(d(m.get("metrics")).get("python", {}).get("products", "n/a"))],
    ]))

    L.append("\n## Data Quality\n")
    dq = d(m.get("data_quality"))
    L.append(table([
        ["Check", "Value"],
        ["Rows", f"{dq.get('rows', 'n/a'):,}" if isinstance(dq.get('rows'), int) else "n/a"],
        ["Columns", str(dq.get("columns", "n/a"))],
        ["Missing critical fields", str(d(dq.get("summary")).get("missing_critical", "n/a"))],
        ["Duplicate rows", str(d(dq.get("summary")).get("duplicate_rows", "n/a"))],
        ["Invalid dates", str(d(dq.get("summary")).get("invalid_dates", "n/a"))],
        ["Status", str(dq.get("status", "n/a"))],
    ]))

    L.append("\n## Database\n")
    db = d(m.get("database"))
    L.append(table([
        ["Table", "Rows"],
        [db.get("table", "n/a"), f"{db.get('rows', 'n/a'):,}" if isinstance(db.get('rows'), int) else "n/a"],
    ]))

    L.append("\n## SQL Analytics\n")
    rows = m.get("sql_analytics") or []
    L.append(table([["Script", "Status", "Seconds"]] +
                   [[r["name"], r["status"], f"{r['seconds']:.2f}"] for r in rows]))

    L.append("\n## Excel\n")
    ex = d(m.get("excel"))
    L.append(table([
        ["Workbook", "Sheets"],
        [ex.get("path", "n/a"), f"{ex.get('sheet_count', 'n/a')}"],
    ]))

    L.append("\n## Power BI\n")
    pbi = d(m.get("powerbi"))
    if pbi.get("files"):
        L.append(table([["File", "Rows"]] + [[k, f"{v:,}"] for k, v in pbi["files"].items()]))
    else:
        L.append("Skipped (--skip-powerbi).")
    val = d(m.get("validation"))
    if val:
        L.append(f"\n- Power BI validation: {val.get('validate_pbi', {}).get('tail', 'skipped')}")

    L.append("\n## Reconciliation\n")
    recon = d(m.get("reconciliation"))
    L.append(f"Status: **{recon.get('status', 'n/a')}**  ({recon.get('metric_count', 0)} metric rows)")
    metrics = d(m.get("metrics"))
    L.append("```")
    L.append(f"{'Metric':<28}{'Python':>16}{'SQL':>16}{'Excel':>16}{'PBI':>16}")
    for key, label, _, fmt in _RECON_METRIC_ORDER:
        pm = d(metrics.get("python")).get(key)
        sm = d(metrics.get("sql")).get(key)
        em = d(metrics.get("excel")).get(key)
        pb = d(metrics.get("pbi")).get(key)
        L.append(f"{label:<28}{fmt(pm) if pm is not None else 'n/a':>16}"
                 f"{fmt(sm) if sm is not None else 'n/a':>16}"
                 f"{fmt(em) if em is not None else 'n/a':>16}"
                 f"{fmt(pb) if pb is not None else 'n/a':>16}")
    L.append("```")
    L.append(f"\n**PIPELINE: {m['status']}**\n")
    return "\n".join(L)


_RECON_METRIC_ORDER = [
    ("revenue", "Revenue", 0.02, lambda v: f"£{v:,.2f}"),
    ("orders", "Orders", 0, lambda v: f"{v:,}"),
    ("customers", "Customers", 0, lambda v: f"{v:,}"),
    ("products", "Products", 0, lambda v: f"{v:,}"),
    ("units", "Units", 0, lambda v: f"{v:,}"),
    ("aov", "AOV", 0.01, lambda v: f"£{v:,.2f}"),
    ("repeat_customers", "Repeat Customers", 0, lambda v: f"{v:,}"),
    ("customer_revenue", "Customer Revenue", 0.02, lambda v: f"£{v:,.2f}"),
    ("cohort_customers", "Cohort Customers", 0, lambda v: f"{v:,}"),
]


# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------

def _run_stage(index: int, name: str, fn, ctx: dict) -> tuple[str, float]:
    log = ctx["log"]
    log.stage(index, TOTAL_STAGES, name, "RUNNING")
    t0 = time.time()
    try:
        detail = fn(ctx)
        elapsed = time.time() - t0
        log.stage(index, TOTAL_STAGES, name, "PASS", detail)
        return "PASS", elapsed
    except SkippedStage as s:
        elapsed = time.time() - t0
        log.stage(index, TOTAL_STAGES, name, "SKIPPED", s.message)
        return "SKIPPED", elapsed
    except PipelineError as e:
        elapsed = time.time() - t0
        log.stage(index, TOTAL_STAGES, name, "FAIL")
        raise StageFailure(index, name, str(e)) from e


def pipeline(config: cfg.Config, log: PipelineLogger) -> int:
    ctx = {
        "config": config,
        "log": log,
        "run_id": run_id(),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "stages": [],
        "total_seconds": 0.0,
        "_t_start": time.time(),
    }
    log.banner("RETAIL ANALYTICS PIPELINE", ctx["run_id"])

    stage_fns = [
        stage_ingest, stage_clean, stage_data_quality, stage_postgresql,
        stage_sql_analytics, stage_powerbi_dataset, stage_excel_report,
        stage_full_validation, stage_final_report,
    ]
    t_start = time.time()
    try:
        for i, fn in enumerate(stage_fns, start=1):
            status, elapsed = _run_stage(i, STAGE_NAMES[i - 1], fn, ctx)
            if i < TOTAL_STAGES:  # FINAL REPORT appends its own entry (it writes the manifest)
                ctx["stages"].append({"name": STAGE_NAMES[i - 1], "status": status, "seconds": round(elapsed, 2)})
    except StageFailure as sf:
        ctx["failed_stage"] = sf.stage_name
        ctx["stages"].append({"name": sf.stage_name, "status": "FAIL", "seconds": None})
        log.blank()
        log.error(f"stage failed: {sf.stage_name}")
        log.error(f"reason:\n{sf.reason}")
        if config.debug:
            traceback.print_exc()
        ctx["total_seconds"] = time.time() - t_start
        _write_failure_artifacts(config, ctx)
        log.blank()
        log._emit("Pipeline stopped. Exit code: 1")
        return 1

    ctx["total_seconds"] = time.time() - t_start
    _print_summary(ctx, log)
    return 0


def _print_summary(ctx: dict, log: PipelineLogger) -> None:
    log.blank()
    bar = "=" * 60
    log._emit(bar)
    for s in ctx["stages"]:
        detail = ""
        idx = STAGE_NAMES.index(s["name"]) + 1
        log.stage(idx, TOTAL_STAGES, s["name"], s["status"],
                  f"{s['seconds']:.1f}s" if s.get("seconds") is not None else "")
    log._emit(bar)
    log._emit(f"PIPELINE STATUS: {SUCCESS}")
    log._emit(f"Total duration: {ctx['total_seconds']:.1f}s")
    log._emit(bar)


def _write_failure_artifacts(config: cfg.Config, ctx: dict) -> None:
    """Write the manifest + report for the final state (used on success too)."""
    try:
        status = SUCCESS if ctx.get("failed_stage") is None else FAILED
        manifest = build_manifest(ctx, status)
        config.output_dir.mkdir(parents=True, exist_ok=True)
        (config.output_dir / "pipeline_run.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8")
        (config.output_dir / "pipeline_run_report.md").write_text(
            render_report(manifest), encoding="utf-8")
    except Exception:  # noqa: BLE001 - reporting must never crash the process
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", help="source dataset path (default: online_retail.csv / INPUT_DATA_PATH)")
    parser.add_argument("--db-url", help="PostgreSQL connection string (overrides DATABASE_URL)")
    parser.add_argument("--skip-powerbi", action="store_true", help="skip Power BI dataset + validation")
    parser.add_argument("--skip-excel", action="store_true", help="skip the Excel cohort-sheet build")
    parser.add_argument("--debug", action="store_true", help="print full tracebacks on failure")
    args = parser.parse_args(argv)

    try:
        config = cfg.build_config(
            input_path=args.input,
            db_url=args.db_url,
            skip_powerbi=args.skip_powerbi,
            skip_excel=args.skip_excel,
            debug=args.debug,
        )
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print("Pipeline stopped. Exit code: 1", file=sys.stderr)
        return 1

    config.output_dir.mkdir(parents=True, exist_ok=True)
    log_file = config.output_dir / "pipeline_run.log"
    log = PipelineLogger(log_file)
    try:
        code = pipeline(config, log)
    finally:
        log.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
