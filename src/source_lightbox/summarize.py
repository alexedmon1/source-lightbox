"""Generate a concise 'significant results by contrast' summary from stat tables.

The verbose ``ANALYSIS_SUMMARY.md`` that source-analytics writes is a full report,
not a summary. Instead of embedding it verbatim, we derive a short, scannable
digest directly from a module's effect-size table: which contrasts show
significant effects, in which bands, and in which direction.

Column-driven and reusable: any module with a ``contrast`` × ``band``/``freq_pair``
× ``hedges_g`` table (with a significance flag or q/p column) gets a digest.
"""

from __future__ import annotations

from html import escape

from .render import (
    _facet_column,
    _is_sig,
    _records,
    _table_priority,
    _to_float,
    _unique,
)


def _summary_table(tables: list[dict]) -> dict | None:
    """Pick the highest-priority effect-size table suitable for a digest."""
    candidates = [
        t for t in tables
        if "contrast" in t["headers"]
        and ("band" in t["headers"] or "freq_pair" in t["headers"])
        and "hedges_g" in t["headers"]
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda t: _table_priority(t["filename"]))


_DEGENERATE = {"", "na", "nan", "none"}


def _category_column(headers: list[str], records: list[dict]) -> str | None:
    """Per-contrast category axis: ``band``/``freq_pair`` for spectral tables,
    ``dv`` (exponent/offset) for aperiodic. Skips a column that is entirely NA
    (aperiodic carries a placeholder ``band = NA``)."""
    for col in ("band", "freq_pair", "dv"):
        if col in headers:
            if any(
                v is not None and str(v).strip().lower() not in _DEGENERATE
                for v in (r.get(col) for r in records)
            ):
                return col
    for col in ("band", "freq_pair", "dv"):
        if col in headers:
            return col
    return None


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

    table = _summary_table(tables)
    if table is None:
        return None

    headers = table["headers"]
    records = _records(headers, table["rows"])
    cat = _category_column(headers, records)
    facet_col, _ = _facet_column(headers, records)
    if facet_col == cat:  # don't repeat the category as its own facet (aperiodic dv)
        facet_col = None

    all_contrasts = _unique(records, "contrast")
    sig_by_contrast: dict[str, list[dict]] = {}
    for rec in records:
        if _is_sig(rec) and _to_float(rec.get("hedges_g")) is not None:
            sig_by_contrast.setdefault(rec.get("contrast"), []).append(rec)

    if not sig_by_contrast:
        return (
            '<div class="sig-summary"><p class="sig-lead">'
            "No significant group contrasts (FDR q &lt; 0.05)."
            "</p></div>"
        )

    # Protected post-hoc: for connectivity (a region-pair table is present), count
    # region pairs at uncorrected p<0.05 per (contrast, band, metric) — these are
    # the localized findings the circos show within an FDR-significant omnibus. The
    # global effect (this digest's rows) provides the family-wise correction.
    # 0 pairs = a diffuse global effect with no suprathreshold pair.
    # Prefer the full region-pair table (the embedded one in `tables` may be
    # row-truncated for the gallery, which would undercount).
    rp_source = region_pair_table
    if rp_source is None:
        rp_source = next((t for t in tables
                          if "region_pair" in t["headers"] and "p_value" in t["headers"]), None)
    rp_counts: dict[tuple, int] = {}
    has_region_pairs = rp_source is not None
    if rp_source is not None:
        for r in _records(rp_source["headers"], rp_source["rows"]):
            p = _to_float(r.get("p_value"))
            if p is not None and p < 0.05:
                key = (r.get("contrast"), r.get("band"), r.get("metric"))
                rp_counts[key] = rp_counts.get(key, 0) + 1

    # Build one list item per significant contrast (keyed for later grouping).
    item_by_contrast: dict[str, str] = {}
    n_findings = 0
    for contrast in all_contrasts:
        rows = sig_by_contrast.get(contrast)
        if not rows:
            continue
        chips = []
        for rec in sorted(rows, key=lambda r: -abs(_to_float(r.get("hedges_g")) or 0.0)):
            g = _to_float(rec.get("hedges_g"))
            arrow = "&#9650;" if g > 0 else "&#9660;"  # ▲ / ▼
            direction = "up" if g > 0 else "down"
            band = escape(str(rec.get(cat, "")))
            facet = ""
            if facet_col and rec.get(facet_col):
                facet = ' <span class="sig-facet">' + escape(str(rec[facet_col])) + "</span>"
            pairs = ""
            if has_region_pairs:  # connectivity: annotate with gated region-pair detail
                n = rp_counts.get((contrast, rec.get(cat), rec.get(facet_col) if facet_col else None), 0)
                pairs = (' <span class="sig-pairs">' + f"{n} region pair{'s' if n != 1 else ''}" + "</span>"
                         if n else ' <span class="sig-pairs diffuse">diffuse</span>')
            chips.append(
                f'<span class="sig-item"><span class="arrow {direction}">{arrow}</span> '
                f'{band}{facet} <span class="g">g={abs(g):.2f}</span>{pairs}</span>'
            )
            n_findings += 1
        item_by_contrast[contrast] = (
            f'<li><span class="sig-contrast">{escape(str(_label(contrast)))}</span> '
            + "".join(chips)
            + "</li>"
        )

    def _ul(contrasts):
        return '<ul class="sig-list">' + "".join(item_by_contrast[c] for c in contrasts) + "</ul>"

    # Body: grouped into tier sections (YAML order) when groups are provided.
    body = ""
    if groups:
        group_order = []
        for g in groups.values():
            if g and g not in group_order:
                group_order.append(g)
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
    else:
        body = _ul([c for c in all_contrasts if c in item_by_contrast])

    null_contrasts = [c for c in all_contrasts if c not in sig_by_contrast]

    html = '<div class="sig-summary">'
    html += (
        f'<p class="sig-lead">{n_findings} significant effect{"s" if n_findings != 1 else ""} '
        f"across {len(sig_by_contrast)} of {len(all_contrasts)} comparisons "
        "(FDR q &lt; 0.05). <span class=\"sig-key\">&#9650; first group higher, "
        "&#9660; lower</span>.</p>"
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
