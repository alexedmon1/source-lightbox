"""Build configuration dataclass."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SourceInput:
    """A labeled input directory (localization or results)."""

    path: Path
    label: str

    def __post_init__(self):
        self.path = Path(self.path)


@dataclass
class BuildConfig:
    """Configuration for a gallery build."""

    output_dir: Path
    title: str = "Source Analysis Gallery"
    localizations: list[SourceInput] = field(default_factory=list)
    results: list[SourceInput] = field(default_factory=list)
    analytics_dir: Path | None = None
    thumb_size: int = 300
    thumb_quality: int = 80
    thumb_workers: int = 4
    max_table_rows: int = 500
    render_figures: bool = True
    figure_dpi: int = 150
    # Anatomy-aware ROI brain mosaics (delegated to source-analytics).
    brain_render: bool = True
    brain_python: str | None = None       # path to source-analytics venv python
    roi_categories: str | None = None     # YAML with top-level roi_categories:
    contrasts: list[str] | None = None    # study contrasts to render (None = all)
    contrast_labels: dict | None = None   # contrast name -> readable label
    contrast_groups: dict | None = None   # contrast name -> tier/group label
    contrast_meta: dict | None = None     # contrast name -> {role, test, gate_on}
    brain_power_type: str = "relative"    # power_type filter for ROI mosaics
    # Connectivity circos (delegated to source-analytics)
    circos_render: bool = True
    contrast_pairs: list | None = None    # [{name, group_a, group_b}] for circos
    circos_metrics: list | None = None    # connectivity metrics to render (None = imag_coherence)
    # Per-paradigm nav display: paradigm key -> {group, label}. Lets a study nest
    # its paradigms under a shared group header (e.g. resting/vertex -> "Resting"
    # with "ROI-based"/"Vertex-based" sub-labels). None = flat, formatName labels.
    paradigm_display: dict | None = None
    # Treatment-group display: id -> readable label, and the id order to list
    # groups in (both from the study YAML's ``groups:`` / ``group_order:``).
    # None = format the raw id (underscores -> spaces), alphabetical order.
    group_labels: dict | None = None
    group_order: list | None = None
    # Optional "back" link rendered in the sidebar header — used when this gallery is
    # one view under a splash/landing page (e.g. report/ + exploratory/ under a shared
    # index.html). None = self-contained build, no link (so a handed-off standalone
    # build never carries a dead ../index.html).
    home_link: str | None = None
    home_label: str = "Home"
    # Analyses to omit from the gallery entirely (figures, tables, summaries, nav).
    # Defaults to the combined network aliases, now superseded by the split
    # graph + nbs modules; a study can override via `exclude_analyses:` in its yaml.
    exclude_analyses: list[str] = field(default_factory=lambda: ["roi_network", "vertex_network"])

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        if self.analytics_dir is not None:
            self.analytics_dir = Path(self.analytics_dir)
