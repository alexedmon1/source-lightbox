# neuro-lightbox — plan

**Status: plan only. Nothing here is implemented.** To be worked in its own
session. This file moves into the neuro-lightbox repository once that exists
(Phase 0).

**Decision (author, revised 2026-10-04): neuro-lightbox is a separate project,
derived from source-lightbox, for MRI.** The lightbox itself is already built;
from here each tool changes only as its own modality needs. source-lightbox
stays as it is, for EEG (source-analytics); neuro-lightbox serves MRI
(neurofaune). No rename of source-lightbox, no shared core, no profile
interface, no deprecation shim.

*History:* the 2026-10-02 version of this plan chose to rename source-lightbox
and generalise it in one repository with EEG/MRI profiles. Superseded on
2026-10-04 by the decision above. The reporting defects that the shared code
carries (§2) are recorded for source-lightbox separately, as to-do items in its
`DESIGN_NOTES.md` ("Reporting defects found 2026-10-02"), to be fixed there
later; neuro-lightbox fixes them in its own copy (Phase 2).

The goal: **a static, browsable gallery of a study's MRI results, rebuilt from
its analysis outputs by one command, that reports results honestly** — every
test with its magnitude, direction, uncertainty and correction, null results
included — and says what produced each number. It opens straight from disk:
the source-lightbox gallery it derives from already works from `file://` with
no server (checked 2026-10-04 in headless Firefox: no network requests, the
data is inlined in `index.html`); a web server is only for sharing it.

---

## 1. Principles (author, 2026-10-02)

1. **Built for the analysis package, not for a workflow tool.** neuro-lightbox
   presents what **neurofaune** produces (and study-side analyses that write the
   same output format). It has **no dependency on DUET**, nor on any study's own
   records, and no DUET concept shapes its design or its schema. DUET — or a
   study, or anything else — can *use* it by pointing it at a results tree;
   neuro-lightbox does not know who is calling.
2. **The package's outputs are for everyone, not for the lightbox.** What
   neurofaune writes (and, separately, what source-analytics writes) must be
   usable by anyone — a pandas or R script, a spreadsheet, another dashboard, a
   journal supplement — with no lightbox installed. So the **output format
   belongs to the analysis package**: open formats, a documented and versioned
   specification, self-describing tables, provenance included (§4).
   neuro-lightbox is **one reader** of it. Two consequences:
   - nothing a producer writes may exist only to steer the lightbox (e.g.
     source-lightbox's filename-based table priority, `_table_priority`,
     `render.py:611`, becomes a declared table role anyone can read);
   - the lightbox is never the only place a number or its meaning can be found.

---

## 2. What the feasibility test showed (2026-10-02)

Cuprizone H1c (a study-side analysis: 12 tests × 4 measures × grey-matter
summaries, plus 11,808 ROI rows) was exported into source-lightbox's layout and
built with **no code change**. The export lived in the study's gitignored
`scratch/` and will not survive, so the mapping is recorded here:

| source-lightbox column / name | filled from (study table) |
|---|---|
| `hypothesis` | `test` + `__` + `level` (e.g. `change_group__p60_to_p120`) |
| `band` (the heatmap column axis) | `measure` (ReHo, fALFF, ReHo_zscore, fALFF_zscore, FC_*) |
| `dv` (facet) | `variable` (GM_all, GM_L, GM_R, FC_homotopic, …) |
| `spatial` (ROI table only) | `variable` (SIGMA region name) |
| `effect_size` | `d` (Cohen's d, **not** Hedges g) |
| `stat`, `p_value` | `t`, `p` (**uncorrected**, by the study's decision) |
| file `h1c_effect_size_summary.csv` | `summary_effects.csv` (named so the filename priority makes it the overview) |
| file `h1c_posthoc_roi.csv` | `roi_effects.csv` (priority 10, capped at 500 rows, full CSV linked) |
| `provenance.json` | a stand-in built from the study's run ledger — in the target design neurofaune writes it (§4) |
| `contrasts:` in study.yaml | 12 entries with `label`, `group` (tier) and `role` (the study's pre-specified test `confirmatory`, the rest `exploratory`) |

**Worked:** the overview heatmap (test × measure, d per cell, ★ where p < 0.05)
shows every test *including nulls with their magnitude*, and its numbers match
the study's own tables (ReHo group change p60→p120 d = 1.30; control change
−1.46; p60 gap −1.19). Tier sections, the confirmatory badge, nulls listed in
place, sortable tables with the full CSV linked, and the provenance strip all
worked; the gallery opens from disk with no server.

**Wrong** (items 1–7 are also recorded as source-lightbox to-dos):

1. **The digest says "FDR q < 0.05"** when the table carries only an uncorrected
   `p` (`_sig_note`, `summarize.py:457`).
2. **Effect sizes are labelled "g" / "Hedges g"** whatever they are
   (`_EFFECT_COLS`, `summarize.py:35`; the heatmap colour bar).
3. **Direction wording assumes two groups**: "▲/▼ = the first-listed group of
   each pair is higher" on one-sample (within-group change) tests.
4. **Nulls without magnitude**: "No significant effects" (`_null_item`,
   `summarize.py:1113`).
5. **No CIs in the digest** (only decoding tables' `ci_*`).
6. **The digest leads with a significance count.**
7. Heatmap rows interleaved by window rather than in the configured order.
8. **Provenance fields are EEG-shaped** (`_trim_provenance`, `manifest.py:25`).
9. **Every analysis lands in "Other"** without a source-analytics interpreter
   (`_read_analysis_meta`, `builder.py:219`).
10. **No place for decision criteria**: an analysis that defines them (H1c writes
    a `verdict.json`) has nowhere to show them.

Items 1–3 and 8 are also signs that the *information* was missing from the
files: nothing in them said the p was uncorrected, the effect was Cohen's d, or
the test was one-sample. The fix is in the output specification (§4) as much as
in the lightbox.

## 3. Starting point: what to keep from source-lightbox, what to strip

**Keep** (the built lightbox): the static build (manifest inlined, opens from
disk, optional nginx/Apache deploy); `build` / `serve` / `info`; Summary /
Figures / Tables pages; sortable tables with full-CSV links; the
column-driven renderer registry; tier sections, role badges, gating notes; the
provenance strip; dark/light theme, search, lazy thumbnails; tests.

**Strip or replace** (EEG-specific; none of it is needed for MRI):

| Place | EEG assumption | In neuro-lightbox |
|---|---|---|
| `render.py:34` `BAND_ORDER`, `summarize.py:93` `_GRAPH_BAND_ORDER` | frequency bands as the category axis | measures (configured order) |
| `render.py` `REGISTRY` renderers' `matches()` | source-analytics column names | the output spec's columns (§4) |
| `render.py:39` `_SIG_PVAL_COLS`, `_is_sig` | fixed significance precedence | read `p_kind` / declared correction |
| `render.py:611` `_table_priority` | table roles from filenames | declared table roles (§4) |
| `summarize.py` builders (`_EFFECT_COLS`, comparison, FCD, graph, NBS, cluster, ROI-posthoc, `_sig_note`) | g labels, band chips, FDR wording, EEG modules | MRI digest builders (Phase 2–3) |
| `brain_mosaic.py`, `_brain_render_worker.py`, `circos.py`, `_circos_render_worker.py`, `_worker_atlas.py` | Allen atlas via source-analytics | remove; atlas figures later via neurofaune (Phase 3, optional) |
| `scanner.py` `LocalizationScanner`, `qc_meta.py`, `cli.py` `localiz*` | inputs side = source localization | link to neurofaune's preprocessing QC index |
| `manifest.py:25` `_trim_provenance` | source-analytics provenance fields | the spec's provenance (§4) |
| `builder.py:219` `_read_analysis_meta` | grouping from source-analytics | `analysis.json` / config |
| `config.py:18` `RETIRED_ANALYSES` | retired EEG vertex modules | remove |
| `static/js/app.js` (2,128 lines: "band" ×57, "sensor" ×43, "localiz" ×40, `ACRONYMS`, Localization / Source-vs-Sensor nav) | EEG vocabulary | MRI vocabulary |

## 4. The output specification — owned by neurofaune

A documented, versioned specification of **what neurofaune writes for an
analysis**, so that any reader can use it; neuro-lightbox is one reader.
source-analytics can adopt the same principles for its own outputs
independently (its tables + `provenance.json` are already close) — that is its
own decision and not a dependency of this plan.

**Requirements**

- **Open formats only:** tables as CSV (or TSV), metadata as JSON, maps as NIfTI
  — no pickles, no `.npz` as the only copy of a result.
- **Self-describing:** every table has a column dictionary — a BIDS-style JSON
  sidecar beside it (`<table>.json`: per column, a description, units, levels),
  the convention BIDS uses for tabular files and close to neurofaune's existing
  BIDS-derivatives habits.
- **Complete:** every test that was run has its row, significant or not, with
  its effect and uncertainty. Tables are never truncated.
- **Explicit, not inferred:** the correction (`p_kind`), the effect measure, the
  test kind (direction semantics), units, and each table's role are written.
- **Provenance included:** which package, version and commit; when; on what
  inputs; whether the run finished — from `neurofaune.provenance`, the reader its
  derivative `GeneratedBy` sidecars already use.
- **Versioned:** every `analysis.json` carries `spec_version` (semver).
- **Workflow-neutral:** no field belongs to a workflow tool. A generic
  `references: [{label, value}]` list carries anything a study or tool wants
  attached; producers and readers treat it as opaque.

**Layout** (one folder per analysis):

```
<analysis>/
  analysis.json          what this analysis is
  provenance.json        what produced it
  tables/<name>.csv      results, one row per test / element
  tables/<name>.json     column dictionary for that table
  maps/…                 optional NIfTI maps, each listed in analysis.json
  figures/…              optional, never the only copy of a result
```

**Table columns** (the subset that applies; a reader reports a missing field as
missing, never guesses): `contrast`, `category` (measure), `facet` (variable),
`element` (ROI / cluster / edge); `effect_size`, `effect_measure` (`d`, `g`,
`beta`, `r`, …), `ci_low`, `ci_high`, `effect_selected` (computed on units
selected for significance — inflated); `stat`, `stat_name`, `df`; `p_value` with
`p_kind` (`uncorrected`, `fdr`, `fwe`, `perm`) or explicit `q_value` /
`p_corrected`; `test_kind` (`two_group`, `one_sample`, `regression`, …),
`group_a`, `group_b`, `n_a`, `n_b` (or `n`); `mean_a`, `mean_b`.

**`analysis.json`:** `spec_version`, title, description, analysis type, `role`
(confirmatory / exploratory / descriptive / diagnostic), the **correction
statement** and threshold, the effect measure, the design (groups, n per
group), **decision criteria and their outcome** where the analysis defines them,
each table's **role** (headline / detail / per-element), the maps and figures,
and `references`.

**`provenance.json`:** `tools: [{name, version, commit}]`,
`run: {id, start, end, status}`, `inputs`, `subjects: {n, groups}`, `caveats`.

## 5. Target architecture

- A new repository and package: **`neuro-lightbox`** (package `neuro_lightbox`,
  CLI `neuro-lightbox`), derived from source-lightbox at `f667d7f`, with its
  README saying so.
- Reads spec-conformant analysis folders (§4) written by neurofaune or by a
  study's own analyses; builds one static gallery; opens from disk.
- Inputs side: a link to neurofaune's preprocessing QC index (`qc/index.html`).
- Atlas figures, if added, are delegated by subprocess to neurofaune's
  environment, so the gallery stays lightweight.
- **No DUET, no study-specific code, no EEG code.**

## 6. The work, in phases

Each phase ends with its acceptance check. Phases S and 0 can run in parallel.

### Phase S — the output specification (in neurofaune)
- Write the specification (§4): document, JSON Schemas, conformance checker.
- Each neurofaune analysis (TBSS, voxelwise, ROI extraction, covariance
  networks, connectomes, …) writes its spec folder. The `tbss-reporting`
  branch's `tests.csv` / `clusters.csv` are the first candidates. neurofaune's
  older `reporting/` registry becomes a reader of the spec, or retires.
- A small writer helper in neurofaune, so a study's own analyses can write the
  same folders.
- **Accept:** neurofaune's test suite validates its outputs against the schemas;
  a **"no lightbox" test** — a plain pandas script that knows only the spec reads
  every table, its column meanings, the correction and the provenance.

### Phase 0 — create the project
- New repository `neuro-lightbox` from source-lightbox. Recommended: a copy
  **with history** (`git clone`, then rename and point at a new remote), so
  blame and provenance survive; a GitHub fork would tie it to upstream instead.
- Rename package and CLI; README "derived from source-lightbox @ f667d7f"; move
  this plan in.

### Phase 1 — strip EEG, read the spec
- Remove or replace everything in §3's strip table; MRI vocabulary in the app.
- A scanner for spec folders (§4); grouping from `analysis.json`.
- **Accept:** a purity test fails if the code mentions bands, Allen,
  source-analytics, localization, DUET or any study; the H1c and TBSS fixtures
  build.

### Phase 2 — contract-correct reporting
1. **Correction stated from the data**, never defaulted ("uncorrected p < 0.05";
   "not recorded" when a tree does not say).
2. **Effect-size label from `effect_measure`** in digest chips, colour bars,
   tables.
3. **Direction by `test_kind`**: two-group "A > B" with names; one-sample
   "increase / decrease"; regression "positive / negative".
4. **Nulls with magnitude**: every contrast shows its primary effect and CI,
   significant or not; significant ones lead.
5. **CIs everywhere they exist**, in text and as a cue in heatmaps.
6. **Decision-criteria panel** from `analysis.json`, with any `references`.
7. **No significance-count headline**: the headline table's / confirmatory
   test's effect, CI, p and correction first; counts after, with their threshold.
8. **Selected effects flagged** (`effect_selected`) as inflated.
9. **Order follows the config / `analysis.json`.**
10. **Absence visible**: declared analyses without tables show "no result"; a
    failed / incomplete run shows on the page; display caps say "showing 500 of
    11,808" and link the full file.
11. **Generic provenance strip**, "not recorded" when absent.
12. **Escape every name** reaching HTML.
13. Units from the column dictionaries.
- **Accept:** contract tests on the fixtures — every contrast appears with
  effect, CI (where present), direction and a correction statement matching its
  `p_kind`.

### Phase 3 — MRI renderers
- Test × measure effect heatmap with a CI cue; **per-cohort consistency**
  (effect per cohort/batch) where a design has cohorts; ROI effect tables with
  atlas names; TBSS tests and cluster tables (voxels, mm³, peak, named regions);
  NBS components with signed edges; network distance against its permutation
  null.
- Later, optional: atlas figures (SIGMA ROI mosaics, skeleton montages) via
  neurofaune.
- **Accept:** the neurofaune TBSS read-out and the H1c fixture build with none of
  §2's defects.

### Phase 4 — adoption in the cuprizone study (study-side)
- The study's own analyses (`h1_*`, study-specific by design) write the same spec
  folders through neurofaune's writer helper. Whatever the study keeps in its own
  records (DUET findings, its run ledger) may go into `references` and
  provenance; neuro-lightbox does not know about them.
- A gallery config; build into the study's report folder.

## 7. Testing

- Spec conformance and the "no lightbox" read test (Phase S).
- Purity test (Phase 1).
- Contract tests (Phase 2).
- Fixtures: the neurofaune TBSS read-out and cuprizone H1c (Phases 1–3).
- source-lightbox's existing tests, adapted, as the starting suite.

## 8. Open decisions (author)

1. The new repository: copy with history (recommended) or a fresh start; local
   only or also on GitHub.
2. Where the output specification lives: neurofaune's docs (simplest now that
   neurofaune is the only producer neuro-lightbox reads), or a small standalone
   spec that source-analytics could adopt too.
3. Whether studies commit the built gallery or rebuild it from committed tables
   (the preprocessing QC index does the latter).
4. The reporting contract (magnitude + direction + extent + location + nulls,
   currently in the cuprizone study's `analyses/REPORTING.md`): make it part of
   the output specification, so producers meet it and readers can check it.

## 9. Related

- source-lightbox `DESIGN_NOTES.md` → "Reporting defects found 2026-10-02": the
  shared defects, as to-dos for the EEG tool.
- neurofaune branch `tbss-reporting` (`67c60fd`, validated against the cuprizone
  H1h output; HTML escaping still to fix; not merged): the first neurofaune
  analysis producing test-level tables of the kind §4 specifies.
- neurofaune's own `reporting/` registry + `index.html` (older; headline is a
  significance count) — becomes a reader of the spec, or retires.
