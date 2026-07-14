"""Generate a concise 'significant results by contrast' summary from stat tables.

The verbose ``ANALYSIS_SUMMARY.md`` that source-analytics writes is a full report,
not a summary. Instead of embedding it verbatim, we derive a short, scannable
digest directly from a module's effect-size table: which contrasts show
significant effects, in which bands, and in which direction.

Column-driven and reusable: any module with a ``contrast`` × category
(``band``/``freq_pair``/``parameter``) × effect (``hedges_g``/``coefficient``/
``auc``/``accuracy``) table gets a digest. Per-element tables (``roi``/
``vertex_idx``) are aggregated to one entry per (contrast, category) with a count
and the strongest effect, so a 30k-row table still renders a few chips. NBS
component tables (``*_nbs_results.csv``) get a dedicated sub-network digest.
"""

from __future__ import annotations

from html import escape

from .render import (
    _facet_column,
    _is_sig,
    _parse_nbs_key,
    _records,
    _table_priority,
    _to_float,
    _to_native,
    _unique,
)


# Effect columns in priority order: (column, label_fn, signed). ``signed`` effects
# get a direction arrow (▲/▼); unsigned effects (decoding metrics) read "vs chance".
# hedges_g stays first so modules that already produce a g-digest are unchanged.
_EFFECT_COLS = (
    ("hedges_g", lambda v: f"g={abs(v):.2f}", True),
    ("effect_size", lambda v: f"g={abs(v):.2f}", True),  # native alias of hedges_g
    ("coefficient", lambda v: f"&beta;={v:+.2f}", True),
    ("auc", lambda v: f"AUC={v:.2f}", False),
    ("accuracy", lambda v: f"acc={v:.2f}", False),
)


def _effect_column(headers: list[str]):
    """Return (column, label_fn, signed) for the first present effect column."""
    for col, fmt, signed in _EFFECT_COLS:
        if col in headers:
            return col, fmt, signed
    return None


def _element_column(headers: list[str]) -> str | None:
    """Per-element axis (``roi``/``vertex_idx``) that must be aggregated away."""
    for col in ("roi", "spatial", "vertex_idx"):
        if col in headers:
            return col
    return None


def _summary_table(tables: list[dict]) -> dict | None:
    """Pick the highest-priority table suitable for an effect digest: needs a
    ``contrast`` column, a category axis, and any recognized effect column."""
    candidates = [
        t for t in tables
        if ("contrast" in t["headers"] or "hypothesis" in t["headers"])
        and _category_column(t["headers"], _records(t["headers"], t["rows"])) is not None
        and _effect_column(t["headers"]) is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda t: _table_priority(t["filename"]))


def _nbs_table(tables: list[dict]) -> dict | None:
    """Pick an NBS component-results table (key/component/n_edges/p_corrected)."""
    for t in tables:
        h = t["headers"]
        if "key" in h and "p_corrected" in h and "n_edges" in h:
            return t
    return None


_GRAPH_METRIC_LABEL = {
    "global_efficiency": "global efficiency",
    "characteristic_path_length": "char. path length",
    "mean_clustering": "mean clustering",
    "mean_local_efficiency": "local efficiency",
    "small_worldness": "small-worldness",
    "modularity": "modularity",
    "transitivity": "transitivity",
    "assortativity": "assortativity",
}
_GRAPH_BAND_ORDER = ["Delta", "Theta", "Alpha", "Beta", "Low Gamma", "High Gamma", "Epsilon"]


def _comparison_table(tables: list[dict]) -> dict | None:
    """A source-vs-sensor comparison table (electrode_comparison): per band/dv ×
    contrast, a concordance ``correlation_r`` plus ``source_hedges_g`` /
    ``electrode_hedges_g`` with CIs."""
    cands = [t for t in tables
             if "correlation_r" in t["headers"] and "source_hedges_g" in t["headers"]
             and "electrode_hedges_g" in t["headers"]
             and ("contrast" in t["headers"] or "hypothesis" in t["headers"])]
    if not cands:
        return None
    # Prefer the spectral band-power comparison over the aperiodic one.
    cands.sort(key=lambda t: ("aperiodic" in t["filename"].lower(), t["filename"]))
    return cands[0]


def _ci_sig(rec: dict, level: str) -> bool:
    """True if the ``{level}_hedges_g`` CI excludes zero (same-sign bounds)."""
    lo = _to_float(rec.get(f"{level}_ci_lo"))
    hi = _to_float(rec.get(f"{level}_ci_hi"))
    return lo is not None and hi is not None and lo != 0 and (lo > 0) == (hi > 0)


def _build_comparison_summary(table: dict, _label, groups: dict) -> str | None:
    """Digest the source-vs-sensor comparison: cross-subject concordance (r) plus,
    per contrast, the band/power measures where the group effect is significant
    (95% CI excludes 0) at the source and/or sensor level, and which localizes it
    more sharply."""
    records = _to_native(_records(table["headers"], table["rows"]))
    all_contrasts = _unique(records, "hypothesis")

    rs_all = [_to_float(r.get("correlation_r")) for r in records]
    rs_all = [x for x in rs_all if x is not None]
    concord = ""
    if rs_all:
        concord = (' <span class="sig-key">source–sensor concordance r = '
                   f'{min(rs_all):.2f}–{max(rs_all):.2f} (median {sorted(rs_all)[len(rs_all)//2]:.2f})</span>.')

    def _measure(rec):
        band = str(rec.get("band") or "").strip()
        pt = str(rec.get("power_type") or rec.get("dv") or "").strip()
        return f"{band} {pt}".strip() if band else (pt or "value")

    sig_by_contrast: dict[str, list[dict]] = {}
    for r in records:
        if _ci_sig(r, "source") or _ci_sig(r, "electrode"):
            sig_by_contrast.setdefault(r.get("hypothesis"), []).append(r)

    item_by_contrast: dict[str, str] = {}
    n_findings = 0
    for contrast in all_contrasts:
        rows = sig_by_contrast.get(contrast)
        if not rows:
            continue
        chips = []
        for rec in sorted(rows, key=lambda r: -abs(_to_float(r.get("source_hedges_g")) or 0.0)):
            sg = _to_float(rec.get("source_hedges_g")) or 0.0
            eg = _to_float(rec.get("electrode_hedges_g")) or 0.0
            src = f'{_arrow(sg)} source <span class="g">g={abs(sg):.2f}</span>{"" if _ci_sig(rec,"source") else " (ns)"}'
            sen = f'{_arrow(eg)} sensor <span class="g">g={abs(eg):.2f}</span>{"" if _ci_sig(rec,"electrode") else " (ns)"}'
            sharper = ' <span class="sig-facet">source localizes sharper</span>' if abs(sg) > abs(eg) else ""
            chips.append(
                f'<span class="sig-item has-region"><strong>{escape(_measure(rec))}</strong> '
                f'<span class="sig-region">{src} · {sen}{sharper}</span></span>')
            n_findings += 1
        item_by_contrast[contrast] = (
            f'<li><span class="sig-contrast">{escape(str(_label(contrast)))}</span> '
            + "".join(chips) + "</li>")

    _fill_nulls(all_contrasts, item_by_contrast, _label, "No significant effect at either level")
    body = _render_body(all_contrasts, item_by_contrast, groups)
    html = '<div class="sig-summary">'
    html += (
        f'<p class="sig-lead">{n_findings} band/power measure'
        f'{"s" if n_findings != 1 else ""} significant at source and/or sensor '
        f"across {len(sig_by_contrast)} of {len(all_contrasts)} comparisons "
        f"(95% CI excludes 0).{concord}</p>"
    )
    html += body
    html += "</div>"
    return html


