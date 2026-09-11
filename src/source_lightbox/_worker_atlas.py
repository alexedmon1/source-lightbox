"""Atlas and ROI-category resolution for the render workers.

Runs inside the *source-analytics* interpreter: the worker scripts beside it
import it by path, and source-lightbox itself never needs source_analytics. Only
the functions that look up atlas data import it, lazily.

Categories, first match wins:

1. explicit: a mapping, or a YAML path with a top-level ``roi_categories:``.
   source-lightbox passes the study's own map from the study YAML, which is the
   map source-analytics analysed with.
2. the named atlas's OWN category file (source-analytics with ``resolve_atlas``).
3. a best-overlap guess over every category file shipped with the atlas data.

Step 3 used to be the only path, and it globbed for files named exactly
``roi_categories.yaml``. allen32, allen26 and allen64 share one directory and
only allen32's category file carries that name, so an allen26 study got
allen32's partition: 20 of its 26 parcels, with the six merged parcels missing
from every circos.
"""

from __future__ import annotations

import glob
import inspect
from pathlib import Path

import yaml

# Atlases the source-analytics mosaic default (``"allen"`` = allen32) already
# draws correctly, so they render byte-identically without an explicit atlas.
_DEFAULT_DRAWN = {None, "", "allen", "allen32"}


def _unwrap(data) -> dict | None:
    if isinstance(data, dict):
        data = data.get("roi_categories", data)
    if not isinstance(data, dict):
        return None
    cats = {k: list(v) for k, v in data.items() if isinstance(v, (list, tuple))}
    return cats or None


def load_categories(spec) -> dict | None:
    """An explicit category map: a mapping or a YAML path. None if not given."""
    if not spec:
        return None
    if isinstance(spec, dict):
        return _unwrap(spec)
    with open(spec) as f:
        return _unwrap(yaml.safe_load(f))


def members(categories: dict) -> set[str]:
    return {roi for rois in categories.values() for roi in rois}


def guess_from_files(root, rois) -> dict | None:
    """The fallback: the category file under ``root`` that covers most of ``rois``."""
    rois = set(rois)
    best, best_overlap = None, 0
    for path in sorted(glob.glob(str(Path(root) / "**" / "roi_categories*.yaml"), recursive=True)):
        try:
            cats = load_categories(path)
        except Exception:  # noqa: BLE001 -- an unreadable file is simply not a candidate
            continue
        overlap = len(members(cats) & rois) if cats else 0
        if overlap > best_overlap:
            best, best_overlap = cats, overlap
    return best


def _atlas_own(atlas) -> dict | None:
    if not atlas:
        return None
    try:
        from source_analytics.atlas import load_roi_categories, resolve_atlas
    except ImportError:            # source-analytics predates resolve_atlas
        return None
    try:
        return _unwrap(load_roi_categories(resolve_atlas(atlas_name=atlas)))
    except (FileNotFoundError, ValueError):
        return None


def resolve_categories(spec, atlas, rois) -> tuple[dict | None, str]:
    """``(categories, source)`` by the precedence in the module docstring."""
    cats = load_categories(spec)
    if cats:
        return cats, "the study config"
    rois = set(rois)
    cats = _atlas_own(atlas)
    if cats and members(cats) & rois:
        return cats, f"atlas {atlas}"
    try:
        from source_analytics.atlas import find_atlas_dir
        root = find_atlas_dir()
    except Exception:  # noqa: BLE001
        return None, "no atlas data"
    return guess_from_files(root, rois), "a best-overlap guess"


def mosaic_atlas_kwargs(atlas, render_fn) -> tuple[dict, str | None]:
    """The keyword that makes ``render_fn`` draw the study's atlas, and a warning
    when this source-analytics cannot (it then draws allen32's label volume)."""
    if atlas in _DEFAULT_DRAWN:
        return {}, None
    if "atlas" in inspect.signature(render_fn).parameters:
        return {"atlas": atlas}, None
    return {}, (f"this source-analytics predates per-atlas mosaics, so it draws allen32's "
                f"label volume: {atlas} parcels that allen32 lacks will render blank")
