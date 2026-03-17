"""Tests for scanner module."""

import csv
from pathlib import Path

import pytest

from source_lightbox.scanner import (
    AnalyticsScanner,
    LocalizationScanner,
    ResultsScanner,
    _slugify,
)


@pytest.fixture
def tmp_localization(tmp_path):
    """Create a mock localization directory structure."""
    # Per-subject figures
    sub_dir = tmp_path / "derivatives" / "sub-AUT01" / "pipeline" / "figures"
    sub_dir.mkdir(parents=True)
    (sub_dir / "step1_registration.png").write_bytes(b"PNG")
    (sub_dir / "step2_source_space.png").write_bytes(b"PNG")

    # QC figures
    qc_figs = tmp_path / "qc" / "figures"
    qc_figs.mkdir(parents=True)
    (qc_figs / "qc_summary.png").write_bytes(b"PNG")

    # QC metrics CSV
    qc_csv = tmp_path / "qc" / "qc_metrics.csv"
    with open(qc_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["subject", "snr", "gof"])
        w.writerow(["sub-AUT01", "5.2", "0.85"])

    # QC report
    (tmp_path / "qc" / "qc_report.html").write_text("<html>report</html>")

    return tmp_path


@pytest.fixture
def tmp_results(tmp_path):
    """Create a mock results directory structure."""
    # Figures
    fig_dir = tmp_path / "figures" / "resting" / "roi_psd"
    fig_dir.mkdir(parents=True)
    (fig_dir / "roi_psd_global.png").write_bytes(b"PNG")
    (fig_dir / "roi_psd_regional.png").write_bytes(b"PNG")

    # Tables
    tbl_dir = tmp_path / "tables" / "resting" / "roi_psd"
    tbl_dir.mkdir(parents=True)
    (tbl_dir / "roi_psd_omnibus.csv").write_text("group_a,group_b,p\n30mgkg,Vehicle,0.05\n")

    return tmp_path


@pytest.fixture
def tmp_analytics(tmp_path):
    """Create a mock analytics directory structure."""
    summary_dir = tmp_path / "resting" / "roi_psd"
    summary_dir.mkdir(parents=True)
    (summary_dir / "ANALYSIS_SUMMARY.md").write_text("# PSD Analysis\nDone.")

    summary_dir2 = tmp_path / "chirp" / "roi_evoked"
    summary_dir2.mkdir(parents=True)
    (summary_dir2 / "ANALYSIS_SUMMARY.md").write_text("# Chirp Evoked\nDone.")

    return tmp_path


def test_slugify():
    assert _slugify("Allen ROI") == "allen_roi"
    assert _slugify("Hello World!") == "hello_world"


def test_localization_scanner(tmp_localization):
    scanner = LocalizationScanner(tmp_localization, "Test Source")
    result = scanner.scan()

    assert len(result.figures) == 3  # 2 subject + 1 QC
    assert len(result.qc_entries) == 1

    sub_figs = [f for f in result.figures if f.subject]
    assert len(sub_figs) == 2
    assert sub_figs[0].subject == "sub-AUT01"

    qc_figs = [f for f in result.figures if not f.subject]
    assert len(qc_figs) == 1

    assert result.qc_entries[0].metrics_path is not None
    assert result.qc_entries[0].report_path is not None


def test_results_scanner(tmp_results):
    scanner = ResultsScanner(tmp_results, "Test Source")
    result = scanner.scan()

    assert len(result.figures) == 2
    assert result.figures[0].paradigm == "resting"
    assert result.figures[0].analysis == "roi_psd"

    assert len(result.tables) == 1
    assert result.tables[0].filename == "roi_psd_omnibus.csv"


def test_analytics_scanner(tmp_analytics):
    scanner = AnalyticsScanner(tmp_analytics)
    result = scanner.scan()

    assert len(result.summaries) == 2
    paradigms = {s.paradigm for s in result.summaries}
    assert "resting" in paradigms
    assert "chirp" in paradigms


def test_figure_entry_paths(tmp_results):
    scanner = ResultsScanner(tmp_results, "Allen ROI")
    result = scanner.scan()
    fig = result.figures[0]

    assert "allen_roi" in fig.gallery_rel_path
    assert fig.gallery_rel_path.startswith("analytics/")
    assert fig.thumb_rel_path.startswith("thumbs/")
    assert fig.thumb_rel_path.endswith(".jpg")
