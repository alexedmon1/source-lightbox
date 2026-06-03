"""Render standardized figures from source-analytics stat tables at build time.

Philosophy: **one canonical overview figure per analysis module**. For each
``(source, paradigm, analysis)`` group we pick the single most informative table
(an effect-size summary over per-unit detail) and render exactly one figure —
typically a contrast x band heatmap of the primary metric. This keeps a gallery
to a handful of analysis figures that a reader can actually absorb, while staying
fully automatic: any study whose tables follow the source-analytics schema
conventions gets the same overview set with no per-study configuration.

The renderers are *column-driven*: each declares which columns it needs
(``matches``) rather than keying off a module name. A module whose tables match
no renderer simply contributes no figure — its tables still appear in the gallery
as sortable CSVs. Rendering never aborts the build: per-table failures are caught
and logged by :func:`render_table_figures`.
"""

from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: no display, safe under any build environment

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from .manifest import _read_csv  # noqa: E402
from .scanner import FigureEntry, _slugify  # noqa: E402

# Canonical Jonak-style band order; categories not in this list keep file order.
BAND_ORDER = ["Delta", "Theta", "Alpha", "Beta", "Low Gamma", "High Gamma"]

# Columns scanned, in precedence order, to decide significance of a row.
_SIG_PVAL_COLS = ("q_value", "group_q", "p_corrected", "p_value", "p")

# Per-unit raw tables (one row per vertex) must not be force-fit into a
# contrast x band heatmap — their summaries live in dedicated *_summary tables.
_PER_VERTEX_COLS = ("vertex_idx", "vertex")

# A measure/dv column that an overview figure facets on; in overview mode we
# render only the single preferred value below.
_FACET_COLS = ("metric", "dv", "power_type")
_FACET_PREF = ("relative", "coherence", "exponent", "te", "absolute")

# Preferred contrast for a single-contrast overview (e.g. per-ROI maps).
_CONTRAST_PREF = ("disease", "rescue")


# --------------------------------------------------------------------------- #
# Small parsing / lookup helpers
# --------------------------------------------------------------------------- #
def _to_float(value) -> float | None:
    """Parse a CSV cell to float, returning None for blanks / NA / NaN."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _records(headers: list[str], rows: list[list[str]]) -> list[dict]:
    """Turn parallel headers/rows into a list of column->value dicts."""
    return [dict(zip(headers, r)) for r in rows]


def _has(headers: list[str], *cols: str) -> bool:
    return all(c in headers for c in cols)


def _any(headers: list[str], *cols: str) -> bool:
    return any(c in headers for c in cols)


def _is_sig(rec: dict) -> bool:
    """Significance of a row: explicit flag, else first p/q column < 0.05."""
    flag = rec.get("significant")
    if flag not in (None, ""):
        return str(flag).strip().upper() in ("TRUE", "1", "YES", "T")
    for col in _SIG_PVAL_COLS:
        if rec.get(col) not in (None, ""):
            f = _to_float(rec[col])
            if f is not None:
                return f < 0.05
    return False


def _unique(records: list[dict], key: str) -> list[str]:
    """Distinct non-empty values of ``key`` in first-seen order."""
    seen: list[str] = []
    for rec in records:
        v = rec.get(key)
        if v not in (None, "") and v not in seen:
            seen.append(v)
    return seen


def _order_categories(cats: list[str], key: str) -> list[str]:
    """Apply canonical band order when the axis is a band; else keep order."""
    if key != "band":
        return cats
    known = [b for b in BAND_ORDER if b in cats]
    extra = [c for c in cats if c not in BAND_ORDER]
    return known + extra


def _facet_column(headers, records):
    """Return (column, values) of the first present measure/dv facet column."""
    for c in _FACET_COLS:
        if c in headers:
            vals = _unique(records, c)
            if vals:
                return c, vals
    return None, [None]


def _pick_preferred(values, prefs):
    """First value whose lowercased text contains a preference, else the first."""
    for pref in prefs:
        for v in values:
            if pref in str(v).lower():
                return v
    return values[0] if values else None


# --------------------------------------------------------------------------- #
# Shared drawing primitives
# --------------------------------------------------------------------------- #
def _grid(records, row_key, col_key, value_fn, sig_fn=_is_sig, agg="last"):
    """Build a (values, rows, cols, sig_mask) grid from long-format records.

    agg="last" keeps the final value per cell (clean one-row-per-cell tables);
    agg="max_abs" keeps the largest-magnitude value and ORs significance across
    all rows mapping to that cell (e.g. multiple clusters per band).
    """
    rows: list[str] = []
    cols: list[str] = []
    val: dict[tuple[str, str], float] = {}
    sig: dict[tuple[str, str], bool] = {}
    for rec in records:
        r, c = rec.get(row_key), rec.get(col_key)
        if r in (None, "") or c in (None, ""):
            continue
        v = value_fn(rec)
        if v is None:
            continue
        if r not in rows:
            rows.append(r)
        if c not in cols:
            cols.append(c)
        key = (r, c)
        if agg == "max_abs":
            if key not in val or abs(v) > abs(val[key]):
                val[key] = v
            sig[key] = sig.get(key, False) or sig_fn(rec)
        else:
            val[key] = v
            sig[key] = sig_fn(rec)

    cols = _order_categories(cols, col_key)
    mat = np.full((len(rows), len(cols)), np.nan)
    smask = np.zeros((len(rows), len(cols)), dtype=bool)
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            if (r, c) in val:
                mat[i, j] = val[(r, c)]
                smask[i, j] = sig[(r, c)]
    return mat, rows, cols, smask


def _heatmap(mat, rows, cols, smask, title, out_path, dpi,
             center=0.0, value_label="Hedges g", cmap="RdBu_r",
             vmin=None, vmax=None, int_annot=False):
    """Heatmap with significance stars.

    Diverging around ``center`` by default; pass ``vmin``/``vmax`` for a fixed
    (e.g. sequential) scale. ``int_annot`` formats cell labels as integers.
    """
    n_r, n_c = mat.shape
    fig, ax = plt.subplots(figsize=(max(4.0, 0.65 * n_c + 2.5), max(2.5, 0.45 * n_r + 1.4)))
    finite = mat[np.isfinite(mat)]
    if vmin is not None or vmax is not None:
        lo = vmin if vmin is not None else (float(np.min(finite)) if finite.size else 0.0)
        hi = vmax if vmax is not None else (float(np.max(finite)) if finite.size else 1.0)
        if hi <= lo:
            hi = lo + 1.0
    else:
        dev = float(np.max(np.abs(finite - center))) if finite.size else 1.0
        dev = dev or 1.0
        lo, hi = center - dev, center + dev
    im = ax.imshow(mat, cmap=cmap, vmin=lo, vmax=hi, aspect="auto")
    ax.set_xticks(range(n_c))
    ax.set_xticklabels(cols, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(n_r))
    ax.set_yticklabels(rows, fontsize=8)
    for i in range(n_r):
        for j in range(n_c):
            if np.isfinite(mat[i, j]):
                v = mat[i, j]
                label = (f"{int(round(v))}" if int_annot else f"{v:.2f}") + ("★" if smask[i, j] else "")
                frac = (v - lo) / (hi - lo) if hi > lo else 0.0
                ax.text(
                    j, i, label, ha="center", va="center", fontsize=7,
                    color="white" if frac > 0.62 else "black",
                )
    ax.set_title(title, fontsize=10)
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label(value_label, fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def _bar(labels, values, sig_flags, title, ylabel, out_path, dpi, baseline=None):
    """Bar chart; significant bars in crimson, others steel-blue."""
    fig, ax = plt.subplots(figsize=(max(4.0, 0.5 * len(labels) + 2.0), 3.4))
    colors = ["#c0392b" if s else "#4a78b5" for s in sig_flags]
    ax.bar(range(len(labels)), values, color=colors)
    if baseline is not None:
        ax.axhline(baseline, color="gray", ls="--", lw=1)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(title, fontsize=10)
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi)
    plt.close(fig)


def _facet_heatmaps(records, headers, out_dir, stem, dpi, value_fn, *,
                    col_key, sig_fn=_is_sig, agg="last", center=0.0,
                    value_label="Hedges g", cmap="RdBu_r", suffix="effect_size",
                    single=False):
    """Emit contrast x ``col_key`` heatmap(s), faceted by the measure column.

    With ``single=True`` (overview mode) only the preferred facet value is drawn,
    giving exactly one figure.
    """
    fcol, fvals = _facet_column(headers, records)
    if single and fcol:
        fvals = [_pick_preferred(fvals, _FACET_PREF)]
    out = []
    for fval in fvals:
        subset = records if fcol is None else [r for r in records if r.get(fcol) == fval]
        mat, rows, cols, smask = _grid(subset, "contrast", col_key, value_fn, sig_fn, agg)
        if not rows or not cols:
            continue
        title = stem + (f" — {fval}" if fval else "")
        fname = f"{stem}__{suffix}" + (f"_{_slugify(fval)}" if fval else "") + ".png"
        path = out_dir / fname
        _heatmap(mat, rows, cols, smask, title, path, dpi,
                 center=center, value_label=value_label, cmap=cmap)
        out.append(path)
    return out


# --------------------------------------------------------------------------- #
# Renderers (first match in REGISTRY wins). Each render() honors overview=True
# by returning exactly one figure.
# --------------------------------------------------------------------------- #
class _Renderer:
    name = "base"

    @staticmethod
    def matches(headers: list[str]) -> bool:  # pragma: no cover - overridden
        return False

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):  # pragma: no cover
        return []


class RoiBandHeatmap(_Renderer):
    """Per-ROI effect-size map: one ROI x band heatmap per contrast."""

    name = "roi_band_heatmap"

    @staticmethod
    def matches(headers):
        return _has(headers, "contrast", "roi", "band", "hedges_g")

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):
        contrasts = _unique(records, "contrast")
        if overview and contrasts:
            contrasts = [_pick_preferred(contrasts, _CONTRAST_PREF)]
        out = []
        for contrast in contrasts:
            subset = [r for r in records if r.get("contrast") == contrast]
            mat, rows, cols, smask = _grid(
                subset, "roi", "band", lambda r: _to_float(r.get("hedges_g"))
            )
            if not rows or not cols:
                continue
            path = out_dir / f"{stem}__{_slugify(contrast)}.png"
            _heatmap(mat, rows, cols, smask, f"{stem} — {contrast}", path, dpi)
            out.append(path)
        return out


class MvpaHeatmap(_Renderer):
    """Per-band decoding strength as a contrast x band heatmap (centered at chance)."""

    name = "mvpa_heatmap"

    @staticmethod
    def matches(headers):
        return (
            "band" in headers
            and _any(headers, "auc", "accuracy")
            and _any(headers, "ci_lower", "ci_upper")
        )

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):
        metric = "auc" if "auc" in headers else "accuracy"
        return _facet_heatmaps(
            records, headers, out_dir, stem, dpi,
            value_fn=lambda r: _to_float(r.get(metric)),
            col_key="band", center=0.5, value_label=metric.upper(),
            cmap="RdBu_r", suffix="mvpa", single=overview,
        )


def _parse_nbs_key(key: str):
    """Split an NBS key ``<contrast>_<band>[_<metric>]`` into its parts.

    The key joins fields with ``_`` but bands themselves contain spaces
    ("Low Gamma"), so we locate a known band token rather than naive splitting.
    Returns ``(contrast, band, metric)`` or ``(None, None, None)``.
    """
    for band in sorted(BAND_ORDER + ["Epsilon"], key=len, reverse=True):
        marker = "_" + band
        idx = key.find(marker)
        if idx < 0:
            continue
        rest = key[idx + len(marker):]
        if rest == "" or rest.startswith("_"):
            return key[:idx], band, (rest[1:] if rest.startswith("_") else "")
    return None, None, None


class NbsComponentPlot(_Renderer):
    """Network-Based Statistic as a contrast x band heatmap of the largest
    significant component's size, faceted by connectivity metric."""

    name = "nbs_heatmap"

    @staticmethod
    def matches(headers):
        return _has(headers, "key", "component", "n_edges", "p_corrected")

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):
        labels = contrast_labels or {}
        # Parse keys into contrast/band/metric; keep the largest component per cell.
        parsed = []
        for rec in records:
            key = rec.get("key")
            if not key:
                continue
            contrast, band, metric = _parse_nbs_key(str(key))
            if contrast is None:
                continue
            parsed.append({
                "contrast": labels.get(contrast, contrast),
                "band": band,
                "metric": metric,
                "n_edges": rec.get("n_edges"),
                "p_corrected": rec.get("p_corrected"),
            })

        if not parsed:  # unparseable keys → fall back to the per-key bar chart
            largest: dict[str, dict] = {}
            for rec in records:
                key = rec.get("key")
                if key in (None, ""):
                    continue
                n = _to_float(rec.get("n_edges")) or 0.0
                if key not in largest or n > (_to_float(largest[key].get("n_edges")) or 0.0):
                    largest[key] = rec
            if not largest:
                return []
            keys = list(largest.keys())
            path = out_dir / f"{stem}__nbs.png"
            _bar(keys, [_to_float(largest[k].get("n_edges")) or 0.0 for k in keys],
                 [_is_sig(largest[k]) for k in keys], f"{stem} — largest component / key",
                 "n_edges", path, dpi)
            return [path]

        metrics = _unique(parsed, "metric") or [None]
        out = []
        for metric in metrics:
            subset = parsed if metric in (None, "") else [r for r in parsed if r.get("metric") == metric]
            mat, rows, cols, smask = _grid(
                subset, "contrast", "band",
                lambda r: _to_float(r.get("n_edges")), sig_fn=_is_sig, agg="max_abs",
            )
            if not rows or not cols:
                continue
            title = stem + (f" — {metric}" if metric else "")
            fname = f"{stem}__nbs" + (f"_{_slugify(metric)}" if metric else "") + ".png"
            path = out_dir / fname
            _heatmap(mat, rows, cols, smask, title, path, dpi,
                     value_label="largest component (edges); ★ p<0.05",
                     cmap="Blues", vmin=0, int_annot=True)
            out.append(path)
            if overview:
                break
        return out


class ClusterHeatmap(_Renderer):
    """Cluster strength as a contrast x band heatmap (signed max-magnitude stat)."""

    name = "cluster_heatmap"

    @staticmethod
    def matches(headers):
        return _has(headers, "band", "cluster_stat", "p_corrected")

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):
        return _facet_heatmaps(
            records, headers, out_dir, stem, dpi,
            value_fn=lambda r: _to_float(r.get("cluster_stat")),
            col_key="band", agg="max_abs", value_label="cluster stat",
            suffix="cluster", single=overview,
        )


class SummaryHeatmap(_Renderer):
    """Effect-size summary as a contrast x band heatmap, per metric facet."""

    name = "summary_heatmap"

    @staticmethod
    def matches(headers):
        return _has(headers, "band", "max_abs_hedges_g")

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):
        def sig_fn(rec):
            if "n_nominal_sig" in rec:
                return (_to_float(rec.get("n_nominal_sig")) or 0) > 0
            return _is_sig(rec)

        return _facet_heatmaps(
            records, headers, out_dir, stem, dpi,
            value_fn=lambda r: _to_float(r.get("max_abs_hedges_g")),
            col_key="band", sig_fn=sig_fn, value_label="max |Hedges g|",
            cmap="Reds", center=0.0, suffix="summary", single=overview,
        )


