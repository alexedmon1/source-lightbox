"""Brain-mosaic render worker — executed by the *source-analytics* interpreter.

This file is NOT imported by source-lightbox. It is run as a subprocess with the
source-analytics venv's Python (which has source_analytics, pandas, nibabel, and
the bundled Allen atlas), because rendering anatomy-aware ROI mosaics needs that
whole stack. source-lightbox stays lightweight and shells out to it.

Usage:  <sa-python> _brain_render_worker.py '<json-args>'
Prints a JSON list of written PNG paths on the last stdout line.

json-args keys:
  csv           posthoc ROI table in the native hypothesis schema
                (hypothesis, spatial, band, dv, effect_size, p_value, q_value,
                significant). Legacy alias columns (contrast, roi, power_type,
                hedges_g, p_fdr) are accepted and mapped to the native names.
  categories    the study's category map: a mapping, a path to a YAML with a
                top-level `roi_categories:`, or null to use the atlas's own file
                (then a best-overlap guess). See _worker_atlas.py.
  out_dir       output directory for the mosaics
  analysis_name ANALYSIS_CMAPS key (e.g. "psd", "aperiodic")
  contrasts     list of hypothesis names to keep (None = all)
  power_type    preferred `dv` when the table's dv is a power type (None = all)
  alpha         FDR threshold for the "significant" row (default 0.05)
  atlas         the study's atlas (pipeline.atlas): its own categories when none are
                passed, and -- with a source-analytics that has resolve_atlas -- its
                own label volume for the mosaics (default: allen32)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # _worker_atlas sits beside this script
from _worker_atlas import members, mosaic_atlas_kwargs, resolve_categories  # noqa: E402

# Legacy hypothesis-CSV alias -> native column (mirrors render._ALIAS_TO_NATIVE).
_ALIAS_TO_NATIVE = {
    "contrast": "hypothesis",
    "roi": "spatial",
    "power_type": "dv",
    "hedges_g": "effect_size",
    "p_fdr": "q_value",
    "t": "stat",
    "t_ratio": "stat",
}


def _to_native(df):
    """Fill missing native columns from legacy aliases; drop the aliases."""
    for alias, native in _ALIAS_TO_NATIVE.items():
        if alias in df.columns:
            if native not in df.columns:
                df[native] = df[alias]
            df = df.drop(columns=[alias])
    return df


def main() -> None:
    args = json.loads(sys.argv[1])

    import pandas as pd
    from source_analytics.viz.brain_roi import render_posthoc_mosaics

    df = _to_native(pd.read_csv(args["csv"]))
    for col in ("hypothesis", "spatial", "effect_size"):
        if col not in df.columns:
            sys.stderr.write(f"posthoc table lacks a '{col}' column: {list(df.columns)}\n")
            print(json.dumps([]))
            return

    atlas = args.get("atlas")
    table_rois = set(df["spatial"].dropna().astype(str))
    categories, source = resolve_categories(args.get("categories"), atlas, table_rois)
    if not categories:
        sys.stderr.write("no roi_categories fit the table's ROIs (none passed, and no atlas "
                         "category file matches)\n")
        print(json.dumps([]))
        return
    missing = table_rois - members(categories)
    if missing and source == "a best-overlap guess":
        sys.stderr.write(f"roi_categories from {source} leave {len(missing)} of the table's "
                         f"ROIs uncategorised: {', '.join(sorted(missing))}\n")
    out_dir = Path(args["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    alpha = float(args.get("alpha", 0.05))

    contrasts = args.get("contrasts")
    if contrasts:
        df = df[df["hypothesis"].isin(contrasts)]

    # Category axis: spectral tables facet on band; aperiodic tables carry the
    # `NA` band placeholder and facet on dv (exponent/offset) instead.
    bands = df["band"].dropna().astype(str) if "band" in df.columns else pd.Series(dtype=str)
    band_is_real = bool((bands.str.upper() != "NA").any())
    cat_col = "band" if band_is_real else ("dv" if "dv" in df.columns else None)

    # Power-type facet (relative/absolute) lives in `dv` for the spectral tables;
    # keep only the preferred one when the table actually carries it.
    power_type = args.get("power_type")
    if power_type and "dv" in df.columns and cat_col != "dv":
        if (df["dv"].astype(str) == power_type).any():
            df = df[df["dv"].astype(str) == power_type]

    # Significant cells only: keep (hypothesis, category) cells with >=1 significant ROI.
    if "significant" in df.columns:
        sig_mask = df["significant"].astype(str).str.upper().isin(["TRUE", "1", "YES", "T"])
    elif "q_value" in df.columns:
        sig_mask = pd.to_numeric(df["q_value"], errors="coerce") < alpha
    else:
        sig_mask = pd.Series(True, index=df.index)

    if cat_col:
        keep = set(zip(df.loc[sig_mask, "hypothesis"], df.loc[sig_mask, cat_col]))
        if not keep:
            print(json.dumps([]))
            return
        df = df[[(c, b) in keep for c, b in zip(df["hypothesis"], df[cat_col])]]
    else:
        keep_contrasts = set(df.loc[sig_mask, "hypothesis"])
        if not keep_contrasts:
            print(json.dumps([]))
            return
        df = df[df["hypothesis"].isin(keep_contrasts)]

    # Readable contrast labels drive mosaic titles + filenames (after filtering,
    # which used the raw names).
    labels = args.get("labels")
    if labels:
        df = df.copy()
        df["hypothesis"] = df["hypothesis"].map(lambda c: labels.get(c, c))

    filtered = out_dir / "_filtered.csv"
    df.to_csv(filtered, index=False)
    facet_cols = ["hypothesis"]
    if cat_col:
        facet_cols.append(cat_col)
    if "dv" in df.columns and cat_col != "dv" and df["dv"].nunique() > 1:
        facet_cols.append("dv")
    p_col = "p_value" if "p_value" in df.columns else None
    q_col = "q_value" if "q_value" in df.columns else None
    mosaic_kw, warning = mosaic_atlas_kwargs(atlas, render_posthoc_mosaics)
    if warning:
        sys.stderr.write(warning + "\n")
    paths = render_posthoc_mosaics(
        filtered,
        categories,
        out_dir,
        analysis_name=args.get("analysis_name", "psd"),
        effect_col="effect_size",
        roi_col="spatial",
        p_col=p_col or q_col,
        q_col=q_col,
        correction_label="FDR",
        facet_cols=facet_cols,
        colorbar_label="Hedges' g",
        alpha=alpha,
        **mosaic_kw,
    )
    try:
        filtered.unlink()
    except OSError:
        pass

    print(json.dumps([str(p) for p in paths]))


if __name__ == "__main__":
    main()
