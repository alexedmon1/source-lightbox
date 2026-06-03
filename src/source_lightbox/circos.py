"""Connectivity circos diagrams, delegated to source-analytics.

Same pattern as :mod:`brain_mosaic`: shell out to the source-analytics venv
(which has ``connectivity_plots`` + the Allen atlas) so source-lightbox stays
lightweight. Optional — if the interpreter isn't found, callers skip circos.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_WORKER = Path(__file__).parent / "_circos_render_worker.py"
_DEFAULT_PY = Path.home() / "sandbox" / "source-analytics" / ".venv" / "bin" / "python"


def _resolve(python_path):
    return Path(python_path) if python_path else _DEFAULT_PY


def circos_available(python_path=None) -> bool:
    py = _resolve(python_path)
    if not py.exists():
        return False
    probe = subprocess.run(
        [str(py), "-c", "import source_analytics.viz.connectivity_plots"],
        capture_output=True,
    )
    return probe.returncode == 0


def render_circos(edges_csv, posthoc_csv, out_dir, contrasts, *,
                  metric="imag_coherence", labels=None, alpha=0.05,
                  python_path=None, log=lambda *a, **k: None):
    """Render significance circos for each significant (contrast, band).

    Returns the list of written PNG paths (empty on any failure — never raises).
    """
    py = _resolve(python_path)
    payload = {
        "edges_csv": str(edges_csv),
        "posthoc_csv": str(posthoc_csv),
        "out_dir": str(out_dir),
        "contrasts": contrasts,
        "metric": metric,
        "labels": labels,
        "alpha": alpha,
    }
    proc = subprocess.run(
        [str(py), str(_WORKER), json.dumps(payload)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        log(f"  WARNING: circos render failed: {proc.stderr.strip()[-300:]}")
        return []
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    try:
        return [Path(p) for p in json.loads(last)]
    except (ValueError, IndexError):
        log(f"  WARNING: circos: unparseable output: {proc.stdout[:200]}")
        return []
