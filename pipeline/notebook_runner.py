"""Notebook execution wrapper.

Reuses the project's existing validated cleaning notebook
(``OnlineRetail cleaning.ipynb``) as-is: every cell is executed in order by
``nbclient`` and the notebook file is left untouched (execution is in-memory,
nothing is written back to the .ipynb). The notebook's own side effects produce
the cleaned dataset and the Excel workbook.

Why not rewrite the cleaning in Python here? The notebook IS the validated
Phase 1 cleaning logic (date parsing, cancellations, duplicates, CustomerID,
TotalPrice, Month/Year/Hour). Re-implementing it would create a competing
analytics implementation, which Phase 5 explicitly forbids.
"""

from __future__ import annotations

import warnings
from pathlib import Path

import nbformat
from nbclient import NotebookClient

# nbclient's ZMQ support does not play well with the Windows Proactor event
# loop; the Selector policy keeps kernel communication working. No-op elsewhere.
try:
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
except (ImportError, ValueError):
    pass

# The kernel launches without encryption and prints an alarming (but harmless)
# IPKernelApp warning on every run; silence it.
warnings.filterwarnings("ignore", message=".*Kernel is running over TCP.*")
warnings.filterwarnings("ignore", message=".*Proactor event loop.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)


def execute_notebook(nb_path: Path, cwd: Path, timeout: int = 1800) -> None:
    """Execute every cell of *nb_path* in-memory with *cwd* as working dir.

    Raises RuntimeError if any cell raises.
    """
    nb = nbformat.read(str(nb_path), as_version=4)
    client = NotebookClient(
        nb,
        timeout=timeout,
        resources={"metadata": {"path": str(cwd)}},
    )
    try:
        client.execute()
    except Exception as exc:  # noqa: BLE001 - surface the failed cell clearly
        cell = getattr(exc, "cell", None)
        where = f" (cell {cell.execution_count})" if cell is not None else ""
        raise RuntimeError(f"notebook cell failed{where}: {exc}") from exc
