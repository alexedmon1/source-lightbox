"""Scan input directories for figures, tables, and QC artefacts."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FigureEntry:
    """A discovered figure file."""

    src_path: Path
    category: str  # "analytics" or "localization"
    source_label: str
    paradigm: str = ""
    analysis: str = ""
    subject: str = ""
    filename: str = ""

    @property
    def gallery_rel_path(self) -> str:
        """Relative path within the gallery figures/ directory."""
        label_slug = _slugify(self.source_label)
        if self.category == "analytics":
            return f"analytics/{label_slug}/{self.paradigm}/{self.analysis}/{self.filename}"
        elif self.subject:
            return f"localization/{label_slug}/subjects/{self.subject}/{self.filename}"
        else:
            return f"localization/{label_slug}/qc/{self.filename}"

    @property
    def thumb_rel_path(self) -> str:
        """Relative path for the thumbnail (always a JPEG)."""
        base = self.gallery_rel_path
        return "thumbs/" + re.sub(r"\.(png|jpe?g|webp)$", ".jpg", base, flags=re.IGNORECASE)


@dataclass
class TableEntry:
    """A discovered CSV table."""

    src_path: Path
    source_label: str
    paradigm: str
    analysis: str
    filename: str

    @property
    def gallery_rel_path(self) -> str:
        return f"tables/{self.paradigm}/{self.analysis}/{self.filename}"


@dataclass
class QCEntry:
    """QC metrics and report."""

    metrics_path: Path | None = None
    report_path: Path | None = None
    source_label: str = ""


@dataclass
class ScanResult:
    """Aggregated scan results from all scanners."""

    figures: list[FigureEntry] = field(default_factory=list)
    tables: list[TableEntry] = field(default_factory=list)
    qc_entries: list[QCEntry] = field(default_factory=list)


def _slugify(text: str) -> str:
    """Convert a label to a filesystem-safe slug."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


class LocalizationScanner:
    """Scan a source-localization output directory."""

    def __init__(self, path: Path, label: str):
        self.path = Path(path)
        self.label = label

    def scan(self) -> ScanResult:
        result = ScanResult()

        # Per-subject pipeline figures
        deriv = self.path / "derivatives"
        if deriv.exists():
            for sub_dir in sorted(deriv.iterdir()):
                if not sub_dir.is_dir() or not sub_dir.name.startswith("sub-"):
                    continue
                sub_id = sub_dir.name
                fig_dir = sub_dir / "pipeline" / "figures"
                if fig_dir.exists():
                    for fig in sorted(fig_dir.glob("*.png")):
                        result.figures.append(
                            FigureEntry(
                                src_path=fig,
                                category="localization",
                                source_label=self.label,
                                subject=sub_id,
                                filename=fig.name,
                            )
                        )

        # QC figures
        qc_dir = self.path / "qc"
        if qc_dir.exists():
            qc_figs = qc_dir / "figures"
            if qc_figs.exists():
                for fig in sorted(qc_figs.glob("*.png")):
                    result.figures.append(
                        FigureEntry(
                            src_path=fig,
                            category="localization",
                            source_label=self.label,
                            filename=fig.name,
                        )
                    )

            # QC metrics and report
            qc_entry = QCEntry(source_label=self.label)
            metrics = qc_dir / "qc_metrics.csv"
            if metrics.exists():
                qc_entry.metrics_path = metrics
            report = qc_dir / "qc_report.html"
            if report.exists():
                qc_entry.report_path = report
            if qc_entry.metrics_path or qc_entry.report_path:
                result.qc_entries.append(qc_entry)

        return result


# Raster figure formats the gallery copies and thumbnails (Pillow-readable).
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


class ResultsScanner:
    """Scan a source-analytics results directory (``tables/`` + ``figures/``).

    Point it at ``results/<profile>`` for a profile run — the layout below the
    root is the same.
    """

    def __init__(self, path: Path, label: str):
        self.path = Path(path)
        self.label = label

    def scan(self) -> ScanResult:
        result = ScanResult()

        # Figures: figures/<paradigm>/<analysis>/**/*.{png,jpg,webp}. Nested
        # subfolders are flattened into the filename (a/b.png -> a__b.png) so
        # every figure of a module lives in one gallery folder.
        figs_root = self.path / "figures"
        if figs_root.exists():
            for paradigm_dir in sorted(figs_root.iterdir()):
                if not paradigm_dir.is_dir():
                    continue
                paradigm = paradigm_dir.name
                for analysis_dir in sorted(paradigm_dir.iterdir()):
                    if not analysis_dir.is_dir():
                        continue
                    analysis = analysis_dir.name
                    for fig in sorted(p for p in analysis_dir.rglob("*") if _is_image(p)):
                        rel = fig.relative_to(analysis_dir)
                        result.figures.append(
                            FigureEntry(
                                src_path=fig,
                                category="analytics",
                                source_label=self.label,
                                paradigm=paradigm,
                                analysis=analysis,
                                filename="__".join(rel.parts),
                            )
                        )

        # Tables: tables/<paradigm>/<analysis>/*.csv
        tables_root = self.path / "tables"
        if tables_root.exists():
            for paradigm_dir in sorted(tables_root.iterdir()):
                if not paradigm_dir.is_dir():
                    continue
                paradigm = paradigm_dir.name
                for analysis_dir in sorted(paradigm_dir.iterdir()):
                    if not analysis_dir.is_dir():
                        continue
                    analysis = analysis_dir.name
                    for tbl in sorted(analysis_dir.glob("*.csv")):
                        result.tables.append(
                            TableEntry(
                                src_path=tbl,
                                source_label=self.label,
                                paradigm=paradigm,
                                analysis=analysis,
                                filename=tbl.name,
                            )
                        )

        return result


def qc_csv_to_json(csv_path: Path) -> list[dict]:
    """Convert a QC metrics CSV to a list of dicts for JSON serialization."""
    rows = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows
