"""Brain-mosaic render worker — executed by the *source-analytics* interpreter.

This file is NOT imported by source-lightbox. It is run as a subprocess with the
source-analytics venv's Python (which has source_analytics, pandas, nibabel, and
the bundled Allen atlas), because rendering anatomy-aware ROI mosaics needs that
whole stack. source-lightbox stays lightweight and shells out to it.

Usage:  <sa-python> _brain_render_worker.py '<json-args>'
Prints a JSON list of written PNG paths on the last stdout line.

json-args keys:
  csv           posthoc ROI table (contrast, roi, band, hedges_g, p_value, ...)
  categories    path to a YAML with a top-level `roi_categories:` mapping
  out_dir       output directory for the mosaics
  analysis_name ANALYSIS_CMAPS key (e.g. "psd", "aperiodic")
  contrasts     list of contrast names to keep (None = all)
  power_type    keep only this power_type when the column exists (None = all)
  alpha         FDR threshold for the "significant" row (default 0.05)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    args = json.loads(sys.argv[1])

    import pandas as pd
    import yaml
    from source_analytics.viz.brain_roi import render_posthoc_mosaics

    df = pd.read_csv(args["csv"])
    categories = yaml.safe_load(open(args["categories"]))["roi_categories"]
    out_dir = Path(args["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    alpha = float(args.get("alpha", 0.05))

    # Filter: chosen power_type and the study's contrasts.
    power_type = args.get("power_type")
    if power_type and "power_type" in df.columns:
        df = df[df["power_type"] == power_type]
    contrasts = args.get("contrasts")
    if contrasts:
        df = df[df["contrast"].isin(contrasts)]

    # Significant bands only: keep (contrast, band) cells with >=1 significant ROI.
    if "significant" in df.columns:
        sig_mask = df["significant"].astype(str).str.upper().isin(["TRUE", "1", "YES", "T"])
    elif "q_value" in df.columns:
        sig_mask = pd.to_numeric(df["q_value"], errors="coerce") < alpha
    else:
        sig_mask = pd.Series(True, index=df.index)
    keep = set(zip(df.loc[sig_mask, "contrast"], df.loc[sig_mask, "band"]))
    if not keep:
        print(json.dumps([]))
        return
    df = df[[(c, b) in keep for c, b in zip(df["contrast"], df["band"])]]

    # Readable contrast labels drive mosaic titles + filenames (after filtering,
    # which used the raw names).
    labels = args.get("labels")
    if labels:
        df = df.copy()
        df["contrast"] = df["contrast"].map(lambda c: labels.get(c, c))

    filtered = out_dir / "_filtered.csv"
    df.to_csv(filtered, index=False)
    facet_cols = [c for c in ("contrast", "band", "power_type") if c in df.columns]
    paths = render_posthoc_mosaics(
        filtered,
        categories,
        out_dir,
        analysis_name=args.get("analysis_name", "psd"),
        effect_col="hedges_g",
        roi_col="roi",
        p_col="p_value",
        facet_cols=facet_cols,
        colorbar_label="Hedges' g",
        alpha=alpha,
    )
    try:
        filtered.unlink()
    except OSError:
        pass

    print(json.dumps([str(p) for p in paths]))


if __name__ == "__main__":
    main()