def _fcd_comparison_table(tables: list[dict]) -> dict | None:
    """The FCD source-vs-sensor comparison table (mean FCD + spatial CV)."""
    for t in tables:
        h = t["headers"]
        if ("corr_mean_r" in h and "source_mean_g" in h and "sensor_mean_g" in h
                and ("contrast" in h or "hypothesis" in h)):
            return t
    return None


def _build_fcd_comparison_summary(table: dict, _label, groups: dict) -> str | None:
    """Digest the FCD source-vs-sensor comparison: mean-FCD & spatial-CV
    concordance (r) plus, per contrast, the band × metric measures where the
    group effect is significant (95% CI excludes 0) at source and/or sensor."""
    records = _to_native(_records(table["headers"], table["rows"]))
    all_contrasts = _unique(records, "hypothesis")

    def _rng(col):
        xs = [_to_float(r.get(col)) for r in records]
        xs = [x for x in xs if x is not None]
        return f"{min(xs):.2f}–{max(xs):.2f}" if xs else None
    parts_r = []
    if _rng("corr_mean_r"):
        parts_r.append(f"mean-FCD r = {_rng('corr_mean_r')}")
    if _rng("corr_cv_r"):
        parts_r.append(f"spatial-CV r = {_rng('corr_cv_r')}")
    concord = f' <span class="sig-key">source–sensor concordance: {"; ".join(parts_r)}</span>.' if parts_r else ""

    def _measure(rec):
        return f"{str(rec.get('band') or '').strip()} {_pretty_metric(rec.get('metric'))}".strip()

    LEVELS = [("mean FCD", "source_mean", "sensor_mean"), ("spatial CV", "source_cv", "sensor_cv")]
    sig_by_contrast: dict[str, list[dict]] = {}
    for r in records:
        if any(_ci_sig(r, s) or _ci_sig(r, e) for _, s, e in LEVELS):
            sig_by_contrast.setdefault(r.get("hypothesis"), []).append(r)

    item_by_contrast: dict[str, str] = {}
    n_findings = 0
    for contrast in all_contrasts:
        rows = sig_by_contrast.get(contrast)
        if not rows:
            continue
        chips = []
        for rec in sorted(rows, key=lambda r: -abs(_to_float(r.get("source_mean_g")) or 0.0)):
            parts = []
            for lbl, src, sen in LEVELS:
                if _ci_sig(rec, src) or _ci_sig(rec, sen):
                    sg = _to_float(rec.get(f"{src}_g")) or 0.0
                    eg = _to_float(rec.get(f"{sen}_g")) or 0.0
                    parts.append(f'{lbl}: {_arrow(sg)} source <span class="g">g={abs(sg):.2f}</span>'
                                 f' · {_arrow(eg)} sensor <span class="g">g={abs(eg):.2f}</span>')
            chips.append(
                f'<span class="sig-item has-region"><strong>{escape(_measure(rec))}</strong>'
                f'<span class="sig-region">{" ; ".join(parts)}</span></span>')
            n_findings += 1
        item_by_contrast[contrast] = (
            f'<li><span class="sig-contrast">{escape(str(_label(contrast)))}</span> '
            + "".join(chips) + "</li>")

    _fill_nulls(all_contrasts, item_by_contrast, _label, "No significant effect at either level")
    body = _render_body(all_contrasts, item_by_contrast, groups)
    html = '<div class="sig-summary">'
    html += (
        f'<p class="sig-lead">{n_findings} band/metric FCD measure'
        f'{"s" if n_findings != 1 else ""} significant at source and/or sensor '
        f"across {len(sig_by_contrast)} of {len(all_contrasts)} comparisons "
        f"(95% CI excludes 0).{concord}</p>"
    )
    html += body
    html += "</div>"
    return html


def _roi_posthoc_table(tables: list[dict]) -> dict | None:
    """A per-ROI / per-channel posthoc table: a populated spatial unit column
    (``roi``/``spatial``) at ROI/channel scale (≈3–40 units, not a whole-brain
    vertex map), plus effect + significance + contrast. Used to name *which*
    ROIs differ, instead of the region-averaged global table that hides them."""
    best = None
    best_units = 0
    for t in tables:
        h = t["headers"]
        if "graph_metric" in h:   # nodal graph tables keep their own aggregation
            continue
        if not (("hypothesis" in h or "contrast" in h)
                and ("effect_size" in h or "hedges_g" in h) and "significant" in h):
            continue
        elem = _element_column(h)
        if elem not in ("roi", "spatial"):   # ROIs/channels only, not vertex maps
            continue
        recs = _records(h, t["rows"])
        units = {str(r.get(elem, "")).strip() for r in recs}
        units = {u for u in units if u.lower() not in _DEGENERATE}
        if not (3 <= len(units) <= 40):   # ROI/channel scale, not a vertex map
            continue
        # prefer the dedicated posthoc-per-unit table, else the most-detailed one
        score = (2 if "posthoc_roi" in t["filename"].lower() else
                 1 if "posthoc" in t["filename"].lower() else 0, len(units))
        if score > (2 if best and "posthoc_roi" in best["filename"].lower() else
                    1 if best and "posthoc" in best["filename"].lower() else 0, best_units):
            best, best_units = t, len(units)
    return best