class EffectSizeHeatmap(_Renderer):
    """Contrast x band (or freq_pair) effect-size heatmap; faceted by metric.

    The general-purpose choice for clean one-row-per-cell effect-size tables.
    Skips per-vertex raw tables (their summaries are handled elsewhere).
    """

    name = "effect_size_heatmap"

    @staticmethod
    def matches(headers):
        if _any(headers, *_PER_VERTEX_COLS):
            return False
        return (
            "hedges_g" in headers
            and "contrast" in headers
            and _any(headers, "band", "freq_pair")
        )

    @staticmethod
    def render(records, headers, out_dir, stem, dpi, overview=False, contrast_labels=None):
        col_key = "band" if "band" in headers else "freq_pair"
        return _facet_heatmaps(
            records, headers, out_dir, stem, dpi,
            value_fn=lambda r: _to_float(r.get("hedges_g")),
            col_key=col_key, suffix="effect_size", single=overview,
        )


# Order matters: more specific renderers first.
REGISTRY: list[type[_Renderer]] = [
    RoiBandHeatmap,
    MvpaHeatmap,
    NbsComponentPlot,
    ClusterHeatmap,
    SummaryHeatmap,
    EffectSizeHeatmap,
]


def select_renderer(headers: list[str]) -> type[_Renderer] | None:
    """Return the first registered renderer whose column requirements match."""
    for renderer in REGISTRY:
        if renderer.matches(headers):
            return renderer
    return None


