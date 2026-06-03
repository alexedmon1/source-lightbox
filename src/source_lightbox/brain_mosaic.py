"""Anatomy-aware ROI brain mosaics, delegated to source-analytics.

Rendering ROI effect sizes on actual brain anatomy needs source-analytics
(`source_analytics.viz.brain_roi`) plus its bundled Allen atlas and the pandas/
nibabel stack. Rather than pull that heavy tree into source-lightbox, we shell
out to the source-analytics venv's Python (see ``_brain_render_worker.py``).

Brain rendering is therefore *optional*: if the source-analytics interpreter
isn't found, callers fall back to flat heatmaps. This keeps the lightbox
installable on its own while any study that has source-analytics gets
publication-style mosaics in its gallery.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_WORKER = Path(__file__).parent / "_brain_render_worker.py"

# Conventional location of the source-analytics venv interpreter.
_DEFAULT_PY = Path.home() / "sandbox" / "source-analytics" / ".venv" / "bin" / "python"


def resolve_python(python_path: str | Path | None) -> Path:
    return Path(python_path) if python_path else _DEFAULT_PY


def brain_available(python_path: str | Path | None = None) -> bool:
    """True if the source-analytics interpreter exists and can import the viz."""
    py = resolve_python(python_path)
    if not py.exists():
        return False
    probe = subprocess.run(
        [str(py), "-c", "import source_analytics.viz.brain_roi"],
        capture_output=True,
    )
    return probe.returncode == 0


def render_roi_mosaics(
    table_path: str | Path,
    *,
    categories: str | Path,
    out_dir: str | Path,
    analysis_name: str,
    contrasts: list[str] | None = None,
    labels: dict | None = None,
    power_type: str | None = "relative",
    alpha: float = 0.05,
    python_path: str | Path | None = None,
    log=lambda *a, **k: None,
) -> list[Path]:
    """Render brain mosaics for one ROI posthoc table via source-analytics.

    Returns the list of written PNG paths (empty on any failure — never raises).
    """
    py = resolve_python(python_path)
    payload = {
        "csv": str(table_path),
        "categories": str(categories),
        "out_dir": str(out_dir),
        "analysis_name": analysis_name,
        "contrasts": contrasts,
        "labels": labels,
        "power_type": power_type,
        "alpha": alpha,
    }
    proc = subprocess.run(
        [str(py), str(_WORKER), json.dumps(payload)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        log(f"  WARNING: brain mosaic render failed [{analysis_name}]: "
            f"{proc.stderr.strip()[-300:]}")
        return []
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    try:
        return [Path(p) for p in json.loads(last)]
    except (ValueError, IndexError):
        log(f"  WARNING: brain mosaic [{analysis_name}]: unparseable output: {proc.stdout[:200]}")
        return []
