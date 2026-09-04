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


def normalize_study_contrasts(study_cfg: dict) -> list[dict]:
    """Return the study's contrasts as uniform dicts, from either schema.

    Legacy studies declare ``contrasts:``; migrated studies declare
    ``hypotheses:`` (name/label/role/kind/weights). Both are normalized to the
    shape the mosaic / circos / label plumbing expects: ``name``, ``label``,
    ``role``, ``group`` (role doubles as the tier label), and ``group_a`` /
    ``group_b`` derived from the +1 / -1 entries of a two-group contrast's
    ``weights``. ``contrasts:`` takes precedence when present.
    """
    legacy = [c for c in (study_cfg.get("contrasts") or [])
              if isinstance(c, dict) and c.get("name")]
    if legacy:
        return legacy
    out: list[dict] = []
    for h in (study_cfg.get("hypotheses") or []):
        if not isinstance(h, dict) or not h.get("name"):
            continue
        weights = h.get("weights") or {}
        pos = [g for g, w in weights.items() if isinstance(w, (int, float)) and w > 0]
        neg = [g for g, w in weights.items() if isinstance(w, (int, float)) and w < 0]
        norm = {
            "name": h["name"],
            "label": h.get("label"),
            "role": h.get("role"),
            "group": h.get("role"),
        }
        if len(pos) == 1 and len(neg) == 1:
            norm["group_a"], norm["group_b"] = pos[0], neg[0]
        out.append(norm)
    return out


def resolve_config_path(raw: str | None, default: str, config_dir: Path) -> str:
    """Resolve a ``paths:`` entry from the study YAML.

    ``~`` is expanded first (the README documents
    ``source_analytics_python: ~/sandbox/.../python``), then relative paths are
    taken relative to the YAML's directory.
    """
    pp = Path(raw or default).expanduser()
    resolved = pp if pp.is_absolute() else (config_dir / pp).resolve()
    return str(resolved)


def study_group_display(study_cfg: dict) -> tuple[dict | None, list | None]:
    """``(group_labels, group_order)`` from the study YAML's ``groups:`` block.

    source-analytics declares ``groups: {id: label}`` (or a list of
    ``{name/id, label}``) plus an optional ``group_order:``. Returns ``(None,
    None)`` when the study declares neither.
    """
    raw = study_cfg.get("groups")
    labels: dict = {}
    if isinstance(raw, dict):
        labels = {str(k): (str(v) if isinstance(v, str) else str((v or {}).get("label") or k))
                  for k, v in raw.items()}
    elif isinstance(raw, list):
        for g in raw:
            if isinstance(g, dict):
                gid = g.get("name") or g.get("id")
                if gid:
                    labels[str(gid)] = str(g.get("label") or gid)
            elif isinstance(g, str):
                labels[g] = g
    order = study_cfg.get("group_order")
    order = [str(g) for g in order] if isinstance(order, list) else (list(labels) or None)
    return (labels or None), order


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
    help="source-analytics working directory (paths.analytics). Only its per-subject "
         "connectivity edge CSVs are read, for the circos chords.",
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
@click.option(
    "--render-figures/--no-render-figures",
    default=True,
    help="Render standardized figures from stat tables at build time.",
)
@click.option("--figure-dpi", default=150, type=int, help="DPI for rendered figures.")
@click.option(
    "--brain/--no-brain",
    "brain_render",
    default=True,
    help="Render anatomy-aware ROI brain mosaics via source-analytics when available.",
)
@click.option("--brain-python", default=None, help="Path to the source-analytics venv python.")
@click.option(
    "--roi-categories",
    default=None,
    type=click.Path(dir_okay=False),
    help="YAML with a top-level roi_categories: mapping (for brain mosaics).",
)
@click.option("--exclude-analysis", "exclude_analyses", multiple=True,
              help="Analysis name to omit from the gallery (repeatable). Overrides "
                   "the study config's exclude_analyses / the built-in default.")
@click.option("--home-link", default=None,
              help="Relative URL to a splash/landing page, rendered as a 'back' link in "
                   "the sidebar (e.g. ../index.html when this gallery is a view under a "
                   "splash). Omit for a self-contained standalone build.")
@click.option("--home-label", default="Home",
              help="Text for the --home-link back link.")
@click.option("--verbose/--quiet", default=True, help="Verbose output.")
@click.option("--serve", "serve_after", is_flag=True, default=False,
              help="Serve the gallery locally after building (build + preview in one step).")
