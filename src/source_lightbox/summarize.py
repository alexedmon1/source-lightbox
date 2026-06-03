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


def build_significance_summary(tables: list[dict], contrast_labels: dict | None = None) -> str | None:
    """Return concise HTML summarizing significant effects by contrast, or None.

    ``tables`` are embedded table dicts: ``{filename, headers, rows}``.
    ``contrast_labels`` maps raw contrast names to readable labels for display.
    """
    labels = contrast_labels or {}

    def _label(name):
        return labels.get(name, name)

    table = _summary_table(tables)
    if table is None:
        return None

    headers = table["headers"]
    records = _records(headers, table["rows"])
    cat = "band" if "band" in headers else "freq_pair"
    facet_col, _ = _facet_column(headers, records)

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

    items_html = []
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
            chips.append(
                f'<span class="sig-item"><span class="arrow {direction}">{arrow}</span> '
                f'{band}{facet} <span class="g">g={abs(g):.2f}</span></span>'
            )
            n_findings += 1
        items_html.append(
            f'<li><span class="sig-contrast">{escape(str(_label(contrast)))}</span> '
            + "".join(chips)
            + "</li>"
        )

    null_contrasts = [c for c in all_contrasts if c not in sig_by_contrast]

    html = '<div class="sig-summary">'
    html += (
        f'<p class="sig-lead">{n_findings} significant contrast'
        f"&times;band effect{'s' if n_findings != 1 else ''} across "
        f"{len(sig_by_contrast)} of {len(all_contrasts)} comparisons "
        "(FDR q &lt; 0.05). <span class=\"sig-key\">&#9650; first group higher, "
        "&#9660; lower</span>.</p>"
    )
    html += '<ul class="sig-list">' + "".join(items_html) + "</ul>"
    if null_contrasts:
        html += (
            '<p class="sig-none">No significant effects: '
            + ", ".join(escape(_label(c)) for c in null_contrasts)
            + ".</p>"
        )
    html += "</div>"
    return html
