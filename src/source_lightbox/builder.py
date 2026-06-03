"""Orchestrate the gallery build: scan, copy, thumbs, HTML, manifest."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import jinja2

from .config import BuildConfig
from .manifest import build_manifest
from .scanner import (
    AnalyticsScanner,
    LocalizationScanner,
    ResultsScanner,
    ScanResult,
)
from .thumbnails import generate_thumbnails


def build(config: BuildConfig, verbose: bool = True) -> Path:
    """Run the full gallery build pipeline.

    Returns the output directory path.
    """
    out = config.output_dir
    _log = print if verbose else lambda *a, **k: None

    # 1. Scan all inputs
    _log("Scanning inputs...")
    scan = ScanResult()

    for loc_input in config.localizations:
        _log(f"  Localization: {loc_input.path} [{loc_input.label}]")
        scanner = LocalizationScanner(loc_input.path, loc_input.label)
        partial = scanner.scan()
        _merge_scan(scan, partial)

    for res_input in config.results:
        _log(f"  Results: {res_input.path} [{res_input.label}]")
        scanner = ResultsScanner(res_input.path, res_input.label)
        partial = scanner.scan()
        _merge_scan(scan, partial)

    if config.analytics_dir:
        _log(f"  Analytics: {config.analytics_dir}")
        scanner = AnalyticsScanner(config.analytics_dir)
        partial = scanner.scan()
        _merge_scan(scan, partial)

    _log(
        f"  Found: {len(scan.figures)} figures, {len(scan.tables)} tables, "
        f"{len(scan.summaries)} summaries"
    )

    # 2. Prepare output directory. Rendered analytics figures are regenerated
    #    every build, so clear stale ones (and their thumbnails) to avoid orphans
    #    from a prior run. Localization figures are stable and kept.
    out.mkdir(parents=True, exist_ok=True)
    for sub in ("figures/analytics", "figures/thumbs/analytics", "qc"):
        shutil.rmtree(out / sub, ignore_errors=True)

    # 2b. Render standardized figures from tables (staged, then treated like any
    #     other discovered figure by the copy/thumbnail/manifest steps below).
    staging_dir = out / ".rendered"
    if config.render_figures and scan.tables:
        _log("Rendering figures from tables...")
        from .render import render_table_figures

        brain = None
        if config.brain_render and config.roi_categories:
            brain = {
                "categories": config.roi_categories,
                "contrasts": config.contrasts,
                "labels": config.contrast_labels,
                "python": config.brain_python,
                "power_type": config.brain_power_type,
            }

        rendered = render_table_figures(
            scan.tables, staging_dir, dpi=config.figure_dpi, log=_log,
            brain=brain, contrast_labels=config.contrast_labels,
        )
        scan.figures.extend(rendered)
        _log(f"  Rendered {len(rendered)} figures from {len(scan.tables)} tables")

    # 3. Copy figures
    _log("Copying figures...")
    for fig in scan.figures:
        dst = out / "figures" / fig.gallery_rel_path
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fig.src_path, dst)

    # 4. Process QC report (a full self-contained HTML page). Namespace by source
    #    slug so multiple localization sources (e.g. ROI + Shell) don't collide.
    from .scanner import _slugify

    for qc in scan.qc_entries:
        if qc.report_path:
            qc_out = out / "qc" / _slugify(qc.source_label)
            qc_out.mkdir(parents=True, exist_ok=True)
            shutil.copy2(qc.report_path, qc_out / "qc_report.html")

    # 5. Generate thumbnails
    _log("Generating thumbnails...")
    thumb_tasks = []
    for fig in scan.figures:
        src = out / "figures" / fig.gallery_rel_path
        dst = out / "figures" / fig.thumb_rel_path
        thumb_tasks.append((src, dst))

    def _progress(done, total):
        if done % 50 == 0 or done == total:
            _log(f"  Thumbnails: {done}/{total}")

    errors = generate_thumbnails(
        thumb_tasks,
        size=config.thumb_size,
        quality=config.thumb_quality,
        workers=config.thumb_workers,
        on_progress=_progress,
    )
    if errors:
        for err in errors:
            _log(f"  WARNING: {err}")

    # 6. Build manifest (tables + summaries are embedded inline)
    _log("Building manifest...")
    manifest = build_manifest(
        scan, config.title, max_table_rows=config.max_table_rows,
        contrast_labels=config.contrast_labels,
    )
    manifest_json = json.dumps(manifest, indent=2)
    data_dir = out / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "manifest.json").write_text(manifest_json, encoding="utf-8")

    # 7. Render HTML
    _log("Rendering HTML...")
    _render_html(out, manifest_json, title=config.title)

    # 8. Copy static assets
    _log("Copying static assets...")
    _copy_static(out)

    # 9. Clean up staged renders (already copied into figures/ above)
    if staging_dir.exists():
        shutil.rmtree(staging_dir, ignore_errors=True)

    _log(f"Gallery built: {out}")
    _log(f"  {manifest['stats']['total_figures']} figures")
    _log(f"  {manifest['stats']['total_tables']} tables")
    _log(f"  {manifest['stats']['total_summaries']} summaries")

    return out


def _merge_scan(target: ScanResult, source: ScanResult):
    """Merge source scan results into target."""
    target.figures.extend(source.figures)
    target.tables.extend(source.tables)
    target.summaries.extend(source.summaries)
    target.qc_entries.extend(source.qc_entries)


def _render_html(out: Path, manifest_json: str, title: str = "Source Analysis Gallery"):
    """Render the index.html from the Jinja2 template."""
    template_dir = Path(__file__).parent / "templates"
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(template_dir)),
        autoescape=True,
    )
    template = env.get_template("index.html.j2")
    html = template.render(
        manifest_json=manifest_json,
        title=title,
        build_ts=str(int(time.time())),
    )
    (out / "index.html").write_text(html, encoding="utf-8")


def _copy_static(out: Path):
    """Copy vendored static assets to output."""
    static_src = Path(__file__).parent / "static"
    if not static_src.exists():
        return

    assets_dir = out / "assets"
    for sub in ("css", "js"):
        src_dir = static_src / sub
        if not src_dir.exists():
            continue
        dst_dir = assets_dir / sub
        dst_dir.mkdir(parents=True, exist_ok=True)
        for f in src_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, dst_dir / f.name)
