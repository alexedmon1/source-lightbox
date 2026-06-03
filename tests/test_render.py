"""Tests for the table-driven figure renderers (one overview per module)."""

from pathlib import Path

from source_lightbox.render import (
    ClusterHeatmap,
    EffectSizeHeatmap,
    MvpaHeatmap,
    NbsComponentPlot,
    RoiBandHeatmap,
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