@click.option("--port", "-p", default=5500, type=int, help="Port for --serve.")
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
    render_figures,
    figure_dpi,
    brain_render,
    brain_python,
    roi_categories,
    exclude_analyses,
    home_link,
    home_label,
    verbose,
    serve_after,
    port,
):
    """Build a static gallery from analysis outputs."""
    import yaml as _yaml

    # Labeled localization/results inputs from --config (CLI flags take precedence).
    config_loc_inputs = []
    config_res_inputs = []
    # Study contrasts that drive brain-mosaic rendering (read from --config).
    contrasts = None
    # Contrast name -> readable label / tier group (read from --config).
    contrast_labels = None
    contrast_groups = None
    # Contrast name -> {role, test, gate_on} hypothesis metadata (read from --config).
    contrast_meta = None
    # Contrast name + groups (for connectivity circos).
    contrast_pairs = None
    # Connectivity metrics to render as circos (from --config).
    circos_metrics = None
    # Per-paradigm nav display mapping (from --config): paradigm -> {group, label}.
    paradigm_display = None
    # Analyses to omit from the gallery (from --config); CLI flag takes precedence.
    cfg_exclude = None
    # Treatment-group display names / order (from --config `groups:`).
    group_labels = group_order = None

    # If --config provided, read paths from unified study.yaml
    if config_file is not None:
        config_path = Path(config_file).resolve()
        config_dir = config_path.parent
        with open(config_path) as f:
            study_cfg = _yaml.safe_load(f)

        paths = study_cfg.get("paths", {})

        def _resolve(p: str, default: str) -> str:
            return resolve_config_path(p, default, config_dir)

        cfg_analytics = _resolve(paths.get("analytics"), "./analytics")
        # source-analytics `--profile NAME` runs write to results/<NAME>/ and
        # analytics/<NAME>/; `paths.results_profile` selects that subtree.
        profile = paths.get("results_profile") or study_cfg.get("gallery_profile")
        if profile:
            cfg_analytics = str(Path(cfg_analytics) / str(profile))

        def _labeled_inputs(spec, scalar_default, scalar_label, explicit, sub=None):
            """Parse a paths entry that is either a list of {path, label} (compared
            sources, e.g. Shell vs Cartesian) or a single scalar path. Configured
            paths that are not directories are reported (a typo otherwise builds a
            quietly incomplete gallery); only the implicit default is skipped
            silently. ``sub`` appends a profile subdirectory."""
            out = []
            entries = spec if isinstance(spec, list) else [spec]
            for entry in entries:
                if isinstance(entry, dict):
                    p = _resolve(entry.get("path"), scalar_default)
                    lbl = entry.get("label") or Path(p).name
                else:
                    p = _resolve(entry, scalar_default)
                    lbl = (scalar_label if not isinstance(spec, list) else None) or Path(p).name
                if sub:
                    p = str(Path(p) / sub)
                if Path(p).is_dir():
                    out.append(SourceInput(path=p, label=lbl))
                elif explicit:
                    click.echo(f"WARNING: configured path is not a directory, skipping: {p}",
                               err=True)
            return out

        # Localization pipelines and analytics results are both source namespaces:
        # each may be a list of {path, label} (to compare reconstructions) or scalar.
        loc_spec = paths.get("localizations") or paths.get("localization")
        config_loc_inputs.extend(
            _labeled_inputs(loc_spec, "./localization", "Localization", loc_spec is not None)
        )
        config_res_inputs.extend(
            _labeled_inputs(paths.get("results"), "./results", None,
                            paths.get("results") is not None, sub=profile)
        )

        # Merge: CLI flags take precedence over config
        if analytics is None and Path(cfg_analytics).is_dir():
            analytics = cfg_analytics
        if title is None:
            title = (study_cfg.get("gallery_title")
                     or study_cfg.get("name", "Source Analysis Gallery"))
        if output is None:
            output = _resolve(paths.get("gallery"), "./gallery")

        # Brain mosaics: study contrasts drive which mosaics get rendered.
        study_contrasts = normalize_study_contrasts(study_cfg)
        if not contrasts:
            contrasts = [c["name"] for c in study_contrasts] or None
        if contrast_labels is None:
            contrast_labels = {c["name"]: c["label"] for c in study_contrasts if c.get("label")} or None
        if contrast_groups is None:
            contrast_groups = {c["name"]: c["group"] for c in study_contrasts if c.get("group")} or None
        if contrast_meta is None:
            contrast_meta = {
                c["name"]: {
                    "role": c.get("role", "exploratory"),
                    "test": c.get("test", "difference"),
                    "gate_on": ([c["gate_on"]] if isinstance(c.get("gate_on"), str)
                                else list(c.get("gate_on") or [])),
                }
                for c in study_contrasts
                # Only emit for contrasts that declare hypothesis-testing intent.
                if c.get("role") or c.get("test") or c.get("gate_on")
            } or None
        if contrast_pairs is None:
            contrast_pairs = [
                {"name": c["name"], "group_a": c["group_a"], "group_b": c["group_b"]}
                for c in study_contrasts if c.get("group_a") and c.get("group_b")
            ] or None
        if circos_metrics is None:
            cm = study_cfg.get("circos_metrics")
            circos_metrics = list(cm) if cm else None
        # Per-paradigm nav display, co-located under each paradigm's `display:` key.
        if paradigm_display is None:
            paradigm_display = {
                name: p["display"]
                for name, p in (study_cfg.get("paradigms") or {}).items()
                if isinstance(p, dict) and p.get("display")
            } or None
        cfg_exclude = study_cfg.get("exclude_analyses")
        # ROI categories YAML: explicit path, else conventional file beside config.
        if roi_categories is None:
            cfg_cats = paths.get("roi_categories")
            if cfg_cats:
                roi_categories = _resolve(cfg_cats, "")
            else:
                default_cats = config_dir / "allen_roi_categories_proposed.yaml"
                if default_cats.is_file():
                    roi_categories = str(default_cats)
        if brain_python is None:
            bp = paths.get("source_analytics_python")
            if bp:
                brain_python = _resolve(bp, "")
                if not Path(brain_python).is_file():
                    click.echo(f"WARNING: paths.source_analytics_python is not a file: "
                               f"{brain_python} (mosaics, circos and analysis metadata "
                               "will be unavailable)", err=True)
        group_labels, group_order = study_group_display(study_cfg)

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

    # Fall back to config-provided labeled inputs when none given on the CLI.
    if not loc_inputs and config_loc_inputs:
        loc_inputs = config_loc_inputs
    if not res_inputs and config_res_inputs:
        res_inputs = config_res_inputs

    config = BuildConfig(
        output_dir=output,
        title=title,
        localizations=loc_inputs,
        results=res_inputs,
        analytics_dir=analytics,
        thumb_size=thumb_size,
        thumb_quality=thumb_quality,
        thumb_workers=thumb_workers,
        render_figures=render_figures,
        figure_dpi=figure_dpi,
        brain_render=brain_render,
        brain_python=brain_python,
        roi_categories=roi_categories,
        contrasts=contrasts,
        contrast_labels=contrast_labels,
        contrast_groups=contrast_groups,
        contrast_meta=contrast_meta,
        contrast_pairs=contrast_pairs,
        circos_metrics=circos_metrics,
        paradigm_display=paradigm_display,
        group_labels=group_labels,
        group_order=group_order,
        home_link=home_link,
        home_label=home_label,
        # CLI flag > study-config `exclude_analyses:` > BuildConfig built-in default.
        **({"exclude_analyses": list(exclude_analyses)} if exclude_analyses
           else {"exclude_analyses": list(cfg_exclude)} if cfg_exclude is not None
           else {}),
    )

    from .builder import build as do_build

    do_build(config, verbose=verbose)

    if serve_after:
        _serve_gallery(Path(output), port)


