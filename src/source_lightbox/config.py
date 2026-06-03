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

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        if self.analytics_dir is not None:
            self.analytics_dir = Path(self.analytics_dir)
