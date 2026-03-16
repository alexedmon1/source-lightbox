"""Build the manifest.json from scan results."""

from __future__ import annotations

import csv
from pathlib import Path

from .markdown_convert import md_to_html
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


def build_manifest(scan: ScanResult, title: str, max_table_rows: int = 500) -> dict:
    """Build the manifest dictionary from aggregated scan results.

    Tables are embedded as parsed CSV data and summaries as rendered HTML,
    so the gallery works without a server (no fetch() needed).
    """
    manifest = {
        "title": title,
        "paradigms": {},
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

    # Summaries — embed converted HTML inline
    for summary in scan.summaries:
        paradigm = summary.paradigm
        analysis = summary.analysis
        if paradigm in manifest["paradigms"] and analysis in manifest["paradigms"][paradigm]:
            html = md_to_html(summary.src_path)
            manifest["paradigms"][paradigm][analysis]["summary"] = html

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

    # QC entries — embed metrics inline
    for qc in scan.qc_entries:
        source = qc.source_label
        if source not in manifest["localization"]:
            manifest["localization"][source] = {"subjects": {}, "qc_figures": []}
        if qc.metrics_path:
            manifest["localization"][source]["qc_metrics"] = qc_csv_to_json(qc.metrics_path)
        if qc.report_path:
            manifest["localization"][source]["qc_report"] = "qc/qc_report.html"

    # Compute stats
    manifest["stats"] = {
        "total_figures": len(scan.figures),
        "total_tables": len(scan.tables),
        "total_summaries": len(scan.summaries),
        "paradigm_count": len(manifest["paradigms"]),
    }

    return manifest
