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
        return meas or "map"
    if not meas or meas == band or meas.lower() in {"spectral_slope", "peak_alpha"}:
        return band
    return f"{band} {meas}"


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

    body = _render_body(all_contrasts, item_by_contrast, groups)
    null_contrasts = [c for c in all_contrasts if c not in sig_by_contrast]

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
    if null_contrasts:
        html += (
            '<p class="sig-none">No significant effects: '
            + ", ".join(escape(_label(c)) for c in null_contrasts)
            + ".</p>"
        )
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
        band = escape(str(rec.get(cat, "")))
        facet = ""
        if facet_col and rec.get(facet_col):
            facet = ' <span class="sig-facet">' + escape(str(rec[facet_col])) + "</span>"
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
            f'<span class="sig-item">{arrow}{escape(cat_val)} '
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
                      f'{"vertex" if n_vtx == 1 else "vertices"}</span>') if n_vtx is not None else ""
            p = _to_float(rec.get(p_col))
            pstr = f" <span class=\"g\">p={p:.3f}</span>" if p is not None else ""
            region = rec.get("region")
            region_html = (f' <span class="sig-region">{escape(str(region))}</span>'
                           if region not in (None, "") else "")
            chips.append(
                f'<span class="sig-item">{arrow}{escape(_cluster_measure_label(rec))} '
                f'{extent}{pstr}{region_html}</span>'
            )
            n_findings += 1
        item_by_contrast[contrast] = (
            f'<li><span class="sig-contrast">{escape(str(_label(contrast)))}</span> '
            + "".join(chips) + "</li>"
        )

    body = _render_body(all_contrasts, item_by_contrast, groups)
    null_contrasts = [c for c in all_contrasts if c not in sig_by_contrast]
    html = '<div class="sig-summary">'
    html += (
        f'<p class="sig-lead">{n_findings} significant cluster'
        f'{"s" if n_findings != 1 else ""} across {len(sig_by_contrast)} of '
        f"{len(all_contrasts)} comparisons (cluster-corrected p &lt; 0.05)."
        ' <span class="sig-key">&#9650;/&#9660; = the first-listed group of each '
        'pair is higher/lower</span>.</p>'
    )
    html += body
    if null_contrasts:
        html += ('<p class="sig-none">No significant clusters: '
                 + ", ".join(escape(_label(c)) for c in null_contrasts) + ".</p>")
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
                (band, metric, n_edges, p, rec.get("region")))

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
        for band, metric, n_edges, p, region in sorted(comps, key=lambda c: (c[3])):
            facet = f' <span class="sig-facet">{escape(metric)}</span>' if metric else ""
            edges = f"{int(n_edges)}-edge " if n_edges is not None else ""
            region_html = (f' <span class="sig-region">{escape(str(region))}</span>'
                           if region not in (None, "") else "")
            chips.append(
                f'<span class="sig-item">{escape(band or "")}{facet} '
                f'<span class="sig-pairs">{edges}sub-network (p={p:.3f})</span>{region_html}</span>'
            )
            n_findings += 1
        item_by_contrast[contrast] = (
            f'<li><span class="sig-contrast">{escape(str(_label(contrast)))}</span> '
            + "".join(chips) + "</li>"
        )

    body = _render_body(all_contrasts, item_by_contrast, groups)
    null_contrasts = [c for c in all_contrasts if c not in sig_by_contrast]
    html = '<div class="sig-summary">'
    html += (
        f'<p class="sig-lead">{n_findings} significant sub-network'
        f'{"s" if n_findings != 1 else ""} across {len(sig_by_contrast)} of '
        f"{len(all_contrasts)} comparisons (NBS p_corrected &lt; 0.05).</p>"
    )
    html += body
    if null_contrasts:
        html += ('<p class="sig-none">No significant sub-networks: '
                 + ", ".join(escape(_label(c)) for c in null_contrasts) + ".</p>")
    html += "</div>"
    return html


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
