"""Click CLI for source-lightbox: build, serve, info."""

from __future__ import annotations

import http.server
import json
import socketserver
import sys
from functools import partial
from pathlib import Path

import click

from .config import BuildConfig, SourceInput


class _PairedOption(click.Option):
    """Custom option that collects paired --flag/--label values."""


@click.group()
@click.version_option()
def main():
    """source-lightbox: Static gallery builder for EEG source analysis results."""
    pass


@main.command()
@click.option(
    "--config",
    "config_file",
    type=click.Path(exists=True, dir_okay=False),
    help="Unified study.yaml — auto-populates --localization, --results, --analytics from paths section.",
)
@click.option(
    "--localization",
    "localizations",
    multiple=True,
    type=click.Path(exists=True, file_okay=False),
    help="Localization output directory (repeatable, pair with --label).",
)
@click.option(
    "--results",
    "results_dirs",
    multiple=True,
    type=click.Path(exists=True, file_okay=False),
    help="Results directory (repeatable, pair with --label).",
)
@click.option(
    "--label",
    "labels",
    multiple=True,
    help="Label for the preceding --localization or --results (applied in order).",
)
@click.option(
    "--analytics",
    type=click.Path(exists=True, file_okay=False),
    help="Analytics working directory (for ANALYSIS_SUMMARY.md files).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default=None,
    help="Output gallery directory.",
)
@click.option("--title", default=None, help="Gallery title.")
@click.option("--thumb-size", default=300, type=int, help="Thumbnail max dimension.")
@click.option("--thumb-quality", default=80, type=int, help="Thumbnail JPEG quality.")
@click.option("--thumb-workers", default=4, type=int, help="Parallel thumbnail workers.")
@click.option("--verbose/--quiet", default=True, help="Verbose output.")
def build(
    config_file,
    localizations,
    results_dirs,
    labels,
    analytics,
    output,
    title,
    thumb_size,
    thumb_quality,
    thumb_workers,
    verbose,
):
    """Build a static gallery from analysis outputs."""
    import yaml as _yaml

    # If --config provided, read paths from unified study.yaml
    if config_file is not None:
        config_path = Path(config_file).resolve()
        config_dir = config_path.parent
        with open(config_path) as f:
            study_cfg = _yaml.safe_load(f)

        paths = study_cfg.get("paths", {})

        def _resolve(p: str, default: str) -> str:
            raw = p or default
            pp = Path(raw)
            resolved = pp if pp.is_absolute() else (config_dir / pp).resolve()
            return str(resolved)

        cfg_loc = _resolve(paths.get("localization"), "./localization")
        cfg_results = _resolve(paths.get("results"), "./results")
        cfg_analytics = _resolve(paths.get("analytics"), "./analytics")

        # Merge: CLI flags take precedence over config
        if not localizations:
            localizations = (cfg_loc,) if Path(cfg_loc).is_dir() else ()
        if not results_dirs:
            results_dirs = (cfg_results,) if Path(cfg_results).is_dir() else ()
        if analytics is None and Path(cfg_analytics).is_dir():
            analytics = cfg_analytics
        if title is None:
            title = study_cfg.get("name", "Source Analysis Gallery")
        if output is None:
            output = _resolve(paths.get("gallery"), "./gallery")

    if title is None:
        title = "Source Analysis Gallery"
    if output is None:
        click.echo("Error: --output is required (or provide --config with paths.gallery).", err=True)
        sys.exit(1)

    # Parse paired inputs with labels
    # Labels are assigned in order to the combined list of localizations + results
    all_inputs = []
    for path in localizations:
        all_inputs.append(("localization", path))
    for path in results_dirs:
        all_inputs.append(("results", path))

    # Pad labels with auto-generated ones if needed
    padded_labels = list(labels)
    for i in range(len(padded_labels), len(all_inputs)):
        padded_labels.append(Path(all_inputs[i][1]).name)

    loc_inputs = []
    res_inputs = []
    label_idx = 0
    for kind, path in all_inputs:
        lbl = padded_labels[label_idx]
        label_idx += 1
        si = SourceInput(path=path, label=lbl)
        if kind == "localization":
            loc_inputs.append(si)
        else:
            res_inputs.append(si)

    config = BuildConfig(
        output_dir=output,
        title=title,
        localizations=loc_inputs,
        results=res_inputs,
        analytics_dir=analytics,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        thumb_workers=thumb_workers,
    )

    from .builder import build as do_build

    do_build(config, verbose=verbose)


@main.command()
@click.argument("gallery_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--port", "-p", default=5500, type=int, help="Port to serve on.")
def serve(gallery_dir, port):
    """Serve a built gallery locally for preview."""
    gallery = Path(gallery_dir)
    if not (gallery / "index.html").exists():
        click.echo(f"Error: {gallery} does not contain index.html. Run 'build' first.", err=True)
        sys.exit(1)

    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(gallery))
    click.echo(f"Serving gallery at http://localhost:{port}")
    click.echo("Press Ctrl+C to stop.")
    with socketserver.TCPServer(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            click.echo("\nStopped.")


@main.command()
@click.argument("gallery_dir", type=click.Path(exists=True, file_okay=False))
def info(gallery_dir):
    """Print stats about a built gallery."""
    gallery = Path(gallery_dir)
    manifest_path = gallery / "data" / "manifest.json"
    if not manifest_path.exists():
        click.echo(f"Error: No manifest.json found in {gallery}/data/", err=True)
        sys.exit(1)

    manifest = json.loads(manifest_path.read_text())
    stats = manifest.get("stats", {})

    click.echo(f"Gallery: {manifest.get('title', 'Unknown')}")
    click.echo(f"Location: {gallery.resolve()}")
    click.echo(f"Sources: {', '.join(manifest.get('sources', []))}")
    click.echo(f"Paradigms: {stats.get('paradigm_count', 0)}")
    click.echo(f"Figures: {stats.get('total_figures', 0)}")
    click.echo(f"Tables: {stats.get('total_tables', 0)}")
    click.echo(f"Summaries: {stats.get('total_summaries', 0)}")

    # List paradigms and analyses
    for paradigm, analyses in manifest.get("paradigms", {}).items():
        click.echo(f"\n  {paradigm}:")
        for analysis, data in analyses.items():
            n_figs = sum(len(v) for v in data.get("figures", {}).values())
            n_tbls = sum(len(v) for v in data.get("tables", {}).values())
            has_summary = "+" if data.get("summary") else "-"
            click.echo(f"    {analysis}: {n_figs} figs, {n_tbls} tables, summary={has_summary}")
