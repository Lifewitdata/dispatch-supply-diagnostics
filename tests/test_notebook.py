import asyncio
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "python" / "02_root_cause_and_sizing.ipynb"

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def test_notebook_executes_analysis_and_renders_figures():
    notebook = nbformat.read(NOTEBOOK, as_version=4)
    NotebookClient(
        notebook,
        timeout=180,
        kernel_name="python3",
        resources={"metadata": {"path": str(NOTEBOOK.parent)}},
        record_timing=False,
    ).execute()
    code_cells = [cell for cell in notebook.cells if cell.cell_type == "code"]
    assert len(code_cells) == 8
    assert all(cell.execution_count is not None for cell in code_cells)
    assert not any(
        output.output_type == "error"
        for cell in code_cells
        for output in cell.outputs
    )
    text = "".join(
        output.get("text", "")
        for cell in code_cells
        for output in cell.outputs
        if output.output_type == "stream"
    )
    assert "events 304286" in text
    assert "R2 = 0.14" in text
    figures = sum(
        "image/png" in output.get("data", {})
        for cell in code_cells
        for output in cell.outputs
    )
    assert figures >= 2
