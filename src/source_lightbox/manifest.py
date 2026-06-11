"""Build the manifest.json from scan results."""

from __future__ import annotations

import csv
from pathlib import Path

from .scanner import ScanResult, _slugify, qc_csv_to_json


def _read_csv(path: Path) -> dict:
    """Read a CSV file and return {headers: [...], rows: [[...], ...]}."""
    rows = []
    headers = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if i == 0:
                headers = row
            else:
                rows.append(row)
    return {"headers": headers, "rows": rows}


def build_manifest(scan: ScanResult, title: str, max_table_rows: int = 500,
                   contrast_labels: dict | None = None,
                   contrast_groups: dict | None = None,
                   contrast_meta: dict | None = None,
                   analysis_meta: dict | None = None,
                   paradigm_display: dict | None = None) -> dict:
    """Build the manifest dictionary from aggregated scan results.

    Tables are embedded as parsed CSV data and summaries as rendered HTML,
    so the gallery works without a server (no fetch() needed).

    ``analysis_meta`` (read from source-analytics) attaches a ``meta`` block —
    ``domain`` and ``supplements`` — to each analysis so the gallery can group
    by domain and nest each secondary under the primary it supplements.

    ``contrast_meta`` (read from the study YAML) carries each contrast's
    hypothesis-testing metadata — ``role``, ``test``, ``gate_on`` — keyed by
    contrast name. Phase 0 only passes it through to the manifest; the
    rescue-map presentation (Phase 2) consumes it.
    """
    analysis_meta = analysis_meta or {}
    manifest = {
        "title": title,
        "paradigms": {},
        # Per-paradigm nav display: paradigm key -> {group, label}. Empty = flat nav.
        "paradigm_meta": paradigm_display or {},
        # Per-contrast hypothesis metadata: name -> {role, test, gate_on}.
        "contrast_meta": contrast_meta or {},
        "localization": {},
        "sources": [],
    }

    # Collect unique source labels
    source_labels = set()
    for fig in scan.figures:
        source_labels.add(fig.source_label)
    for tbl in scan.tables:
        source_labels.add(tbl.source_label)
    manifest["sources"] = sorted(source_labels)

    # Group analytics figures by paradigm > analysis > source
    for fig in scan.figures:
        if fig.category != "analytics":
            continue
        paradigm = fig.paradigm
        analysis = fig.analysis
        source = fig.source_label

        if paradigm not in manifest["paradigms"]:
            manifest["paradigms"][paradigm] = {}
        if analysis not in manifest["paradigms"][paradigm]:
            manifest["paradigms"][paradigm][analysis] = {
                "figures": {},
                "tables": {},
                "summary": None,
            }

        entry = manifest["paradigms"][paradigm][analysis]
        if source not in entry["figures"]:
            entry["figures"][source] = []
        entry["figures"][source].append(
            {
                "path": f"figures/{fig.gallery_rel_path}",
                "thumb": f"figures/{fig.thumb_rel_path}",
                "filename": fig.filename,
            }
        )

    # Group tables by paradigm > analysis > source — embed CSV data inline
    for tbl in scan.tables:
        paradigm = tbl.paradigm
        analysis = tbl.analysis
        source = tbl.source_label

        if paradigm not in manifest["paradigms"]:
            manifest["paradigms"][paradigm] = {}
        if analysis not in manifest["paradigms"][paradigm]:
            manifest["paradigms"][paradigm][analysis] = {
                "figures": {},
                "tables": {},
                "summary": None,
            }

        entry = manifest["paradigms"][paradigm][analysis]
        if source not in entry["tables"]:
            entry["tables"][source] = []

        table_data = _read_csv(tbl.src_path)
        total_rows = len(table_data["rows"])
        truncated = total_rows > max_table_rows
        tbl_entry = {
            "filename": tbl.filename,
            "headers": table_data["headers"],
            "rows": table_data["rows"][:max_table_rows] if truncated else table_data["rows"],
        }
        if truncated:
            tbl_entry["truncated"] = True
            tbl_entry["total_rows"] = total_rows
        entry["tables"][source].append(tbl_entry)

    # Summaries — a concise 'significant results by contrast' digest derived from
    # each module's effect-size table, NOT the verbose ANALYSIS_SUMMARY.md verbatim.
    from .summarize import build_significance_summary

    # Full (untruncated) region-pair tables, by module — the embedded copies may
    # be row-capped, which would undercount post-hoc region pairs in the digest.
    region_pair_full: dict[tuple, dict] = {}
    for tbl in scan.tables:
        if "region_pair" in tbl.filename:
            try:
                region_pair_full[(tbl.paradigm, tbl.analysis)] = _read_csv(tbl.src_path)
            except Exception:  # noqa: BLE001
                pass

    n_summaries = 0
    for paradigm, analyses in manifest["paradigms"].items():
        for analysis, entry in analyses.items():
            module_tables = []
            for src_tables in entry["tables"].values():
                module_tables.extend(src_tables)
            summary_html = build_significance_summary(
                module_tables, contrast_labels=contrast_labels, contrast_groups=contrast_groups,
                region_pair_table=region_pair_full.get((paradigm, analysis)))
            entry["summary"] = summary_html
            if summary_html:
                n_summaries += 1

            # Domain / supplements metadata (for domain-grouped nav + nesting).
            m = analysis_meta.get(analysis, {})
            entry["meta"] = {
                "domain": m.get("domain", "Other"),
                "supplements": m.get("supplements"),
                "description": m.get("description"),
            }

    # Localization entries grouped by source
    for fig in scan.figures:
        if fig.category != "localization":
            continue
        source = fig.source_label
        if source not in manifest["localization"]:
            manifest["localization"][source] = {"subjects": {}, "qc_figures": []}

        entry = manifest["localization"][source]
        if fig.subject:
            if fig.subject not in entry["subjects"]:
                entry["subjects"][fig.subject] = []
            entry["subjects"][fig.subject].append(
                {
                    "path": f"figures/{fig.gallery_rel_path}",
                    "thumb": f"figures/{fig.thumb_rel_path}",
                    "filename": fig.filename,
                }
            )
        else:
            entry["qc_figures"].append(
                {
                    "path": f"figures/{fig.gallery_rel_path}",
                    "thumb": f"figures/{fig.thumb_rel_path}",
                    "filename": fig.filename,
                }
            )

    # QC entries — embed metrics inline + per-subject group/outlier metadata
    from .qc_meta import compute_subject_meta

    for qc in scan.qc_entries:
        source = qc.source_label
        if source not in manifest["localization"]:
            manifest["localization"][source] = {"subjects": {}, "qc_figures": []}
        if qc.metrics_path:
            metrics = qc_csv_to_json(qc.metrics_path)
            manifest["localization"][source]["qc_metrics"] = metrics
            subject_keys = list(manifest["localization"][source].get("subjects", {}).keys())
            meta = compute_subject_meta(metrics, subject_keys)
            manifest["localization"][source]["subject_meta"] = meta
            manifest["localization"][source]["n_outliers"] = sum(1 for m in meta.values() if m["outliers"])
        if qc.report_path:
            manifest["localization"][source]["qc_report"] = f"qc/{_slugify(source)}/qc_report.html"

    # Compute stats
    manifest["stats"] = {
        "total_figures": len(scan.figures),
        "total_tables": len(scan.tables),
        "total_summaries": n_summaries,
        "paradigm_count": len(manifest["paradigms"]),
    }

    return manifest