def _roi_measure_label(rec: dict) -> str:
    """'Low Gamma relative' / 'exponent' — band + dv, collapsing the NA-band case."""
    band = str(rec.get("band") or "").strip()
    dv = str(rec.get("dv") or "").strip()
    if not band or band.lower() in _DEGENERATE:
        return dv or "value"
    return f"{band} {dv}" if dv and dv.lower() not in _DEGENERATE else band


# Canonical display for connectivity/coupling/method acronyms (matches the
# figure labels), so digests show 'AEC', 'dwPLI', … not 'aec', 'dwpli'.
_METRIC_DISPLAY = {
    "imag_coherence": "Imag. coherence", "coherence": "Coherence",
    "dwpli": "dwPLI", "wpli": "wPLI", "pli": "PLI", "dpli": "dPLI", "aec": "AEC",
    "partial_corr": "Partial corr.", "partial_correlation": "Partial corr.",
    "pac": "PAC", "aac": "AAC", "ppc": "PPC", "dtf": "DTF", "te": "TE",
    "inflow": "inflow", "outflow": "outflow", "netflow": "netflow",
}


def _pretty_metric(m) -> str:
    """Display form of a metric/measure token (AEC, dwPLI, …); pass others through."""
    if m is None:
        return ""
    return _METRIC_DISPLAY.get(str(m).strip().lower(), str(m))


# Band-name suffixes (lower/underscored) as they appear in connectivity figure
# filenames like ``circos_<metric>_<band>.png``. Multi-word bands are listed so
# ``low_gamma`` is matched before a bare ``gamma``.
_BAND_SUFFIXES = ("low_gamma", "high_gamma", "epsilon", "delta", "theta",
                  "alpha", "beta", "gamma")


def build_descriptive_matrix_summary(analysis, figure_names,
                                     contrast_labels=None) -> str | None:
    """Descriptive digest for a connectivity-*matrix* module that carries no
    inferential tables — e.g. ``roi_connectivity`` after its per-edge stats were
    retired (group inference moved to ``*_nbs`` / ``*_graph``). Names the metrics
    and bands the matrices span and points to the sibling modules that hold the
    inference, so the gallery entry isn't blank.

    ``figure_names`` are the module's figure filenames (``circos_*``/``heatmap_*``
    are parsed for ``<metric>``/``<band>``). Returns None if none parse (so it is
    a no-op for any module that isn't a connectivity-matrix module).
    """
    metrics: dict[str, str] = {}
    bands: set[str] = set()
    for fn in figure_names or ():
        stem = None
        for pre in ("circos_", "heatmap_"):
            if fn.startswith(pre):
                stem = fn[len(pre):].rsplit(".", 1)[0]
                break
        if stem is None:
            continue
        for band in _BAND_SUFFIXES:
            if stem.endswith("_" + band):
                metric = stem[: -(len(band) + 1)]
                if metric:
                    metrics[metric.lower()] = _pretty_metric(metric)
                    bands.add(band)
                break
    if not metrics:
        return None

    metric_list = ", ".join(sorted(metrics.values(), key=str.lower))
    n_metrics, n_bands = len(metrics), len(bands)
    n_contr = len(contrast_labels) if contrast_labels else 0

    prefix = analysis.rsplit("_", 1)[0]  # roi_connectivity -> roi
    siblings = (f"<strong>{escape(prefix)}_nbs</strong> (sub-networks) and "
                f"<strong>{escape(prefix)}_graph</strong> (graph metrics)")
    contr_txt = f" &times; {n_contr} group contrasts" if n_contr else ""
    lead = (f"Descriptive connectivity matrices — {n_metrics} "
            f"metric{'s' if n_metrics != 1 else ''} ({escape(metric_list)}) "
            f"across {n_bands} band{'s' if n_bands != 1 else ''}{contr_txt}.")
    note = f"Group-level inference for this family is reported in {siblings}."
    return ('<div class="sig-summary"><p class="sig-lead">' + lead + "</p>"
            '<p class="sig-note">' + note + "</p></div>")


def _graph_table(tables: list[dict]) -> dict | None:
    """A *global* graph-theory table: keyed by a ``graph_metric`` (global
    efficiency, modularity, …) with no populated spatial unit. Summarized by
    graph parameter, not by band, so the digest names *which* metrics differ.

    Per-ROI *nodal* graph tables (a real ``roi`` column: degree/clustering per
    node) are NOT matched — they keep the per-element aggregation.
    """
    for t in tables:
        h = t["headers"]
        if not ("graph_metric" in h and ("hypothesis" in h or "contrast" in h)
                and ("effect_size" in h or "hedges_g" in h)):
            continue
        elem = _element_column(h)
        if elem:
            recs = _records(h, t["rows"])
            if any(str(r.get(elem, "")).strip().lower() not in _DEGENERATE for r in recs):
                continue  # real per-element axis → not a graph-parameter summary
        return t
    return None


def _order_graph_bands(bands: set[str]) -> list[str]:
    known = [b for b in _GRAPH_BAND_ORDER if b in bands]
    return known + sorted(b for b in bands if b not in _GRAPH_BAND_ORDER)


