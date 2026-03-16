"""Convert ANALYSIS_SUMMARY.md files to HTML fragments."""

from __future__ import annotations

import re
from pathlib import Path

import markdown


def _fix_table_pipes(text: str) -> str:
    """Escape literal pipe characters inside markdown table cells.

    Markdown table parsers treat every ``|`` as a column separator.
    Patterns like ``|t|`` or ``|g|`` in header/data cells break parsing.
    Replace ``|<word>|`` with the escaped form so the table renders correctly.
    """
    lines = text.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        # Only process lines that look like table rows (start and end with |)
        if stripped.startswith("|") and stripped.endswith("|"):
            # Protect separator rows (|---|---|)
            if re.match(r"^\|[\s:|-]+\|$", stripped):
                result.append(line)
                continue
            # Replace |word| patterns mid-cell with escaped version
            # Match |word| that isn't at cell boundaries (preceded/followed by space)
            line = re.sub(
                r"(?<=\s)\|([a-zA-Z0-9_]+)\|(?=\s)",
                r"&#124;\1&#124;",
                line,
            )
        result.append(line)
    return "\n".join(result)


def md_to_html(md_path: Path) -> str:
    """Convert a Markdown file to an HTML fragment string."""
    text = md_path.read_text(encoding="utf-8")
    text = _fix_table_pipes(text)
    html = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "codehilite", "toc"],
    )
    return html
