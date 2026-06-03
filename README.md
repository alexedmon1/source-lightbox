# source-lightbox

Static gallery builder for EEG source analysis results. Generates a self-contained, portable website from `source-localization` and `source-analytics` outputs.

## Installation

```bash
cd ~/sandbox/source-lightbox
uv sync
```

## Usage

```bash
# Build gallery
source-lightbox build \
  --localization /path/to/localization_output --label "Allen ROI" \
  --results /path/to/results --label "Allen ROI" \
  --analytics /path/to/analytics \
  --output ./gallery \
  --title "My Study"

# Serve locally
source-lightbox serve ./gallery --port 5500

# Print stats
source-lightbox info ./gallery
```

## Features

- Lightbox image viewer with zoom, pan, keyboard navigation
- Sortable statistical tables with significance highlighting
- **Standardized figures rendered from stat tables at build time** (see below)
- Dark/light theme with system preference detection
- Comparison mode for multiple sources (ROI vs Shell, etc.)
- Search across all figures by filename, paradigm, analysis
- Lazy-loaded thumbnails for fast browsing of 500+ figures
- Fully static — drop on any web server

## Figure standard (rendered from tables)

The gallery does **not** require pre-generated analysis figures. At build time
`source-lightbox` renders **one canonical overview figure per analysis module**
directly from the `results/tables/<paradigm>/<analysis>/*.csv` outputs of
`source-analytics`. The goal is a gallery a reader can actually absorb — a
handful of high-signal figures, not hundreds. Disable with `--no-render-figures`.

For each `(source, paradigm, analysis)` module the builder picks the single most
informative table (an effect-size *summary* in preference to per-ROI / per-vertex
detail; see `_table_priority` in `render.py`) and renders exactly one figure,
collapsing any measure/`dv` facet to its primary value (e.g. relative power,
coherence). Rendering is *column-driven*: a renderer fires on which columns a
table has, not on the module's name — so any study following these schema
conventions gets the same overview set with no per-study configuration.

| Table has columns (subset) | Overview figure |
|---|---|
| `contrast`, `band`/`freq_pair`, `hedges_g` | Contrast × band effect-size heatmap (★ = significant) |
| `contrast`, `roi`, `band`, `hedges_g` | Per-ROI effect-size heatmap (preferred contrast) |
| `band` + `auc`/`accuracy` + `ci_*` | Contrast × band decoding heatmap (centered at chance) |
| `band`, `max_abs_hedges_g` | Contrast × band effect-size summary heatmap |
| `band`, `cluster_stat`, `p_corrected` | Contrast × band cluster-strength heatmap |
| `key`, `component`, `n_edges`, `p_corrected` | NBS largest-component-per-key bars |

Significance precedence per row: `significant` flag → `q_value` → `p_corrected`
→ `p_value` (threshold 0.05). Bands are ordered Delta, Theta, Alpha, Beta,
Low Gamma, High Gamma (unknown bands appended). Per-vertex raw tables
(`vertex_idx`) are skipped — their `*_summary` tables carry the overview. A module
whose tables match no renderer simply contributes no figure; its tables remain in
the gallery as sortable CSVs. To add a figure type, append a renderer to
`REGISTRY` in `src/source_lightbox/render.py`.

> Per-subject localization pipeline figures are **not** analysis figures — they
> live under **Localization → Subjects** (one subject at a time) and
> **Localization → QC**, separate from this overview set.

### Anatomy-aware ROI brain mosaics

For ROI modules that have a per-ROI posthoc table (`*_posthoc_roi.csv`), the
overview heatmap is replaced by **brain mosaics** — ROI effect sizes painted on
mouse-brain anatomy across coronal/axial/sagittal views, with an all-ROIs row and
an FDR-significant row (publication style). These delegate to
`source_analytics.viz.brain_roi` (with its bundled Allen atlas) via a subprocess
to the source-analytics venv, so source-lightbox stays lightweight; if that
interpreter isn't found, the module falls back to the flat heatmap.

Mosaics are curated by the study config: one per **(contrast, band)** where the
contrast is listed in the study's `contrasts:` and the band has ≥1 FDR-significant
ROI, for the primary `power_type` (default `relative`). Controlled by:

```
--config study.yaml         # contrasts come from its `contrasts:` list
--roi-categories FILE.yaml  # default: allen_roi_categories_proposed.yaml beside the config
--brain-python PATH         # default: ~/sandbox/source-analytics/.venv/bin/python
--no-brain                  # disable, use heatmaps everywhere
```

### Config-driven build with multiple localizations

The `--config study.yaml` form reads a `paths:` block. For source comparison
(e.g. ROI vs Shell), list labeled localization directories:

```yaml
paths:
  analytics: ./analytics_treatment
  results: ./results_treatment
  gallery: ./gallery_treatment
  localizations:
    - {path: ./localization/rest_roi, label: "Allen ROI"}
    - {path: ./localization/rest_shell, label: "Shell"}
```

A scalar `localization: ./localization` is still accepted for single-pipeline studies.