def _cluster_table(tables: list[dict]):
    """Pick a vertex cluster-permutation table and the (p, direction) columns to
    read. The inferential unit for these modules is the *cluster* (with a
    corrected p), not the per-vertex row — so the digest must read one of these,
    never the truncated per-vertex ``*_stats.csv``.

    Two shapes, in preference order:
      A. ``cluster_results.csv`` — per-contrast difference clusters
         (contrast/band/metric/n_vertices/peak_t/p_corrected); this is what the
         cluster figures draw.
      B. the map-adapter ``*_hypotheses.csv`` — cluster rows carrying
         ``cluster_id``/``n_vertices``/``cluster_p``/``significant`` (used by the
         connectivity/directed/cross-freq/specparam vertex modules).
    Returns (table, p_col, direction_col) or (None, None, None).
    """
    for t in tables:
        h = t["headers"]
        if "p_corrected" in h and "n_vertices" in h and ("contrast" in h or "hypothesis" in h):
            return t, "p_corrected", ("peak_t" if "peak_t" in h else "cluster_stat")
    for t in tables:
        h = t["headers"]
        if (t["filename"].endswith("_hypotheses.csv") and "cluster_id" in h
                and "n_vertices" in h and "cluster_p" in h):
            return t, "cluster_p", ("peak_stat" if "peak_stat" in h else "mass")
    return None, None, None


def _cluster_measure_label(rec: dict) -> str:
    """Readable measure for a cluster row: band plus its dependent variable, e.g.
    'Low Gamma relative', 'spectral_slope', 'exponent'. Collapses the redundant
    case where the band *is* the measure (spectral_slope / peak_alpha maps)."""
    band = str(rec.get("band") or "").strip()
    meas = ""
    for col in ("metric", "dv", "parameter", "measure"):
        v = rec.get(col)
        if v not in (None, "") and str(v).strip().lower() not in _DEGENERATE:
            meas = str(v).strip()
            break
    if not band:
        return _pretty_metric(meas) or "map"
    if not meas or meas == band or meas.lower() in {"spectral_slope", "peak_alpha"}:
        return band
    return f"{band} {_pretty_metric(meas)}"


_DEGENERATE = {"", "na", "nan", "none"}


def _category_column(headers: list[str], records: list[dict]) -> str | None:
    """Per-contrast category axis: ``band``/``freq_pair`` for spectral tables,
    ``dv`` (exponent/offset) for aperiodic, ``parameter`` for specparam. Skips a
    column that is entirely NA (aperiodic carries a placeholder ``band = NA``)."""
    for col in ("band", "freq_pair", "dv", "parameter"):
        if col in headers:
            if any(
                v is not None and str(v).strip().lower() not in _DEGENERATE
                for v in (r.get(col) for r in records)
            ):
                return col
    for col in ("band", "freq_pair", "dv", "parameter"):
        if col in headers:
            return col
    return None


def _sig_note(headers: list[str], signed: bool) -> str:
    """Significance-threshold wording for the lead, matched to the table's stat."""
    if "q_value" in headers or "group_q" in headers:
        return "FDR q &lt; 0.05"
    if "p_corrected" in headers:
        return "p_corrected &lt; 0.05"
    if not signed:  # decoding metrics use a permutation test against chance
        return "perm p &lt; 0.05"
    if "p_fdr" in headers:
        return "FDR p &lt; 0.05"
    # Default preserves the original wording for the existing g-digest modules.
    return "FDR q &lt; 0.05"


def _group_pair(rows) -> str:
    """Name the A-vs-B pairing for a contrast so the ▲/▼ arrows are unambiguous:
    ▲ = the first-listed group (group_a) is higher. Groups come straight from the
    stat rows (native group_a/group_b columns)."""
    if not rows:
        return ""
    ga = rows[0].get("group_a")
    gb = rows[0].get("group_b")
    if not ga or not gb or str(ga).strip() in _DEGENERATE or str(gb).strip() in _DEGENERATE:
        return ""
    return f' <span class="sig-groups">{escape(str(ga))} vs {escape(str(gb))}</span>'


