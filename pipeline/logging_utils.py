"""Structured console + file logging for the pipeline.

Every line is written both to stdout (console) and to the run log file so a
failed run always leaves a full record behind.
"""

from __future__ import annotations

import sys
from pathlib import Path

W = 16  # width of the stage-name column in the summary table


class PipelineLogger:
    def __init__(self, log_file: Path | None = None) -> None:
        self._fh = None
        if log_file is not None:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(log_file, "w", encoding="utf-8", newline="\n")

    def close(self) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def _emit(self, line: str) -> None:
        print(line)
        if self._fh is not None:
            self._fh.write(line + "\n")
            self._fh.flush()

    def banner(self, title: str, run_id: str) -> None:
        bar = "=" * 60
        self._emit(bar)
        self._emit(title)
        self._emit(f"Run ID: {run_id}")
        self._emit(bar)

    def stage(self, index: int, total: int, name: str, status: str, detail: str = "") -> None:
        label = f"[{index}/{total}] {name.upper()}".ljust(12 + W)
        suffix = f"  {detail}" if detail else ""
        self._emit(f"{label}{status}{suffix}")

    def info(self, msg: str) -> None:
        self._emit(f"  {msg}")

    def detail(self, msg: str) -> None:
        self._emit(f"    {msg}")

    def warning(self, msg: str) -> None:
        self._emit(f"  WARNING: {msg}")

    def error(self, msg: str) -> None:
        self._emit(f"  ERROR: {msg}")

    def blank(self) -> None:
        self._emit("")
