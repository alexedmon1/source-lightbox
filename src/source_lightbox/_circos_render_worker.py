"""Connectivity circos render worker — executed by the *source-analytics* interpreter.

Like ``_brain_render_worker.py``, this runs under the source-analytics venv (which
has ``source_analytics.viz.connectivity_plots`` + the Allen atlas roi_categories +
pandas). For each significant ``(contrast, band)`` it draws a significance circos:
32 ROIs grouped/colored by their 10 anatomical regions, chords showing the group
difference (direction + magnitude), with FDR-significant region pairs opaque.

Usage:  <sa-python> _circos_render_worker.py '<json-args>'
Prints a JSON list of written PNG paths on the last stdout line.

json-args keys:
  edges_csv     roi_connectivity edge table (subject × band × roi1/roi2 × metrics)
  posthoc_csv   region-pair posthoc table (contrast, band, region_pair, q_value, ...)
  out_dir       output directory
  contrasts     list of {name, group_a, group_b}
  labels        {contrast_name: readable label}
  metric        connectivity metric column (default imag_coherence)
  atlas         atlas name for roi_categories (default "allen")
  alpha         FDR threshold (default 0.05)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    args = json.loads(sys.argv[1])

    import glob

    import pandas as pd
    import yaml
    from source_analytics.atlas import find_atlas_dir
    from source_analytics.viz.connectivity_plots import (
        build_roi_matrix,
        build_significance_matrix,
        plot_significance_circos,
    )

    edges = pd.read_csv(args["edges_csv"])
    posthoc = pd.read_csv(args["posthoc_csv"])
    edge_rois = set(edges["roi1"]) | set(edges["roi2"])

    # Pick the roi_categories.yaml under the atlas whose ROI names actually match
    # this study's edges (the atlas ships several at different granularities).
    roi_categories = None
    best_overlap = -1
    atlas_root = Path(find_atlas_dir(args.get("atlas", "allen")))
    for path in glob.glob(str(atlas_root / "**" / "roi_categories.yaml"), recursive=True):
        try:
            data = yaml.safe_load(open(path))
            rc = data.get("roi_categories", data) if isinstance(data, dict) else data
            overlap = len({r for v in rc.values() for r in v} & edge_rois)
        except Exception:  # noqa: BLE001
            continue
        if overlap > best_overlap:
            best_overlap, roi_categories = overlap, rc
    if not roi_categories:
        print(json.dumps([]))
        return
    metrics = args.get("metrics") or [args.get("metric", "imag_coherence")]
    alpha = float(args.get("alpha", 0.05))
    labels = args.get("labels") or {}
    out_dir = Path(args["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    # Gated post-hoc: region-pair circos are only meaningful where the global
    # (omnibus) connectivity test is significant. Build the global-significant set.
    global_sig = set()
    global_csv = args.get("global_csv")
    if global_csv and Path(global_csv).exists():
        g = pd.read_csv(global_csv)
        gq = pd.to_numeric(g.get("q_value"), errors="coerce")
        for _, row in g[gq < alpha].iterrows():
            global_sig.add((row.get("contrast"), row.get("band"), row.get("metric")))

    written = []
    for metric in metrics:
        if metric not in edges.columns:
            continue
        ph = posthoc[posthoc["metric"] == metric] if "metric" in posthoc.columns else posthoc
        ph = ph.copy()
        ph["_sig"] = pd.to_numeric(ph.get("q_value"), errors="coerce") < alpha

        for con in args["contrasts"]:
            cname, ga, gb = con["name"], con.get("group_a"), con.get("group_b")
            if not ga or not gb:
                continue
            csub = ph[ph["contrast"] == cname]
            sig_bands = sorted(csub.loc[csub["_sig"], "band"].dropna().unique())
            for band in sig_bands:
                # Gate on global significance when the global table is available.
                if global_sig and (cname, band, metric) not in global_sig:
                    continue
                band_df = edges[edges["band"] == band]
                try:
                    mat_a, rl, rn, rs = build_roi_matrix(band_df, roi_categories, metric, group=ga)
                    mat_b, *_ = build_roi_matrix(band_df, roi_categories, metric, group=gb)
                    sig = build_significance_matrix(
                        posthoc, rl, rn, rs, band, metric, p_col="q_value", alpha=alpha
                    )
                    if sig is None or not sig.any():
                        continue
                    label = labels.get(cname, cname)
                    # `__`-delimited so the gallery can group by metric / band /
                    # contrast (each field may itself contain single underscores).
                    out = out_dir / f"circos__{metric}__{band.replace(' ', '_')}__{cname}.png"
                    plot_significance_circos(
                        mat_a, mat_b, rl, rn, rs, sig, out,
                        group_labels=(ga, gb), title=f"{label} — {band} ({metric})",
                    )
                    written.append(str(out))
                except Exception as exc:  # noqa: BLE001
                    sys.stderr.write(f"circos fail {metric}/{cname}/{band}: {exc}\n")

    print(json.dumps(written))


if __name__ == "__main__":
    main()
