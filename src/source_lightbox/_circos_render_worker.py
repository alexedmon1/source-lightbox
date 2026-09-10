"""Connectivity circos render worker — executed by the *source-analytics* interpreter.

Like ``_brain_render_worker.py``, this runs under the source-analytics venv (which
has ``source_analytics.viz.connectivity_plots`` + the Allen atlas roi_categories +
pandas). For each hypothesis × (band, metric) with an FDR-significant NBS
subnetwork it draws a significance circos: ROIs grouped/colored by anatomical
region, chords showing the group difference (direction + magnitude), with the
edges of the significant subnetwork(s) opaque and everything else ghosted.

The inferential source is ``<module>_subnetwork_edges.csv`` — the per-edge
membership of each NBS component that source-analytics writes next to
``<module>_hypotheses.csv`` — not a per-edge posthoc table (those were retired
from roi_connectivity in 2026-06).

Usage:  <sa-python> _circos_render_worker.py '<json-args>'
Prints a JSON list of written PNG paths on the last stdout line.

json-args keys:
  edges_csv        roi_connectivity edge table (subject × band × roi1/roi2 × metrics)
  subnetwork_csv   <module>_subnetwork_edges.csv (hypothesis, band, dv, component_p,
                   significant, roi_i, roi_j, stat)
  out_dir          output directory
  contrasts        list of {name, group_a, group_b}
  labels           {hypothesis_name: readable label}
  metrics          connectivity metric columns to draw (default [imag_coherence])
  categories       the study's category map (a mapping or YAML path); null = the
                   atlas's own file, then a best-overlap guess (_worker_atlas.py)
  atlas            the study's atlas (pipeline.atlas), used when categories is null
  alpha            component-p threshold (default 0.05)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))   # _worker_atlas sits beside this script
from _worker_atlas import members, resolve_categories  # noqa: E402


def main() -> None:
    args = json.loads(sys.argv[1])

    import numpy as np
    import pandas as pd
    from source_analytics.viz.connectivity_plots import (
        build_roi_matrix,
        plot_significance_circos,
    )

    edges = pd.read_csv(args["edges_csv"])
    sub = pd.read_csv(args["subnetwork_csv"])
    required = {"hypothesis", "band", "dv", "roi_i", "roi_j"}
    if not required <= set(sub.columns):
        sys.stderr.write(f"subnetwork table lacks {sorted(required - set(sub.columns))}\n")
        print(json.dumps([]))
        return
    alpha = float(args.get("alpha", 0.05))
    if "significant" in sub.columns:
        sig_rows = sub["significant"].astype(str).str.upper().isin(["TRUE", "1", "T", "YES"])
    else:
        sig_rows = pd.to_numeric(sub.get("component_p"), errors="coerce") < alpha
    sub = sub[sig_rows]
    if sub.empty:
        print(json.dumps([]))
        return

    edge_rois = set(edges["roi1"]) | set(edges["roi2"])
    roi_categories, source = resolve_categories(args.get("categories"), args.get("atlas"), edge_rois)
    if not roi_categories:
        sys.stderr.write("no roi_categories fit the edge ROIs (none passed, and no atlas "
                         "category file matches)\n")
        print(json.dumps([]))
        return
    missing = edge_rois - members(roi_categories)
    if missing:
        # build_roi_matrix keeps only categorised ROIs, so these would vanish silently.
        sys.stderr.write(f"roi_categories from {source} leave {len(missing)} edge ROIs out of "
                         f"the circos: {', '.join(sorted(missing))}\n")

    metrics = args.get("metrics") or ["imag_coherence"]
    labels = args.get("labels") or {}
    out_dir = Path(args["out_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    written = []
    for metric in metrics:
        if metric not in edges.columns:
            continue
        msub = sub[sub["dv"].astype(str) == metric]
        if msub.empty:
            continue
        for con in args["contrasts"]:
            cname, ga, gb = con["name"], con.get("group_a"), con.get("group_b")
            if not ga or not gb:
                continue
            csub = msub[msub["hypothesis"].astype(str) == cname]
            for band in sorted(csub["band"].dropna().astype(str).unique()):
                bsub = csub[csub["band"].astype(str) == band]
                band_df = edges[edges["band"] == band]
                if band_df.empty:
                    continue
                try:
                    mat_a, rl, rn, rs = build_roi_matrix(band_df, roi_categories, metric, group=ga)
                    mat_b, *_ = build_roi_matrix(band_df, roi_categories, metric, group=gb)
                    index = {r: i for i, r in enumerate(rl)}
                    sig = np.zeros((len(rl), len(rl)), dtype=bool)
                    for a, b in zip(bsub["roi_i"], bsub["roi_j"]):
                        i, j = index.get(a), index.get(b)
                        if i is None or j is None:
                            continue
                        sig[i, j] = sig[j, i] = True
                    if not sig.any():
                        continue
                    label = labels.get(cname, cname)
                    # `__`-delimited so the gallery can group by metric / band /
                    # contrast (each field may itself contain single underscores).
                    out = out_dir / f"circos__{metric}__{band.replace(' ', '_')}__{cname}.png"
                    kwargs = dict(group_labels=(ga, gb),
                                  title=f"{label} — {band} ({metric}); NBS subnetwork")
                    try:
                        plot_significance_circos(
                            mat_a, mat_b, rl, rn, rs, sig, out,
                            sig_label="edges of an FDR-significant NBS subnetwork", **kwargs)
                    except TypeError:  # older source-analytics without sig_label
                        plot_significance_circos(mat_a, mat_b, rl, rn, rs, sig, out, **kwargs)
                    written.append(str(out))
                except Exception as exc:  # noqa: BLE001
                    sys.stderr.write(f"circos fail {metric}/{cname}/{band}: {exc}\n")

    print(json.dumps(written))


if __name__ == "__main__":
    main()
