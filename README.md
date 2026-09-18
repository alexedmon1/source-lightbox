# source-lightbox

Static gallery builder for EEG source-analysis results. It turns the output
folders of [`source-localization`](../source-localization) and
[`source-analytics`](../source-analytics) into a single self-contained website —
figures, sortable stat tables, per-subject QC, and at-a-glance overview figures
**rendered from the stat tables at build time** (no pre-generated PNGs needed).

The finished gallery is fully static (one folder of HTML/JS/PNG, manifest inlined)
so it hosts on any web server — see [`DEPLOY.md`](DEPLOY.md).

---

## Quick start

```bash
# 1. install (editable; one-time)
cd ~/sandbox/source-lightbox && uv sync

# 2. build a gallery from your study config, and preview it
source-lightbox build --config /path/to/study.yaml --serve
#   → builds the gallery folder named in the config, then serves it at
#     http://localhost:5500  (Ctrl+C to stop)
```

That's the whole happy path. The one input is a **`study.yaml`** whose `paths:`
block points at your folders — the *same* config file you already give
`source-analytics`. Everything else (output location, title, contrasts,
connectivity metrics) is read from it.

If you don't want to keep the server running, build and serve separately:

```bash
source-lightbox build --config study.yaml      # writes the gallery folder
source-lightbox serve  ./gallery_treatment      # serve it later, any time
source-lightbox info   ./gallery_treatment      # print figure/table counts
```

---

## Your folders → the gallery

A study produces three kinds of folder. You don't pass them one by one — you
name them once in the config's `paths:` block, and the builder wires them up:

| Your folder | What's in it | Config key | Shows up as |
|---|---|---|---|
| **Localization output** | per-subject source reconstruction + `qc/` (from `source-localization`) | `paths.localizations` | **Localization → Subjects / QC** |
| **Results** | `tables/<paradigm>/<analysis>/*.csv` (from `source-analytics`) | `paths.results` | **Analytics** — overview figures + tables |
| **Analytics working dir** | `<paradigm>/roi_connectivity/data/*_edges.csv` | `paths.analytics` | per-subject edge CSVs the circos chords are averaged from (the **Summary** tab is a digest generated from the tables) |

Key idea — **two source namespaces, kept separate**:

- **Localization sources** (`localizations`) are reconstruction pipelines (ROI,
  Shell, …). They drive the Subjects/QC browser and never appear under Analytics.
- **Analytics sources** (`results`) are the `source-analytics` output trees. They
  populate the Analytics section.

The Analytics nav is derived from which sources actually contain figures/tables,
so a localization-only pipeline never shows up as an empty Analytics folder, and
a single analytics source renders its paradigms directly with no redundant header.

### Each localization card says what built it

Two galleries can look identical and report different measurements. So each
localization card shows the settings that decide the numbers — atlas, head
model, source space, inverse method and **sampling mode** — read from the
`data/config_resolved.yaml` that source-localization 0.4.2+ writes beside its
outputs. A pipeline localized before that reads "not recorded" rather than being
guessed at.

Two cases are called out in the card rather than left to be noticed:

- **Monte Carlo sampling** (`source_sampling: monte_carlo`) averages the ROI
  operator over many source draws instead of solving one grid, so the pipeline
  has parcel time series only — there is no vertex-level output for it, by
  construction.
- **Subjects that disagree.** If the cohort's subjects differ on any of those
  settings, the card names which, because pooling them compares different
  measurements. source-analytics refuses such a cohort outright; the gallery
  shows it, since a frozen study may already contain one.

### Each analysis says what produced its tables

source-analytics v0.8.2+ writes a `provenance.json` beside each analysis's
tables. The gallery reads it and shows it on the analysis page:

- **Monte Carlo parcel caveats appear open**, above the tabs. A parcel the
  montage cannot separate from its neighbour, or one the run rarely sampled,
  produces an ordinary-looking table row — there is otherwise nothing in the
  gallery to distinguish it.
- **The rest is a collapsed "What produced this" strip** — the localization
  description (atlas, geometry, inverse, sampling mode), the source-localization
  and source-analytics versions, the plugin if the analysis came from one, the
  subject and group counts, and when the run happened.

An older results tree has no such file, and then nothing is shown rather than a
guess. The record's full subject-id list and lifecycle steps are dropped on the
way in: the manifest is inlined into `index.html`, once per analysis.

### The retired vertex analyses