# --------------------------------------------------------------------------- #
# Module-level overview selection
# --------------------------------------------------------------------------- #
def _table_priority(filename: str) -> int:
    """Rank tables so the overview prefers global effect-size summaries over
    per-unit detail (ROI / vertex / directional) tables."""
    f = filename.lower()
    if "posthoc_global" in f:
        return 100
    if "_global" in f or f.endswith("global.csv"):
        return 90
    if "effect_size_summary" in f:
        return 75
    if "mvpa" in f:
        return 70
    if "nbs" in f:
        return 65
    if "cluster_results" in f:
        return 60
    if "summary" in f:
        return 55
    if "posthoc_region" in f:
        return 40
    if _any([f], "posthoc_roi", "voxelwise", "directional"):  # per-unit detail
        return 10
    return 30


def _roi_posthoc_table(group):
    """The per-ROI posthoc table in a module group, if present (for brain mosaics)."""
    for tbl in group:
        if "posthoc_roi" in tbl.filename.lower():
            return tbl
    return None


def _analysis_key(analysis: str) -> str:
    """Strip a leading ``roi_`` so 'roi_psd' -> 'psd' for ANALYSIS_CMAPS lookup."""
    return analysis[4:] if analysis.startswith("roi_") else analysis


def render_table_figures(tables, staging_dir, dpi: int = 150, log=lambda *a, **k: None,
                         brain=None, circos=None, contrast_labels=None):
    """Render figures per analysis module.

    Tables are grouped by ``(source_label, paradigm, analysis)``. For ROI modules
    with a per-ROI posthoc table, anatomy-aware brain mosaics are rendered (when
    ``brain`` is configured and source-analytics is available); otherwise the
    module gets a single flat overview figure from its highest-priority table.

    ``brain`` is an optional dict: ``{categories, contrasts, python, power_type}``.

    Returns a list of :class:`~source_lightbox.scanner.FigureEntry`
    (category ``"analytics"``).
    """
    staging = Path(staging_dir)

    # Group tables by module.
    modules: dict[tuple[str, str, str], list] = {}
    for tbl in tables:
        modules.setdefault((tbl.source_label, tbl.paradigm, tbl.analysis), []).append(tbl)

    # Brain mosaics and circos are optional and require source-analytics.
    brain_ok = False
    if brain and brain.get("categories"):
        from . import brain_mosaic

        brain_ok = brain_mosaic.brain_available(brain.get("python"))
        if not brain_ok:
            log("  (brain mosaics unavailable — source-analytics not found; using heatmaps)")

    circos_ok = False
    if circos and circos.get("contrasts"):
        from . import circos as circos_mod

        circos_ok = circos_mod.circos_available(circos.get("python"))

    figures: list[FigureEntry] = []
    for (source, paradigm, analysis), group in modules.items():
        dest = staging / _slugify(source) / paradigm / analysis

        # 0. Connectivity circos: significance chord diagrams (32 ROIs grouped by
        #    region) for modules with a region-pair posthoc table + edge data.
        if circos_ok:
            region_tbl = next((t for t in group if "posthoc_region_pair" in t.filename.lower()), None)
            if region_tbl is not None:
                edges_csv = (Path(circos["analytics_dir"]) / paradigm / analysis
                             / "data" / f"{analysis}_edges.csv")
                if edges_csv.exists():
                    dest.mkdir(parents=True, exist_ok=True)
                    paths = circos_mod.render_circos(
                        edges_csv, region_tbl.src_path, dest, circos["contrasts"],
                        metrics=circos.get("metrics"),
                        labels=circos.get("labels"), python_path=circos.get("python"), log=log,
                    )
                    if paths:
                        for path in paths:
                            figures.append(FigureEntry(
                                src_path=path, category="analytics", source_label=source,
                                paradigm=paradigm, analysis=analysis, filename=path.name))
                        continue  # circos stand in for this module's overview

        # 1. Brain mosaics for ROI posthoc modules (replace the flat overview).
        if brain_ok:
            roi_tbl = _roi_posthoc_table(group)
            if roi_tbl is not None:
                dest.mkdir(parents=True, exist_ok=True)
                paths = brain_mosaic.render_roi_mosaics(
                    roi_tbl.src_path,
                    categories=brain["categories"],
                    out_dir=dest,
                    analysis_name=_analysis_key(analysis),
                    contrasts=brain.get("contrasts"),
                    labels=brain.get("labels"),
                    power_type=brain.get("power_type", "relative"),
                    python_path=brain.get("python"),
                    log=log,
                )
                if paths:
                    for path in paths:
                        figures.append(
                            FigureEntry(
                                src_path=path, category="analytics", source_label=source,
                                paradigm=paradigm, analysis=analysis, filename=path.name,
                            )
                        )
                    continue  # mosaics stand in for this module's overview

        # 2. Flat overview heatmap from the highest-priority renderable table.
        ranked = sorted(group, key=lambda t: _table_priority(t.filename), reverse=True)

        chosen = None
        for tbl in ranked:
            try:
                data = _read_csv(tbl.src_path)
            except Exception as exc:  # noqa: BLE001
                log(f"  WARNING: render skipped (unreadable) {tbl.src_path}: {exc}")
                continue
            if select_renderer(data["headers"]) is not None:
                chosen = (tbl, data)
                break
        if chosen is None:
            continue

        tbl, data = chosen
        renderer = select_renderer(data["headers"])
        records = _records(data["headers"], data["rows"])
        if contrast_labels:
            for rec in records:
                if rec.get("contrast") in contrast_labels:
                    rec["contrast"] = contrast_labels[rec["contrast"]]
        dest.mkdir(parents=True, exist_ok=True)
        stem = Path(tbl.filename).stem
        try:
            paths = renderer.render(records, data["headers"], dest, stem, dpi, overview=True,
                                    contrast_labels=contrast_labels)
        except Exception as exc:  # noqa: BLE001
            log(f"  WARNING: render failed {tbl.filename} [{renderer.name}]: {exc}")
            continue
        for path in paths:
            figures.append(
                FigureEntry(
                    src_path=path,
                    category="analytics",
                    source_label=source,
                    paradigm=paradigm,
                    analysis=analysis,
                    filename=path.name,
                )
            )
    return figures
