# source-lightbox — design notes

Running record of the design decisions behind the gallery, so they aren't
re-litigated. Newest sections at the bottom.

## Source model: two namespaces

The `paths:` block in a study YAML defines two *kinds* of source, kept strictly
separate in the gallery:

- **Localization sources** (`paths.localizations`) — the source-reconstruction
  pipelines (ROI, Shell, Cartesian, …). They power **Localization → Subjects/QC**
  and **never** appear under Analytics.
- **Analytics sources** (`paths.results`) — `source-analytics` output trees
  (`figures/`, `tables/`). They populate **Analytics**.

Both accept either a scalar path or a labeled list `[{path, label}]`. Use the
labeled list to compare reconstructions (e.g. a `vertex` analysis on Shell vs
Cartesian); match the analytics label to the localization label so each source's
QC/subjects line up with its analytics. Parsed by `_labeled_inputs` in `cli.py`.

The Analytics nav/overview is derived **from the data** (`analyticsSources()` in
`app.js` — a source must carry ≥1 figure/table), not from hardcoded names. So
localization-only pipelines never show as empty Analytics folders, and a single
analytics source renders its paradigms directly with no redundant header or
breadcrumb. Key axes: **paradigm** = analysis family (resting/vertex);
**source** = reconstruction basis.

## Figures rendered from tables (no pre-generated PNGs)

`source-analytics` results carry tables but the `figures/` dirs are empty by
convention. The lightbox renders figures at build time:

- **One canonical overview per analysis module.** `render.py` groups tables by
  `(source, paradigm, analysis)`, picks the highest-priority table
  (`_table_priority`: global/summary over per-unit detail), and renders one
  figure — collapsing measure/`dv` facets to a primary value. Column-driven
  renderers (fire on columns, not module names) → any conformant study works.
- **Brain mosaics** for ROI modules with a `*_posthoc_roi` table: anatomy-aware
  ROI effect-size mosaics via `source_analytics.viz.brain_roi` (+ Allen atlas),
  run as a subprocess to the source-analytics venv (`brain_mosaic.py` +
  `_brain_render_worker.py`). Heatmap fallback if source-analytics is absent.
  Curated by the study config: one mosaic per `(contrast, band)` where the
  contrast is in `contrasts:` and the band has ≥1 FDR-significant ROI, for the
  primary `power_type` (default `relative`). FORGE roi_psd → 5 mosaics (was 120+).
- Contrast **labels** come from `contrasts[].label` in the YAML (required, no
  auto-prettify) and apply everywhere: digest, heatmap axes, mosaic titles.
- **Connectivity circos** for NBS modules (`roi_nbs`) that carry a
  `*_subnetwork_edges.csv` table — the per-edge membership of every NBS
  component that source-analytics writes next to `roi_nbs_hypotheses.csv`
  (roi_connectivity's per-edge posthoc tables were retired 2026-06-25, so the
  old `*_posthoc_region_pair` trigger never fired on a fresh run). Significance
  chord diagrams (32 ROIs grouped/colored by their 10 anatomical regions,
  Yeo-style) show the group difference — direction + magnitude — with the edges
  of each FDR-significant subnetwork opaque. Delegated to source-analytics
  (`viz.connectivity_plots`) via a subprocess (`circos.py` +
  `_circos_render_worker.py`), reading the per-subject edge CSV from the analytics
  working tree (`<paradigm>/roi_connectivity/data/roi_connectivity_edges.csv`)
  for the chords. Rendered for each metric in `circos_metrics` (YAML list;
  default imag_coherence) × contrast × band with a significant subnetwork, and
  shown alongside (not instead of) the NBS component heatmap. In the gallery:
  **metric sub-tabs → band rows → small click-to-enlarge thumbnails**
  (filenames `circos__<metric>__<band>__<contrast>.png` so the JS groups them;
  captions use `contrast_labels`). The worker picks the atlas `roi_categories.yaml`
  whose ROI names match the edges (the atlas ships several granularities; only
  the 32-ROI one matches). Needs `contrast_pairs` (name + group_a/group_b) from
  the study config (`contrasts:` or `hypotheses:` ±1 weights).
- Both workers read the **native hypothesis schema** (`hypothesis`, `spatial`,
  `dv`, `effect_size`, `stat`, `q_value`); source-analytics dropped the legacy
  alias columns on 2026-07-06, and the workers map any remaining aliases to the
  native names before filtering. The mosaic worker facets aperiodic tables on
  `dv` when `band` is the `NA` placeholder.

## Summaries: generated digest, not the verbatim report

`ANALYSIS_SUMMARY.md` is a full stats report, not a summary — it is **not**
embedded. Instead `summarize.py` derives a concise "significant results by
contrast" digest from the module's effect-size table (per-contrast chips with
direction arrows, FDR q<0.05). The per-contrast category axis is band/freq_pair,
falling back to `dv` when band is the aperiodic `NA` placeholder.

The digest is **organized into tier sections** when the YAML gives each contrast
a `group:` (e.g. Disease effect / Treatment rescue / Normalization to WT / Route
& dose). Sections follow the group's first-seen YAML order; contrasts without a
group fall into "Other". No groups → flat per-contrast list. Threaded the same
way as `contrast_labels` (cli → BuildConfig → manifest → summarize).

## Presentation

- **Analysis pages are tabbed**: Summary / Figures / Tables (summary leads).
- **Figures display as full-width titled rows** (`renderFigureRows`) for QC,
  subject, and analysis figures — readable inline, click to zoom. Titles derived
  from filenames via the `ACRONYMS` map (hyphens preserved, e.g. HD-ICV).
- **Localization**: nav nested per source (section-title like Analytics); QC page
  tabbed (Figures/Metrics/Report) with an outlier summary lead and highlighted
  outlier rows; subject browser grouped by treatment group with outlier badges.

## QC

QC is generated by `source-localization` (`study qc <config> --output-dir <dir>`,
which we added) into `<pipeline>/qc/{figures,qc_metrics.csv,qc_report.html}` —
the exact layout the QC scanner reads. The lightbox re-derives per-subject
outlier flags from the metrics (`qc_meta.py`, mirroring `detect_outliers`: 4
metrics, sample-std z>2) so badges match the report. QC report copied per source
slug (`qc/<slug>/qc_report.html`) to avoid ROI/Shell collision. QC plots are
landscape and group-ordered (in `source-localization` `study/qc.py`).

## Open items

- `roi_aperiodic` brain mosaic errors and falls back to a heatmap — to fix.