def _serve_gallery(gallery: Path, port: int) -> None:
    """Serve a built gallery directory over HTTP until interrupted."""
    if not (gallery / "index.html").exists():
        click.echo(f"Error: {gallery} does not contain index.html. Run 'build' first.", err=True)
        sys.exit(1)

    handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(gallery))

    class _Server(socketserver.TCPServer):
        # Reuse the address so re-hosting right after a previous serve doesn't hit
        # "address already in use" while the old socket lingers in TIME_WAIT.
        allow_reuse_address = True

    click.echo(f"Serving gallery at http://localhost:{port}")
    click.echo("Press Ctrl+C to stop.")
    with _Server(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            click.echo("\nStopped.")


@main.command()
@click.argument("gallery_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--port", "-p", default=5500, type=int, help="Port to serve on.")
def serve(gallery_dir, port):
    """Serve a built gallery locally for preview."""
    _serve_gallery(Path(gallery_dir), port)


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
    click.echo(f"Digests: {stats.get('total_summaries', 0)}")

    # List paradigms and analyses
    for paradigm, analyses in manifest.get("paradigms", {}).items():
        click.echo(f"\n  {paradigm}:")
        for analysis, data in analyses.items():
            n_figs = sum(len(v) for v in data.get("figures", {}).values())
            n_tbls = sum(len(v) for v in data.get("tables", {}).values())
            has_summary = "+" if data.get("summary") else "-"
            click.echo(f"    {analysis}: {n_figs} figs, {n_tbls} tables, summary={has_summary}")
