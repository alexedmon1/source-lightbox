"""Tests for manifest module."""

from pathlib import Path

import pytest

from source_lightbox.manifest import build_manifest
from source_lightbox.scanner import FigureEntry, ScanResult, SummaryEntry, TableEntry


@pytest.fixture
def tmp_csv(tmp_path):
    """Create a temporary CSV file."""
    csv = tmp_path / "test.csv"
    csv.write_text("group_a,group_b,p,significant\n30mgkg,Vehicle,0.05,TRUE\n6mgkg,Vehicle,0.10,FALSE\n")
    return csv


@pytest.fixture
def tmp_summary(tmp_path):
    """Create a temporary ANALYSIS_SUMMARY.md file."""
    md = tmp_path / "ANALYSIS_SUMMARY.md"
    md.write_text("# PSD Analysis\nResults are **significant**.\n")
    return md


def test_build_manifest_basic(tmp_csv, tmp_summary):
    scan = ScanResult()
    scan.figures.append(
        FigureEntry(
            src_path="/tmp/fig.png",
            category="analytics",
            source_label="Allen ROI",
            paradigm="resting",
            analysis="psd",
            filename="psd_global.png",
        )
    )
    scan.tables.append(
        TableEntry(
            src_path=tmp_csv,
            source_label="Allen ROI",
            paradigm="resting",
            analysis="psd",
            filename="psd_omnibus.csv",
        )
    )
    scan.summaries.append(
        SummaryEntry(
            src_path=tmp_summary,
            paradigm="resting",
            analysis="psd",
        )
    )

    manifest = build_manifest(scan, "Test Gallery")

    assert manifest["title"] == "Test Gallery"
    assert "Allen ROI" in manifest["sources"]
    assert "resting" in manifest["paradigms"]
    assert "psd" in manifest["paradigms"]["resting"]
    assert manifest["stats"]["total_figures"] == 1
    assert manifest["stats"]["total_tables"] == 1
    assert manifest["stats"]["total_summaries"] == 1

    psd = manifest["paradigms"]["resting"]["psd"]

    # Figures still reference paths
    assert len(psd["figures"]["Allen ROI"]) == 1

    # Tables are now inline with headers + rows
    tbl = psd["tables"]["Allen ROI"][0]
    assert tbl["filename"] == "psd_omnibus.csv"
    assert tbl["headers"] == ["group_a", "group_b", "p", "significant"]
    assert len(tbl["rows"]) == 2
    assert tbl["rows"][0] == ["30mgkg", "Vehicle", "0.05", "TRUE"]

    # Summary is now inline HTML
    assert "<strong>" in psd["summary"] or "<h1>" in psd["summary"]


def test_build_manifest_multi_source(tmp_csv):
    scan = ScanResult()
    for source in ["Allen ROI", "Allen Shell"]:
        scan.figures.append(
            FigureEntry(
                src_path=f"/tmp/{source}/fig.png",
                category="analytics",
                source_label=source,
                paradigm="resting",
                analysis="psd",
                filename="psd_global.png",
            )
        )
        scan.tables.append(
            TableEntry(
                src_path=tmp_csv,
                source_label=source,
                paradigm="resting",
                analysis="psd",
                filename="psd_omnibus.csv",
            )
        )

    manifest = build_manifest(scan, "Multi Source")
    assert len(manifest["sources"]) == 2
    psd = manifest["paradigms"]["resting"]["psd"]
    assert "Allen ROI" in psd["figures"]
    assert "Allen Shell" in psd["figures"]
    assert "Allen ROI" in psd["tables"]
    assert "Allen Shell" in psd["tables"]


def test_build_manifest_empty():
    scan = ScanResult()
    manifest = build_manifest(scan, "Empty")
    assert manifest["stats"]["total_figures"] == 0
    assert manifest["stats"]["paradigm_count"] == 0