def build_significance_summary(tables: list[dict], contrast_labels: dict | None = None,
                               contrast_groups: dict | None = None,
                               region_pair_table: dict | None = None) -> str | None:
    """Return concise HTML summarizing significant effects by contrast, or None.

    ``tables`` are embedded table dicts: ``{filename, headers, rows}``.
    ``contrast_labels`` maps raw contrast names to readable labels for display.
    ``contrast_groups`` maps contrast names to a tier/group label; when given, the
    digest is organized into sections in the group's first-seen (YAML) order.
    """
    labels = contrast_labels or {}
    groups = contrast_groups or {}

    def _label(name):
        return labels.get(name, name)

    # Vertex cluster-permutation modules: the inferential unit is the cluster
    # (corrected p), so summarize the cluster table directly — otherwise the
    # digest would fall through to the truncated per-vertex table and miss most
    # significant clusters (and every contrast past the first).
    ctable, c_pcol, c_dcol = _cluster_table(tables)
    if ctable is not None:
        return _build_cluster_summary(ctable, c_pcol, c_dcol, _label, groups)

    # Graph-theory modules: summarize by graph parameter (which metrics differ),
    # not by the generic band axis — and don't let the empty ``spatial`` column
    # fool the per-element aggregation into a meaningless "1 ROI" count.
    gtable = _graph_table(tables)
    if gtable is not None:
        return _build_graph_summary(gtable, _label, groups)

    # Parcellated spectral modules (roi_psd/aperiodic, electrode_psd/aperiodic):
    # name the significant ROIs/channels from the per-unit posthoc table, rather
    # than the region-averaged global table that hides which units differ.
    # Source-vs-sensor comparison (electrode_comparison): concordance + which
    # measures are significant at each level.
    cmptable = _comparison_table(tables)
    if cmptable is not None:
        return _build_comparison_summary(cmptable, _label, groups)

    fcdtable = _fcd_comparison_table(tables)
    if fcdtable is not None:
        return _build_fcd_comparison_summary(fcdtable, _label, groups)

    rtable = _roi_posthoc_table(tables)
    if rtable is not None:
        return _build_roi_posthoc_summary(rtable, tables, _label, groups)

    table = _summary_table(tables)
    if table is None:
        # No effect-size table — fall back to an NBS sub-network digest if present.
        nbs = _nbs_table(tables)
        if nbs is not None:
            return _build_nbs_summary(nbs, _label, groups)
        return None

    headers = table["headers"]
    records = _to_native(_records(headers, table["rows"]))
    cat = _category_column(headers, records)
    effect_col, effect_fmt, signed = _effect_column(headers)
    elem_col = _element_column(headers)
    facet_col, _ = _facet_column(headers, records)
    if facet_col == cat:  # don't repeat the category as its own facet (aperiodic dv)
        facet_col = None
    if elem_col:  # per-element tables aggregate over the facet too
        facet_col = None

    all_contrasts = _unique(records, "hypothesis")
    sig_by_contrast: dict[str, list[dict]] = {}
    for rec in records:
        if _is_sig(rec) and _to_float(rec.get(effect_col)) is not None:
            sig_by_contrast.setdefault(rec.get("hypothesis"), []).append(rec)

    if not sig_by_contrast:
        return (
            '<div class="sig-summary"><p class="sig-lead">'
            "No significant group contrasts (" + _sig_note(headers, signed) + ")."
            "</p></div>"
        )

    # Protected post-hoc: for connectivity (a region-pair table is present), count
    # region pairs at uncorrected p<0.05 per (contrast, band, metric) — these are
    # the localized findings the circos show within an FDR-significant omnibus.
    rp_source = region_pair_table
    if rp_source is None:
        rp_source = next((t for t in tables
                          if "region_pair" in t["headers"] and "p_value" in t["headers"]), None)
    rp_counts: dict[tuple, int] = {}
    has_region_pairs = rp_source is not None and elem_col is None
    if has_region_pairs:
        for r in _to_native(_records(rp_source["headers"], rp_source["rows"])):
            p = _to_float(r.get("p_value"))
            if p is not None and p < 0.05:
                key = (r.get("hypothesis"), r.get("band"), r.get("metric"))
                rp_counts[key] = rp_counts.get(key, 0) + 1

    # Build one list item per significant contrast (keyed for later grouping).
    item_by_contrast: dict[str, str] = {}
    n_findings = 0
    for contrast in all_contrasts:
        rows = sig_by_contrast.get(contrast)
        if not rows:
            continue
        if elem_col:
            chips, added = _aggregated_chips(rows, cat, effect_col, effect_fmt, signed, elem_col)
        else:
            chips, added = _per_record_chips(
                rows, cat, effect_col, effect_fmt, signed, facet_col,
                rp_counts if has_region_pairs else None)
        n_findings += added
        item_by_contrast[contrast] = (
            f'<li><span class="sig-contrast">{escape(str(_label(contrast)))}</span>'
            + _group_pair(rows)
            + " " + "".join(chips)
            + "</li>"
        )

    _fill_nulls(all_contrasts, item_by_contrast, _label,
                "decoding not above chance" if not signed else "No significant effects")
    body = _render_body(all_contrasts, item_by_contrast, groups)

    html = '<div class="sig-summary">'
    html += (
        f'<p class="sig-lead">{n_findings} significant effect{"s" if n_findings != 1 else ""} '
        f"across {len(sig_by_contrast)} of {len(all_contrasts)} comparisons "
        f"({_sig_note(headers, signed)})."
        + (' <span class="sig-key">&#9650;/&#9660; = the first-listed group of each '
           'pair is higher/lower</span>.'
           if signed else " <span class=\"sig-key\">decoding above chance</span>.")
        + "</p>"
    )
    if has_region_pairs:
        html += (
            '<p class="sig-note">Region-pair counts are protected post-hocs '
            "(uncorrected p &lt; 0.05) within each FDR-significant omnibus; "
            "<em>diffuse</em> = no suprathreshold region pair. Each non-diffuse "
            "effect has a circos in the Figures tab.</p>"
        )
    html += body
    html += "</div>"
    return html


def _per_record_chips(rows, cat, effect_col, effect_fmt, signed, facet_col, rp_counts):
    """One chip per significant record (aggregated tables: vertex_graph, psd, …)."""
    chips = []
    n = 0
    for rec in sorted(rows, key=lambda r: -abs(_to_float(r.get(effect_col)) or 0.0)):
        v = _to_float(rec.get(effect_col))
        arrow = ""
        if signed:
            arrow = (f'<span class="arrow up">&#9650;</span> ' if v > 0
                     else '<span class="arrow down">&#9660;</span> ')
        band = f"<strong>{escape(str(rec.get(cat, '')))}</strong>"
        facet = ""
        if facet_col and rec.get(facet_col):
            facet = ' <span class="sig-facet">' + escape(_pretty_metric(rec[facet_col])) + "</span>"
        pairs = ""
        if rp_counts is not None:  # connectivity: annotate with gated region-pair detail
            k = (rec.get("hypothesis"), rec.get(cat), rec.get(facet_col) if facet_col else None)
            cnt = rp_counts.get(k, 0)
            pairs = (' <span class="sig-pairs">' + f"{cnt} region pair{'s' if cnt != 1 else ''}" + "</span>"
                     if cnt else ' <span class="sig-pairs diffuse">diffuse</span>')
        chips.append(
            f'<span class="sig-item">{arrow}{band}{facet} '
            f'<span class="g">{effect_fmt(v)}</span>{pairs}</span>'
        )
        n += 1
    return chips, n


def _aggregated_chips(rows, cat, effect_col, effect_fmt, signed, elem_col):
    """One chip per (category) for per-element tables (roi_graph, specparam, …):
    collapse the elements to a count + the strongest effect, so a per-vertex/ROI
    table renders a handful of chips instead of thousands."""
    by_cat: dict[str, list[dict]] = {}
    for rec in rows:
        by_cat.setdefault(str(rec.get(cat, "")), []).append(rec)
    unit_s, unit_p = ("vertex", "vertices") if elem_col == "vertex_idx" else ("ROI", "ROIs")

    # Order categories by their strongest |effect|.
    def _peak(recs):
        return max((abs(_to_float(r.get(effect_col)) or 0.0) for r in recs), default=0.0)

    chips = []
    for cat_val, recs in sorted(by_cat.items(), key=lambda kv: -_peak(kv[1])):
        best = max(recs, key=lambda r: abs(_to_float(r.get(effect_col)) or 0.0))
        v = _to_float(best.get(effect_col)) or 0.0
        arrow = ""
        if signed:
            arrow = (f'<span class="arrow up">&#9650;</span> ' if v > 0
                     else '<span class="arrow down">&#9660;</span> ')
        n_el = len({r.get(elem_col) for r in recs})
        chips.append(
            f'<span class="sig-item">{arrow}<strong>{escape(_pretty_metric(cat_val))}</strong> '
            f'<span class="g">{effect_fmt(v)}</span> '
            f'<span class="sig-pairs">{n_el} {unit_s if n_el == 1 else unit_p}</span></span>'
        )
    return chips, len(chips)


def _build_cluster_summary(table: dict, p_col: str, dir_col: str,
                           _label, groups: dict) -> str | None:
    """Digest a vertex cluster-permutation table: significant clusters per
    contrast (cluster-corrected p < 0.05), each with its band/measure, spatial
    extent (n vertices), direction (sign of the peak statistic), and p."""
    records = _to_native(_records(table["headers"], table["rows"]))
    has_flag = "significant" in table["headers"]
    all_contrasts: list[str] = []
    sig_by_contrast: dict[str, list[dict]] = {}
    for rec in records:
        contrast = rec.get("hypothesis") or rec.get("contrast")
        if not contrast:
            continue
        if contrast not in all_contrasts:
            all_contrasts.append(contrast)
        p = _to_float(rec.get(p_col))
        # cluster_results has no `significant` column → gate on the corrected p;
        # the map hypotheses table carries the adapter's own significance flag
        # (which also encodes equivalence for TOST rows).
        is_sig = _is_sig(rec) if has_flag else (p is not None and p < 0.05)
        if is_sig:
            sig_by_contrast.setdefault(contrast, []).append(rec)

    if not all_contrasts:
        return None
    if not sig_by_contrast:
        return ('<div class="sig-summary"><p class="sig-lead">'
                "No significant clusters (cluster-corrected p &lt; 0.05)."
                "</p></div>")

    # Sensor-montage modules (electrode_connectivity) reuse the vertex cluster
    # schema (``n_vertices``/``peak_vertex``), but the inferential unit is a
    # channel, not a source vertex — name it accordingly.
    fn = table["filename"].lower()
    unit_s, unit_p = (("channel", "channels")
                      if ("electrode" in fn or "channel" in fn)
                      else ("vertex", "vertices"))

    item_by_contrast: dict[str, str] = {}
    n_findings = 0
    for contrast in all_contrasts:
        recs = sig_by_contrast.get(contrast)
        if not recs:
            continue
        chips = []
        for rec in sorted(recs, key=lambda r: (_to_float(r.get(p_col)) if _to_float(r.get(p_col)) is not None else 1.0)):
            d = _to_float(rec.get(dir_col))
            arrow = ""
            if d is not None:
                arrow = ('<span class="arrow up">&#9650;</span> ' if d > 0
                         else '<span class="arrow down">&#9660;</span> ')
            n_vtx = _to_float(rec.get("n_vertices"))
            extent = (f'<span class="sig-pairs">{int(n_vtx)} '
                      f'{unit_s if n_vtx == 1 else unit_p}</span>') if n_vtx is not None else ""
            p = _to_float(rec.get(p_col))
            pstr = f" <span class=\"g\">p={p:.3f}</span>" if p is not None else ""
            region = rec.get("region")
            region_html = (f'<span class="sig-region">{escape(str(region))}</span>'
                           if region not in (None, "") else "")
            cls = "sig-item has-region" if region_html else "sig-item"
            chips.append(
                f'<span class="{cls}">{arrow}<strong>{escape(_cluster_measure_label(rec))}</strong> '
                f'{extent}{pstr}{region_html}</span>'
            )
            n_findings += 1
        # Region-bearing findings render one-per-row (block), so drop the space
        # separators that would otherwise leave stray gaps between block rows.
        joiner = "" if any("has-region" in c for c in chips) else " "
        item_by_contrast[contrast] = (
            f'<li><span class="sig-contrast">{escape(str(_label(contrast)))}</span> '
            + joiner.join(chips) + "</li>"
        )

    _fill_nulls(all_contrasts, item_by_contrast, _label, "No significant clusters")
    body = _render_body(all_contrasts, item_by_contrast, groups)
    html = '<div class="sig-summary">'
    html += (
        f'<p class="sig-lead">{n_findings} significant cluster'
        f'{"s" if n_findings != 1 else ""} across {len(sig_by_contrast)} of '
        f"{len(all_contrasts)} comparisons (cluster-corrected p &lt; 0.05)."
        ' <span class="sig-key">&#9650;/&#9660; = the first-listed group of each '
        'pair is higher/lower</span>.</p>'
    )
    html += body
    html += "</div>"
    return html


def _arrow(v) -> str:
    return ('<span class="arrow up">&#9650;</span>' if (v or 0) > 0
            else '<span class="arrow down">&#9660;</span>')