The vertex analyses left source-analytics in v0.8.0 for the unmaintained
`source-analytics-vertex` plugin: a vertex map describes one arbitrary source
placement, and the ROI analyses over Monte Carlo operators replaced them. An
older results tree still carries their tables and figures, so the gallery
**skips them** and logs what it skipped, rather than publishing them beside
current results with nothing to mark them as retired. Pass `--include-retired`
(or set `include_retired: true` in the study config) to publish them anyway.

---

## The config the gallery reads

source-lightbox reads a **subset** of the study config — if you already run
`source-analytics` from a `study.yaml`, point the gallery at the same file. Only
these keys are consulted:

```yaml
name: "FORGE — Treatment (MS2)"      # gallery title

paths:
  results:    ./results_treatment    # source-analytics tables/  (Analytics)
  analytics:  ./analytics_treatment  # source-analytics working tree (edge CSVs for circos)
  # results_profile: external        # read results/<profile>/ + analytics/<profile>/ (SA --profile runs)
  gallery:    ./gallery_treatment    # OUTPUT dir the gallery is written to
  localizations:                     # reconstruction pipelines (Subjects/QC)
    - {path: ./localization/rest_roi,   label: "Allen ROI"}
    - {path: ./localization/rest_shell, label: "Shell"}
  # optional:
  roi_categories: ./allen_roi_categories_proposed.yaml   # optional override; default = the study's roi_categories: map
  source_analytics_python: ~/sandbox/source-analytics/.venv/bin/python   # ~ is expanded

# groups drive the treatment-group chips / labels on the Localization pages
groups: {WT_VEH: "WT Vehicle", KO_VEH: "KO Vehicle", KO_HD_ICV: "KO HD-ICV"}
group_order: [WT_VEH, KO_VEH, KO_HD_ICV]

# contrasts drive: digest labels, heatmap axes, brain-mosaic titles, circos pairs
contrasts:
  - {name: disease_effect, label: "KO vs WT", group: "Disease effect",
     group_a: KO_VEH, group_b: WT_VEH}
  - {name: hd_icv_rescue,  label: "HD-ICV rescue", group: "Treatment rescue",
     group_a: KO_HD_ICV, group_b: KO_VEH}

circos_metrics: [imag_coherence, dwpli, pli, aec, coherence]   # connectivity chords

# the atlas the ROI data were extracted with (the source-analytics `pipeline:` block):
# brain mosaics and circos use its own parcels and categories
pipeline: {atlas: allen26}
roi_categories: {...}               # the study's own category map, if it declares one
```

Paths are resolved relative to the config file. `results` and `localizations`
each accept **either** a scalar path **or** a labeled list (see *Comparing
reconstructions* below). Everything except `paths.results`/`paths.gallery` is
optional — omit `contrasts`/`circos_metrics` and you simply get fewer
study-specific figures.

> Anything the config doesn't cover can still be passed as an explicit flag
> (`--results … --label …`, `--output …`, `--title …`); CLI flags override the
> config. Run `source-lightbox build --help` for the full set.

---

## What gets rendered (the figure standard)

`source-analytics` writes stat **tables** but leaves `figures/` empty by
convention. At build time source-lightbox renders **one canonical overview
figure per analysis module** straight from the tables — the goal is a gallery a
reader can absorb (a handful of high-signal figures, not hundreds). Disable with
`--no-render-figures`.

Renderers are **column-driven**: each fires on which columns a table has, not on
the module name, so any study following the `source-analytics` schema gets the
same overview set with zero per-study configuration.

| Table has columns (subset) | Overview figure |
|---|---|
| `hypothesis`, `band`/`freq_pair`, `effect_size` | Contrast × band effect-size heatmap (★ = significant) |
| `hypothesis`, `spatial`, `band`, `effect_size` | Per-ROI effect-size heatmap (preferred contrast) |
| `hypothesis`, `spatial`, `band`, `graph_metric`, `stat` | Per-ROI graph-metric *t* heatmaps (degree/clustering/betweenness) |
| `band` + `auc`/`accuracy` + `ci_*` | Contrast × band decoding heatmap (centered at chance) |
| `band`, `max_abs_hedges_g` | Contrast × band effect-size summary heatmap |
| `band`, `cluster_stat`, `p_corrected` | Contrast × band cluster-strength heatmap |
| `key`, `component`, `n_edges`, `p_corrected` | NBS largest-component heatmap, per connectivity metric |

