"""Convert ANALYSIS_SUMMARY.md files to HTML fragments."""

from __future__ import annotations

from pathlib import Path

import markdown


def md_to_html(md_path: Path) -> str:
    """Convert a Markdown file to an HTML fragment string."""
    text = md_path.read_text(encoding="utf-8")
    html = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "codehilite", "toc"],
    )
    return html