def _build_roi_posthoc_summary(table: dict, tables: list[dict], _label, groups: dict) -> str | None:
    """Digest parcellated spectral results at BOTH levels, per contrast × measure
    (band + dv): the whole-brain (region-averaged) effect AND the per-ROI/channel
    breakdown that names which units differ. Either level may be significant on
    its own (e.g. a global aperiodic effect with no surviving per-ROI unit)."""
    records = _to_native(_records(table["headers"], table["rows"]))
    elem = _element_column(table["headers"])
    fn = table["filename"].lower()
    unit_word = "channel" if ("electrode" in fn or "channel" in fn) else "ROI"
    all_contrasts = _unique(records, "hypothesis")

    # Significant per-unit rows, keyed (contrast, measure).
    roi_by: dict[tuple, list[dict]] = {}
    for r in records:
        if _is_sig(r) and _to_float(r.get("effect_size")) is not None and r.get(elem):
            roi_by.setdefault((r.get("hypothesis"), _roi_measure_label(r)), []).append(r)

    # Significant whole-brain (region-averaged) effects, keyed (contrast, measure).
    gtbl = next((t for t in tables if "posthoc_global" in t["filename"].lower()), None)
    global_by: dict[tuple, dict] = {}
    if gtbl is not None:
        for r in _to_native(_records(gtbl["headers"], gtbl["rows"])):
            if _is_sig(r) and _to_float(r.get("effect_size")) is not None:
                global_by[(r.get("hypothesis"), _roi_measure_label(r))] = r
    # A contrast may be significant only at the whole-brain level.
    for c, _mzr in global_by:
        if c not in all_contrasts:
            all_contrasts.append(c)

    if not all_contrasts:
        return None
    if not roi_by and not global_by:
        return ('<div class="sig-summary"><p class="sig-lead">'
                f"No significant spectral effects (FDR q &lt; 0.05).</p></div>")

    NAME_CAP = 8
    item_by_contrast: dict[str, str] = {}
    n_findings = 0
    sig_contrasts: set = set()
    for contrast in all_contrasts:
        # Collect measures from either level for this contrast.
        meas: dict[str, dict] = {}
        for (c, mzr), rows in roi_by.items():
            if c == contrast:
                meas.setdefault(mzr, {"rois": [], "global": None})["rois"] = rows
        for (c, mzr), grow in global_by.items():
            if c == contrast:
                meas.setdefault(mzr, {"rois": [], "global": None})["global"] = grow
        if not meas:
            continue
        sig_contrasts.add(contrast)

        def _peak(m):
            vals = [abs(_to_float(r.get("effect_size")) or 0.0) for r in m["rois"]]
            if m["global"] is not None:
                vals.append(abs(_to_float(m["global"].get("effect_size")) or 0.0))
            return max(vals, default=0.0)

        chips = []
        for measure, m in sorted(meas.items(), key=lambda kv: -_peak(kv[1])):
            global_html = ""
            if m["global"] is not None:
                gv = _to_float(m["global"].get("effect_size")) or 0.0
                global_html = (f' <span class="sig-facet">whole-brain</span> {_arrow(gv)}'
                               f'<span class="g">g={abs(gv):.2f}</span>')
                n_findings += 1
            rs = sorted(m["rois"], key=lambda x: -abs(_to_float(x.get("effect_size")) or 0.0))
            count_html = region_html = ""
            if rs:
                named = []
                for r in rs[:NAME_CAP]:
                    v = _to_float(r.get("effect_size")) or 0.0
                    named.append(f'{_arrow(v)}&nbsp;{escape(str(r.get(elem)))} '
                                 f'<span class="g">g={abs(v):.2f}</span>')
                more = len(rs) - len(named)
                tail = f" (+{more} more)" if more > 0 else ""
                count_html = (f' <span class="sig-pairs">{len(rs)} {unit_word}'
                              f'{"s" if len(rs) != 1 else ""}</span>')
                region_html = f'<span class="sig-region">{", ".join(named)}{tail}</span>'
                n_findings += len(rs)
            # Every measure is its own block row — so a whole-brain-only contrast
            # (rescue/exploratory, no surviving per-ROI unit) lines up the same as
            # a per-ROI one instead of cramming onto a single line.
            chips.append(
                f'<span class="sig-item has-region"><strong>{escape(measure)}</strong>'
                f'{global_html}{count_html}{region_html}</span>')
        item_by_contrast[contrast] = (
            f'<li><span class="sig-contrast">{escape(str(_label(contrast)))}</span> '
            + "".join(chips) + "</li>")

    _fill_nulls(all_contrasts, item_by_contrast, _label, "No significant effects")
    body = _render_body(all_contrasts, item_by_contrast, groups)
    html = '<div class="sig-summary">'
    html += (
        f'<p class="sig-lead">{n_findings} significant {unit_word}-level effect'
        f'{"s" if n_findings != 1 else ""} across {len(sig_contrasts)} of '
        f"{len(all_contrasts)} comparisons (FDR q &lt; 0.05)."
        ' <span class="sig-key">whole-brain effect + the '
        f'{unit_word}s that differ; &#9650;/&#9660; = the first-listed group is '
        'higher/lower</span>.</p>'
    )
    html += body
    html += "</div>"
    return html


def _build_graph_summary(table: dict, _label, groups: dict) -> str | None:
    """Digest a graph-theory table by graph parameter: for each contrast, which
    graph metrics differ (global efficiency, modularity, …), in which bands and
    connectivity metrics, with the peak effect and direction. Answers 'which
    graph parameters are significant', not just which bands."""
    records = _to_native(_records(table["headers"], table["rows"]))
    all_contrasts = _unique(records, "hypothesis")
    sig_by_contrast: dict[str, list[dict]] = {}
    for r in records:
        if _is_sig(r):
            sig_by_contrast.setdefault(r.get("hypothesis"), []).append(r)

    if not all_contrasts:
        return None
    if not any(sig_by_contrast.values()):
        return ('<div class="sig-summary"><p class="sig-lead">'
                "No significant graph metrics (FDR q &lt; 0.05).</p></div>")

    def _peak(rs):
        return max((abs(_to_float(x.get("effect_size")) or 0.0) for x in rs), default=0.0)

    item_by_contrast: dict[str, str] = {}
    n_findings = 0
    for contrast in all_contrasts:
        rows = sig_by_contrast.get(contrast)
        if not rows:
            continue
        by_gm: dict[str, list[dict]] = {}
        for r in rows:
            by_gm.setdefault(r.get("graph_metric") or "", []).append(r)
        chips = []
        for gm, rs in sorted(by_gm.items(), key=lambda kv: -_peak(kv[1])):
            best = max(rs, key=lambda x: abs(_to_float(x.get("effect_size")) or 0.0))
            v = _to_float(best.get("effect_size")) or 0.0
            signed = str(best.get("effect_size_type", "")).lower() == "hedges_g"
            arrow = ""
            if signed:
                arrow = ('<span class="arrow up">&#9650;</span> ' if v > 0
                         else '<span class="arrow down">&#9660;</span> ')
            bands = _order_graph_bands({str(x.get("band")) for x in rs if x.get("band")})
            conns = sorted({_pretty_metric(x.get("conn_metric")) for x in rs if x.get("conn_metric")})
            label = _GRAPH_METRIC_LABEL.get(gm, str(gm).replace("_", " "))
            estr = f"g&le;{abs(v):.2f}" if signed else f"&omega;&sup2;&le;{abs(v):.2f}"
            band_html = (f' <span class="sig-facet">{escape(", ".join(bands))}</span>'
                         if bands else "")
            conn_html = (f' <span class="sig-pairs">{escape(", ".join(conns))}</span>'
                         if conns else "")
            chips.append(
                f'<span class="sig-item">{arrow}<strong>{escape(label)}</strong>'
                f'{band_html}{conn_html} <span class="g">{estr}</span></span>')
            n_findings += 1
        item_by_contrast[contrast] = (
            f'<li><span class="sig-contrast">{escape(str(_label(contrast)))}</span> '
            + "".join(chips) + "</li>")

    n_sig_contrasts = sum(1 for c in sig_by_contrast if sig_by_contrast[c])
    _fill_nulls(all_contrasts, item_by_contrast, _label, "No significant graph metrics")
    body = _render_body(all_contrasts, item_by_contrast, groups)
    html = '<div class="sig-summary">'
    html += (
        f'<p class="sig-lead">{n_findings} significant graph-metric finding'
        f'{"s" if n_findings != 1 else ""} across {n_sig_contrasts} of '
        f"{len(all_contrasts)} comparisons (FDR q &lt; 0.05)."
        ' <span class="sig-key">grouped by graph parameter; bands and connectivity '
        'metric listed; &#9650;/&#9660; = the first-listed group is higher/lower</span>.</p>'
    )
    html += body
    html += "</div>"
    return html


def _build_nbs_summary(table: dict, _label, groups: dict) -> str | None:
    """Digest an NBS component table: significant sub-networks per (contrast, band,
    metric), parsed from the ``key`` column (``<contrast>_<band>[_<metric>]``)."""
    records = _records(table["headers"], table["rows"])
    sig_by_contrast: dict[str, list[tuple]] = {}
    all_contrasts: list[str] = []
    for rec in records:
        contrast, band, metric = _parse_nbs_key(str(rec.get("key", "")))
        if contrast is None:
            continue
        if contrast not in all_contrasts:
            all_contrasts.append(contrast)
        p = _to_float(rec.get("p_corrected"))
        n_edges = _to_float(rec.get("n_edges"))
        if p is not None and p < 0.05:
            sig_by_contrast.setdefault(contrast, []).append(
                (band, metric, n_edges, p, rec.get("region"), rec.get("direction"),
                 _to_float(rec.get("n_edges_increase")),
                 _to_float(rec.get("n_edges_decrease"))))

    if not all_contrasts:
        return None
    if not sig_by_contrast:
        return ('<div class="sig-summary"><p class="sig-lead">'
                "No significant sub-networks (NBS p_corrected &lt; 0.05)."
                "</p></div>")

    item_by_contrast: dict[str, str] = {}
    n_findings = 0
    for contrast in all_contrasts:
        comps = sig_by_contrast.get(contrast)
        if not comps:
            continue
        chips = []
        for band, metric, n_edges, p, region, direction, n_inc, n_dec in sorted(
                comps, key=lambda c: (c[3])):
            facet = (f' <span class="sig-facet">{escape(_pretty_metric(metric))}</span>'
                     if metric else "")
            edges = f"{int(n_edges)}-edge " if n_edges is not None else ""
            # Direction: NBS thresholds |t|, so a sub-network can be up-, down-, or
            # mixed-regulation. ▲ = group A > B, ▼ = group A < B.
            dstr = str(direction or "").strip().lower()
            if dstr == "increase":
                arrow = '<span class="arrow up">&#9650;</span> '
            elif dstr == "decrease":
                arrow = '<span class="arrow down">&#9660;</span> '
            elif dstr == "mixed" and n_inc is not None and n_dec is not None:
                arrow = (f'<span class="sig-mixed">&#9650;{int(n_inc)}/'
                         f'&#9660;{int(n_dec)}</span> ')
            else:
                arrow = ""
            region_html = (f'<span class="sig-region">{escape(str(region))}</span>'
                           if region not in (None, "") else "")
            cls = "sig-item has-region" if region_html else "sig-item"
            band_html = f"<strong>{escape(band)}</strong>" if band else ""
            chips.append(
                f'<span class="{cls}">{arrow}{band_html}{facet} '
                f'<span class="sig-pairs">{edges}sub-network (p={p:.3f})</span>{region_html}</span>'
            )
            n_findings += 1
        joiner = "" if any("has-region" in c for c in chips) else " "
        item_by_contrast[contrast] = (
            f'<li><span class="sig-contrast">{escape(str(_label(contrast)))}</span> '
            + joiner.join(chips) + "</li>"
        )

    _fill_nulls(all_contrasts, item_by_contrast, _label, "No significant sub-networks")
    body = _render_body(all_contrasts, item_by_contrast, groups)
    html = '<div class="sig-summary">'
    html += (
        f'<p class="sig-lead">{n_findings} significant sub-network'
        f'{"s" if n_findings != 1 else ""} across {len(sig_by_contrast)} of '
        f"{len(all_contrasts)} comparisons (NBS p_corrected &lt; 0.05).</p>"
    )
    html += body
    html += "</div>"
    return html


def _null_item(label, note: str) -> str:
    """A list item for a comparison that was run but had no significant result —
    shown in place, so it's clear the test was done."""
    return (f'<li class="sig-null-item"><span class="sig-contrast">{escape(str(label))}</span> '
            f'<span class="sig-none-inline">{note}</span></li>')


def _fill_nulls(all_contrasts, item_by_contrast, _label, note: str) -> None:
    """Add an in-place 'no significant …' item for every contrast without one."""
    for c in all_contrasts:
        if c not in item_by_contrast:
            item_by_contrast[c] = _null_item(_label(c), note)


def _render_body(all_contrasts, item_by_contrast, groups: dict) -> str:
    """Shared body renderer: tier sections (YAML order) when groups given, else flat."""
    def _ul(contrasts):
        return '<ul class="sig-list">' + "".join(item_by_contrast[c] for c in contrasts) + "</ul>"

    if not groups:
        return _ul([c for c in all_contrasts if c in item_by_contrast])

    group_order = []
    for g in groups.values():
        if g and g not in group_order:
            group_order.append(g)
    body = ""
    rendered = set()
    for grp in group_order:
        members = [c for c in all_contrasts if c in item_by_contrast and groups.get(c) == grp]
        if not members:
            continue
        body += '<h4 class="sig-group">' + escape(grp) + "</h4>" + _ul(members)
        rendered.update(members)
    leftover = [c for c in all_contrasts if c in item_by_contrast and c not in rendered]
    if leftover:
        body += '<h4 class="sig-group">Other</h4>' + _ul(leftover)
    return body