Column names are the native `source-analytics` hypothesis schema; the legacy
aliases (`contrast`, `roi`, `hedges_g`, `t`, `p_fdr`, `power_type`) are still
read. Per-row significance precedence: `significant` flag → `q_value` → `p_corrected`
→ `p_fdr` → `p_value` (threshold 0.05). Bands order Delta, Theta, Alpha, Beta,
Low Gamma, High Gamma (unknown bands appended). Per-vertex raw tables
(`vertex_idx`) are skipped — their `*_summary` carries the overview. A module
whose tables match no renderer simply contributes no figure; its tables stay in
the gallery as sortable CSVs. To add a figure type, append a renderer to
`REGISTRY` in `src/source_lightbox/render.py`.

> Per-subject localization figures are **not** analysis figures — they live under
> **Localization → Subjects** (one subject at a time) and **→ QC**, separate from
> this overview set.

### Brain mosaics and connectivity circos (optional, anatomy-aware)

Two module types get a richer figure than a heatmap, delegated to
`source-analytics` (its atlas data) via a subprocess to its venv — so
source-lightbox itself stays lightweight. If that interpreter isn't found, both
fall back to a heatmap.

- **Brain mosaics** — ROI modules with a `*_posthoc_roi` table get ROI effect
  sizes painted on mouse-brain anatomy, one mosaic per `(contrast, band)` with
  ≥1 FDR-significant ROI (aperiodic tables facet on `dv` — exponent / offset —
  instead of band). The mosaics are drawn on the study's atlas (`pipeline.atlas`)
  when source-analytics supports it (the release with `resolve_atlas`); an older
  one draws allen32, and the build warns if that leaves the study's parcels blank.
- **Connectivity circos** — NBS modules (`roi_nbs`) with a
  `*_subnetwork_edges.csv` table (written by `source-analytics` next to
  `roi_nbs_hypotheses.csv`; it lists the edges of every NBS component) get
  significance chord diagrams (the study's ROIs, grouped by its categories) alongside
  the NBS component heatmap, one per `circos_metrics` entry × contrast × band
  with an FDR-significant subnetwork. The chords are group-mean differences
  from `roi_connectivity`'s per-subject edge CSV under `paths.analytics`.

**ROI categories**, first match wins: `--roi-categories` / `paths.roi_categories`;
the study's own `roi_categories:` map (a profile's narrowed map when building a
profile subtree); the atlas's own category file; and only then a best-overlap
guess across the atlas data. The guess used to be the only route and could see
only files named exactly `roi_categories.yaml`, which for allen26 data picked
allen32's partition and dropped six parcels from every circos. ROIs the chosen
categories do not cover are now reported in the build log instead of vanishing.

Both are curated by the config (`contrasts:` / `hypotheses:`, `circos_metrics:`,
`pipeline.atlas`, `roi_categories:`, `paths.source_analytics_python`). Override on the CLI with
`--roi-categories`, `--brain-python`, or `--no-brain`. If the source-analytics
interpreter is missing or cannot import, the build prints a warning and falls
back to heatmaps (and groups every analysis under "Other", since the domain
metadata comes from the same interpreter).

---

## Comparing reconstructions (Shell ↔ Cartesian, ROI ↔ Shell, …)

To compare the same analysis across two reconstructions, give each `results`
tree a label and match it to a localization label:

```yaml
paths:
  results:
    - {path: ./results_vertex_shell,     label: "Shell"}
    - {path: ./results_vertex_cartesian, label: "Cartesian"}
  localizations:
    - {path: ./localization/rest_shell,     label: "Shell"}
    - {path: ./localization/rest_cartesian, label: "Cartesian"}
```

The analysis pages then show a **Shell ↔ Cartesian** source toggle, and each
source's QC/subjects line up with its analytics.

---

## Features

- Lightbox image viewer with zoom, pan, keyboard navigation
- Sortable stat tables with significance highlighting
- Overview figures rendered from tables at build time (column-driven)
- Domain-grouped Analytics nav with secondary analyses nested under their primary
- Per-subject localization browser + tabbed QC with outlier flags
- Dark/light theme, full-text figure search, lazy thumbnails (500+ figures)
- Fully static — drop the folder on any web server

---

## More

- **Hosting on a LAN/workstation (nginx):** [`DEPLOY.md`](DEPLOY.md)
- **Design rationale (source model, figure curation, QC, UX):**
  [`DESIGN_NOTES.md`](DESIGN_NOTES.md) — read this before changing rendering behavior.
</content>
