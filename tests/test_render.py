"""Tests for the table-driven figure renderers (one overview per module)."""

from pathlib import Path

from source_lightbox.render import (
    ClusterHeatmap,
    EffectSizeHeatmap,
    MvpaHeatmap,
    NbsComponentPlot,
    RoiBandHeatmap,
    RoiGraphMetricHeatmap,
    SummaryHeatmap,
    render_table_figures,
    select_renderer,
)
from source_lightbox.scanner import TableEntry


def _write_csv(path: Path, header: str, rows: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# Renderer selection (column-driven dispatch)
# --------------------------------------------------------------------------- #
def test_select_renderer_dispatch():
    assert select_renderer("contrast,band,hedges_g,significant".split(",")) is EffectSizeHeatmap
    assert select_renderer("contrast,roi,band,hedges_g".split(",")) is RoiBandHeatmap
    assert select_renderer("contrast,band,accuracy,auc,ci_lower,ci_upper".split(",")) is MvpaHeatmap
    assert select_renderer("contrast,band,cluster_stat,p_corrected".split(",")) is ClusterHeatmap
    assert select_renderer("contrast,band,max_abs_hedges_g,n_nominal_sig".split(",")) is SummaryHeatmap
    assert select_renderer("key,component,n_edges,p_corrected".split(",")) is NbsComponentPlot


def test_graph_metric_dispatch():
    # The nodal graph-metric table (t/p_fdr per ROI) -> its own renderer, and it
    # must NOT shadow the NBS table that shares the same module.
    headers = "contrast,band,conn_metric,graph_metric,roi,mean_a,mean_b,t,p,p_fdr".split(",")
    assert select_renderer(headers) is RoiGraphMetricHeatmap
    assert select_renderer("key,component,n_edges,p_corrected".split(",")) is NbsComponentPlot


def _graph_records():
    headers = "contrast,band,conn_metric,graph_metric,roi,t,p,p_fdr".split(",")
    records = []
    for contrast in ("disease_effect", "hd_icv_rescue"):
        for conn in ("imag_coherence", "aec"):
            for gm in ("degree", "clustering", "betweenness"):
                for band in ("Delta", "Low Gamma"):
                    for roi in ("Auditory_L", "Motor_R"):
                        records.append({
                            "contrast": contrast, "band": band, "conn_metric": conn,
                            "graph_metric": gm, "roi": roi, "t": "2.1",
                            "p": "0.03", "p_fdr": "0.02" if roi == "Motor_R" else "0.9",
                        })
    return headers, records


def test_graph_metric_overview_one_per_graph_metric(tmp_path):
    headers, records = _graph_records()
    # Overview collapses to the preferred contrast + connectivity metric, leaving
    # one ROIxband figure per graph metric (degree / clustering / betweenness).
    over = RoiGraphMetricHeatmap.render(records, headers, tmp_path, "roi_network_stats",
                                        dpi=72, overview=True)
    assert len(over) == 3
    assert all(p.exists() for p in over)
    names = " ".join(p.name for p in over)
    assert "degree" in names and "clustering" in names and "betweenness" in names
    assert all("disease_effect" in p.name for p in over)  # preferred contrast


def test_graph_metric_full_spans_contrasts(tmp_path):
    headers, records = _graph_records()
    # Without overview: still one connectivity metric, but every contrast x metric.
    full = RoiGraphMetricHeatmap.render(records, headers, tmp_path, "roi_network_stats",
                                        dpi=72, overview=False)
    assert len(full) == 6  # 2 contrasts x 3 graph metrics


def test_render_network_module_nbs_plus_graph(tmp_path):
    # A roi_network module carries NBS results AND the nodal graph-metric table;
    # both should render (graph metrics alongside the NBS overview).
    base = tmp_path / "tables" / "resting" / "roi_network"
    nbs = _write_csv(
        base / "roi_nbs_results.csv",
        "key,component,n_edges,p_corrected",
        ["disease_effect_Delta_imag_coherence,1,12,0.03"],
    )
    headers, records = _graph_records()
    stats = _write_csv(
        base / "roi_network_stats.csv",
        ",".join(headers),
        [",".join(r[c] for c in headers) for r in records],
    )

    def te(p):
        return TableEntry(src_path=p, source_label="Allen ROI", paradigm="resting",
                          analysis="roi_network", filename=p.name)

    figures = render_table_figures([te(nbs), te(stats)], tmp_path / ".rendered", dpi=72)
    assert {f.analysis for f in figures} == {"roi_network"}
    names = " ".join(f.filename for f in figures)
    assert "nbs" in names  # NBS overview present
    assert "degree" in names and "clustering" in names  # nodal graph maps present


def test_per_vertex_table_not_matched():
    # voxelwise per-vertex stats have hedges_g+band but must NOT become a heatmap.
    headers = "contrast,band,metric,vertex_idx,t,hedges_g,p".split(",")
    assert select_renderer(headers) is None


def test_omnibus_table_not_matched():
    # F/p omnibus tables carry no effect size -> no renderer.
    assert select_renderer("contrast,band,group_F,group_p,roi_F".split(",")) is None


# --------------------------------------------------------------------------- #
# Overview mode yields exactly one figure
# --------------------------------------------------------------------------- #
def test_effect_size_overview_single_figure(tmp_path):
    # Two dv facets present; overview must collapse to one (the preferred).
    headers = "contrast,dv,band,hedges_g,significant".split(",")
    records = [
        {"contrast": "disease_effect", "dv": "relative", "band": "Delta", "hedges_g": "0.6", "significant": "TRUE"},
        {"contrast": "disease_effect", "dv": "relative", "band": "Alpha", "hedges_g": "-0.2", "significant": "FALSE"},
        {"contrast": "disease_effect", "dv": "absolute", "band": "Delta", "hedges_g": "0.1", "significant": "FALSE"},
        {"contrast": "hd_icv_rescue", "dv": "relative", "band": "Alpha", "hedges_g": "0.9", "significant": "TRUE"},
    ]
    out = EffectSizeHeatmap.render(records, headers, tmp_path, "psd_posthoc_global", dpi=72, overview=True)
    assert len(out) == 1
    assert out[0].exists() and "relative" in out[0].name


def test_roi_overview_single_contrast(tmp_path):
    headers = "contrast,roi,band,hedges_g,significant".split(",")
    records = [
        {"contrast": "disease_effect", "roi": "Auditory_L", "band": "Delta", "hedges_g": "0.4", "significant": "FALSE"},
        {"contrast": "disease_effect", "roi": "Motor_R", "band": "Alpha", "hedges_g": "0.7", "significant": "TRUE"},
        {"contrast": "hd_icv_rescue", "roi": "Auditory_L", "band": "Delta", "hedges_g": "-0.1", "significant": "FALSE"},
    ]
    full = RoiBandHeatmap.render(records, headers, tmp_path, "psd_posthoc_roi", dpi=72, overview=False)
    assert len(full) == 2  # one per contrast without overview
    over = RoiBandHeatmap.render(records, headers, tmp_path, "psd_posthoc_roi", dpi=72, overview=True)
    assert len(over) == 1 and "disease" in over[0].name  # prefers disease_effect


# --------------------------------------------------------------------------- #
# Native hypothesis schema (post alias-drop) — migration regression guard.
# After source-analytics dropped the legacy aliases, <module>_hypotheses.csv and
# the hyp-derived posthoc tables carry ONLY native columns (hypothesis/spatial/
# dv/stat/effect_size/q_value). These lock in that the renderers that consume
# those tables still dispatch and render from the native schema alone.
# --------------------------------------------------------------------------- #
def test_native_schema_dispatch():
    # No alias columns present at all.
    assert select_renderer("hypothesis,spatial,band,effect_size,significant".split(",")) is RoiBandHeatmap
    assert select_renderer("hypothesis,dv,band,effect_size,significant".split(",")) is EffectSizeHeatmap


def test_native_roi_band_heatmap_renders(tmp_path):
    headers = "hypothesis,spatial,band,dv,effect_size,significant".split(",")
    records = [
        {"hypothesis": "disease_effect", "spatial": "Auditory_L", "band": "Delta", "dv": "relative", "effect_size": "0.4", "significant": "FALSE"},
        {"hypothesis": "disease_effect", "spatial": "Motor_R", "band": "Alpha", "dv": "relative", "effect_size": "0.7", "significant": "TRUE"},
        {"hypothesis": "hd_icv_rescue", "spatial": "Auditory_L", "band": "Delta", "dv": "relative", "effect_size": "-0.1", "significant": "FALSE"},
    ]
    assert select_renderer(headers) is RoiBandHeatmap
    full = RoiBandHeatmap.render(records, headers, tmp_path, "roi_psd_posthoc_roi", dpi=72, overview=False)
    assert len(full) == 2  # one figure per hypothesis, keyed off native `hypothesis`
    over = RoiBandHeatmap.render(records, headers, tmp_path, "roi_psd_posthoc_roi", dpi=72, overview=True)
    assert len(over) == 1 and over[0].exists() and "disease" in over[0].name


def test_native_effect_size_heatmap_renders(tmp_path):
    headers = "hypothesis,dv,band,effect_size,significant".split(",")
    records = [
        {"hypothesis": "disease_effect", "dv": "relative", "band": "Delta", "effect_size": "0.6", "significant": "TRUE"},
        {"hypothesis": "disease_effect", "dv": "relative", "band": "Alpha", "effect_size": "-0.2", "significant": "FALSE"},
    ]
    assert select_renderer(headers) is EffectSizeHeatmap
    out = EffectSizeHeatmap.render(records, headers, tmp_path, "roi_graph_hypotheses", dpi=72, overview=True)
    assert len(out) == 1 and out[0].exists()


def test_mvpa_overview(tmp_path):
    headers = "contrast,band,accuracy,auc,p_value,ci_lower,ci_upper".split(",")
    records = [
        {"contrast": "disease_effect", "band": "Delta", "accuracy": "0.49", "auc": "0.48",
         "p_value": "0.5", "ci_lower": "0.3", "ci_upper": "0.69"},
        {"contrast": "disease_effect", "band": "Low Gamma", "accuracy": "0.71", "auc": "0.74",
         "p_value": "0.01", "ci_lower": "0.6", "ci_upper": "0.85"},
    ]
    out = MvpaHeatmap.render(records, headers, tmp_path, "mvpa_results", dpi=72, overview=True)
    assert len(out) == 1 and out[0].exists()


def test_cluster_overview(tmp_path):
    headers = "contrast,band,metric,cluster_stat,p_corrected".split(",")
    records = [
        {"contrast": "disease_effect", "band": "Theta", "metric": "relative", "cluster_stat": "-7.1", "p_corrected": "0.04"},
        {"contrast": "disease_effect", "band": "Theta", "metric": "relative", "cluster_stat": "-4.6", "p_corrected": "0.28"},
        {"contrast": "disease_effect", "band": "Alpha", "metric": "absolute", "cluster_stat": "-6.8", "p_corrected": "0.24"},
    ]
    out = ClusterHeatmap.render(records, headers, tmp_path, "cluster_results", dpi=72, overview=True)
    assert len(out) == 1 and out[0].exists()


def test_nbs_plot(tmp_path):
    headers = "key,component,n_edges,p_corrected".split(",")
    records = [
        {"key": "disease_effect_Theta", "component": "1", "n_edges": "10", "p_corrected": "0.22"},
        {"key": "disease_effect_Alpha", "component": "1", "n_edges": "16", "p_corrected": "0.04"},
        {"key": "disease_effect_Alpha", "component": "2", "n_edges": "1", "p_corrected": "0.83"},
    ]
    out = NbsComponentPlot.render(records, headers, tmp_path, "nbs_results", dpi=72, overview=True)
    assert len(out) == 1 and out[0].exists()


# --------------------------------------------------------------------------- #
# render_table_figures: one figure per module, prefers the global summary
# --------------------------------------------------------------------------- #
def test_render_one_per_module_prefers_global(tmp_path):
    base = tmp_path / "tables" / "resting" / "roi_psd"
    # Detailed per-ROI table (lower priority) ...
    roi = _write_csv(
        base / "roi_psd_posthoc_roi.csv",
        "contrast,roi,band,hedges_g,significant",
        ["disease_effect,Motor_R,Delta,0.4,FALSE", "hd_icv_rescue,Motor_R,Delta,0.2,FALSE"],
    )
    # ... and the global summary (higher priority) for the SAME module.
    glob = _write_csv(
        base / "roi_psd_posthoc_global.csv",
        "contrast,dv,band,hedges_g,significant",
        ["disease_effect,relative,Delta,0.6,TRUE", "hd_icv_rescue,relative,Delta,0.1,FALSE"],
    )
    # An unrenderable omnibus table — ignored.
    omni = _write_csv(base / "roi_psd_omnibus.csv", "contrast,group_F,group_p", ["disease_effect,0.2,0.6"])

    def te(p):
        return TableEntry(src_path=p, source_label="Allen ROI", paradigm="resting",
                          analysis="roi_psd", filename=p.name)

    figures = render_table_figures([te(roi), te(glob), te(omni)], tmp_path / ".rendered", dpi=72)
    assert len(figures) == 1  # exactly one overview for the module
    fig = figures[0]
    assert fig.category == "analytics" and fig.analysis == "roi_psd"
    # Chose the global summary, not the per-ROI detail table.
    assert fig.filename.startswith("roi_psd_posthoc_global__")
    assert fig.gallery_rel_path.startswith("analytics/allen_roi/resting/roi_psd/")
    assert Path(fig.src_path).exists()


def test_render_distinct_modules(tmp_path):
    psd = _write_csv(
        tmp_path / "t/resting/roi_psd/roi_psd_posthoc_global.csv",
        "contrast,band,hedges_g,significant",
        ["disease_effect,Delta,0.6,TRUE"],
    )
    conn = _write_csv(
        tmp_path / "t/resting/roi_connectivity/roi_connectivity_global.csv",
        "contrast,metric,band,hedges_g,significant",
        ["disease_effect,coherence,Delta,0.5,TRUE"],
    )
    tables = [
        TableEntry(src_path=psd, source_label="Allen ROI", paradigm="resting",
                   analysis="roi_psd", filename=psd.name),
        TableEntry(src_path=conn, source_label="Allen ROI", paradigm="resting",
                   analysis="roi_connectivity", filename=conn.name),
    ]
    figures = render_table_figures(tables, tmp_path / ".rendered", dpi=72)
    assert {f.analysis for f in figures} == {"roi_psd", "roi_connectivity"}
    assert len(figures) == 2  # one per module


# --------------------------------------------------------------------------- #
# Graph-metric heatmap dual-reads the native nodal hypotheses table, and the
# module renders only one graph-metric figure set even when both the native
# hypotheses table and the legacy *_stats.csv are present.
# --------------------------------------------------------------------------- #
def test_graph_metric_matches_native_and_legacy():
    from source_lightbox.render import RoiGraphMetricHeatmap

    native = "hypothesis,band,spatial,conn_metric,graph_metric,stat,effect_size,q_value,significant"
    legacy = "contrast,band,conn_metric,graph_metric,roi,t,p,p_fdr"
    assert select_renderer(native.split(",")) is RoiGraphMetricHeatmap
    assert select_renderer(legacy.split(",")) is RoiGraphMetricHeatmap


def test_graph_metric_native_render_skips_global_rows(tmp_path):
    from source_lightbox.render import RoiGraphMetricHeatmap, _records

    headers = "hypothesis,band,spatial,conn_metric,graph_metric,stat,q_value".split(",")
    rows = []
    for band in ("Theta", "Alpha"):
        rows.append(["disease_effect", band, "", "imag_coherence", "modularity", "1.2", "0.2"])  # global
        for roi in ("Motor_L", "Motor_R"):
            rows.append(["disease_effect", band, roi, "imag_coherence", "degree", "2.5", "0.01"])
    recs = _records(headers, rows)
    out = RoiGraphMetricHeatmap.render(recs, headers, tmp_path, "roi_graph_hypotheses", 50, overview=True)
    assert len(out) == 1 and "degree" in out[0].name


def test_module_draws_one_graph_metric_set(tmp_path):
    """Native hypotheses + legacy stats both match the graph renderer; only one
    figure set is produced for the module (no duplicate heatmaps)."""
    from source_lightbox.render import render_table_figures
    from source_lightbox.scanner import TableEntry

    d = tmp_path / "tables"
    d.mkdir()
    native = d / "roi_graph_hypotheses.csv"
    native.write_text("hypothesis,band,spatial,conn_metric,graph_metric,stat,q_value\n"
                      "disease_effect,Theta,Motor_L,imag_coherence,degree,2.5,0.01\n"
                      "disease_effect,Theta,Motor_R,imag_coherence,degree,-1.0,0.30\n")
    legacy = d / "roi_graph_stats.csv"
    legacy.write_text("contrast,band,conn_metric,graph_metric,roi,t,p,p_fdr\n"
                      "disease_effect,Theta,imag_coherence,degree,Motor_L,2.5,0.001,0.01\n"
                      "disease_effect,Theta,imag_coherence,degree,Motor_R,-1.0,0.2,0.30\n")
    tables = [TableEntry(src_path=p, source_label="ROI", paradigm="resting", analysis="roi_graph",
                         filename=p.name) for p in (native, legacy)]
    figs = render_table_figures(tables, tmp_path / "out", dpi=50)
    assert len(figs) == 1


def test_circos_trigger_needs_subnetwork_edges_and_edge_csv(tmp_path, monkeypatch):
    """Circos are driven by the NBS module's *_subnetwork_edges.csv plus the
    roi_connectivity edge CSV in the analytics tree — the retired region-pair
    posthoc table is not required. The worker itself is stubbed."""
    from source_lightbox.scanner import TableEntry

    tbl_dir = tmp_path / "tables"
    tbl_dir.mkdir()
    sub = tbl_dir / "roi_nbs_subnetwork_edges.csv"
    sub.write_text("hypothesis,band,dv,component_id,component_p,significant,node_i,node_j,roi_i,roi_j,stat\n"
                   "disease_effect,Theta,imag_coherence,1,0.001,True,0,1,Motor_L,Motor_R,3.1\n")
    nbs = tbl_dir / "roi_nbs_results.csv"
    nbs.write_text("key,component,n_edges,p_corrected\ndisease_effect_Theta_imag_coherence,1,4,0.001\n")
    analytics = tmp_path / "analytics"
    edges = analytics / "resting" / "roi_connectivity" / "data" / "roi_connectivity_edges.csv"
    edges.parent.mkdir(parents=True)
    edges.write_text("subject,group,band,roi1,roi2,imag_coherence\n")

    calls = []

    def fake_render(edges_csv, subnetwork_csv, out_dir, contrasts, **kw):
        calls.append((edges_csv, subnetwork_csv))
        p = Path(out_dir) / "circos__imag_coherence__Theta__disease_effect.png"
        p.write_bytes(b"PNG")
        return [p]

    import source_lightbox.circos as circos_mod

    monkeypatch.setattr(circos_mod, "circos_available", lambda py=None: True)
    monkeypatch.setattr(circos_mod, "render_circos", fake_render)

    tables = [TableEntry(src_path=p, source_label="ROI", paradigm="resting", analysis="roi_nbs",
                         filename=p.name) for p in (sub, nbs)]
    figs = render_table_figures(
        tables, tmp_path / "out", dpi=50,
        circos={"analytics_dir": str(analytics),
                "contrasts": [{"name": "disease_effect", "group_a": "KO", "group_b": "WT"}]})
    assert calls == [(edges, sub)]
    names = sorted(f.filename for f in figs)
    # circos AND the NBS component heatmap (circos no longer replace the overview)
    assert names[0].startswith("circos__") and any("nbs" in n for n in names[1:])
