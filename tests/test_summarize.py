"""Tests for the significance-digest generator."""

from source_lightbox.summarize import build_significance_summary


def _tbl(filename, header, rows):
    return {"filename": filename, "headers": header.split(","), "rows": [r.split(",") for r in rows]}


def test_digest_groups_by_contrast_with_direction():
    tbl = _tbl(
        "roi_psd_posthoc_global.csv",
        "contrast,dv,band,hedges_g,significant",
        [
            "disease_effect,relative,Low Gamma,1.62,TRUE",
            "disease_effect,relative,Delta,-0.20,FALSE",
            "hd_icv_vs_wt,relative,Low Gamma,3.55,TRUE",
            "hd_icv_vs_wt,relative,Theta,-1.20,TRUE",
            "dose_icv,relative,Alpha,0.10,FALSE",
        ],
    )
    html = build_significance_summary([tbl])
    assert html is not None
    assert "sig-summary" in html
    # significant contrasts present, non-significant-only contrast listed as null
    assert "disease_effect" in html and "hd_icv_vs_wt" in html
    assert "dose_icv" in html  # appears in the "No significant effects" line
    # direction: positive -> up arrow class, negative -> down
    assert "arrow up" in html and "arrow down" in html
    assert "g=3.55" in html


def test_digest_prefers_global_over_roi_detail():
    glob = _tbl("roi_psd_posthoc_global.csv", "contrast,band,hedges_g,significant",
               ["disease_effect,Low Gamma,1.6,TRUE"])
    roi = _tbl("roi_psd_posthoc_roi.csv", "contrast,roi,band,hedges_g,significant",
              ["disease_effect,Motor_R,Low Gamma,1.6,TRUE"])
    html = build_significance_summary([roi, glob])
    # global table has no 'roi' column, so a per-band digest (no ROI names) is built
    assert html is not None and "Motor_R" not in html


def test_grouped_into_tiers():
    tbl = _tbl(
        "roi_psd_posthoc_global.csv",
        "contrast,band,hedges_g,significant",
        [
            "disease_effect,Low Gamma,1.6,TRUE",
            "hd_icv_vs_wt,Low Gamma,3.5,TRUE",
            "ld_vs_wt,Low Gamma,3.5,TRUE",
        ],
    )
    groups = {"disease_effect": "Disease effect",
              "hd_icv_vs_wt": "Normalization to WT",
              "ld_vs_wt": "Normalization to WT"}
    html = build_significance_summary([tbl], contrast_groups=groups)
    assert html is not None
    # one section header per distinct group, in YAML order
    assert html.index("Disease effect") < html.index("Normalization to WT")
    assert html.count('class="sig-group"') == 2


def test_no_groups_stays_flat():
    tbl = _tbl("x_global.csv", "contrast,band,hedges_g,significant",
              ["disease_effect,Low Gamma,1.6,TRUE"])
    html = build_significance_summary([tbl])  # no contrast_groups
    assert 'class="sig-group"' not in html


def test_no_effect_size_table_returns_none():
    tbl = _tbl("roi_psd_omnibus.csv", "contrast,band,group_F,group_p",
              ["disease_effect,Alpha,0.2,0.6"])
    assert build_significance_summary([tbl]) is None


def test_aperiodic_uses_dv_when_band_is_na():
    # Aperiodic tables carry band="NA"; the category should fall back to dv.
    tbl = _tbl(
        "roi_aperiodic_posthoc_global.csv",
        "contrast,dv,band,hedges_g,significant",
        [
            "hd_icv_vs_wt,exponent,NA,-2.61,TRUE",
            "hd_icv_vs_wt,offset,NA,-2.00,TRUE",
            "disease_effect,exponent,NA,-0.4,FALSE",
        ],
    )
    html = build_significance_summary([tbl])
    assert html is not None
    assert "exponent" in html and "offset" in html
    assert ">NA<" not in html and " NA " not in html


def test_no_significant_rows_states_so():
    tbl = _tbl("x_global.csv", "contrast,band,hedges_g,significant",
              ["disease_effect,Alpha,0.1,FALSE"])
    html = build_significance_summary([tbl])
    assert html is not None and "No significant" in html


# ── generalized effect columns + per-element aggregation + NBS ──────────────

def test_roi_graph_aggregates_per_band_no_roi_flooding():
    # Per-ROI table (roi col present) must collapse to one chip per (contrast,band)
    # with an ROI count + the strongest g — never one chip per ROI.
    tbl = _tbl(
        "roi_graph_stats.csv",
        "contrast,band,conn_metric,graph_metric,roi,mean_a,mean_b,t,p,p_fdr,hedges_g,significant",
        [
            "disease_effect,Low Gamma,coherence,degree,Motor_R,1,0,3,0.001,0.01,0.91,TRUE",
            "disease_effect,Low Gamma,coherence,degree,Motor_L,1,0,3,0.001,0.02,1.40,TRUE",
            "disease_effect,Low Gamma,coherence,degree,Vis_R,1,0,2,0.2,0.4,0.30,FALSE",
            "disease_effect,Theta,coherence,degree,Aud_R,1,0,3,0.001,0.03,-0.80,TRUE",
        ],
    )
    html = build_significance_summary([tbl])
    assert html is not None
    assert "Motor_R" not in html and "Motor_L" not in html   # no per-ROI flooding
    assert "2 ROIs" in html                                   # Low Gamma: 2 sig ROIs
    assert "g=1.40" in html                                   # strongest |g| reported
    assert "arrow up" in html and "arrow down" in html        # both directions


def test_nbs_digest_from_key_with_spaced_band():
    tbl = _tbl(
        "roi_nbs_results.csv",
        "key,component,n_edges,p_corrected",
        [
            "disease_effect_Low Gamma_aec,1,12,0.004",   # band contains a space
            "disease_effect_Theta_coherence,1,5,0.20",   # not significant
            "hd_icv_vs_wt_Beta_pli,1,8,0.03",
        ],
    )
    html = build_significance_summary([tbl])
    assert html is not None
    assert "sub-network" in html
    assert "Low Gamma" in html and "12-edge" in html
    assert "p=0.004" in html
    # 2 significant sub-networks across 2 of 2 (or 3) comparisons
    assert "significant sub-network" in html


def test_mvpa_unsigned_vs_chance():
    tbl = _tbl(
        "vertex_mvpa_results.csv",
        "contrast,band,accuracy,p_value,auc",
        [
            "disease_effect,Low Gamma,0.78,0.002,0.81",
            "disease_effect,Delta,0.55,0.40,0.56",   # not significant
        ],
    )
    html = build_significance_summary([tbl])
    assert html is not None
    assert "AUC=0.81" in html
    assert "above chance" in html
    assert "arrow up" not in html and "arrow down" not in html  # unsigned: no arrows


def test_spatial_signed_coefficient():
    tbl = _tbl(
        "vertex_spatial_results.csv",
        "contrast,band,metric,coefficient,q_value,significant",
        [
            "disease_effect,Low Gamma,relative,0.42,0.01,TRUE",
            "disease_effect,Theta,relative,-0.30,0.30,FALSE",
        ],
    )
    html = build_significance_summary([tbl])
    assert html is not None
    assert "&beta;=+0.42" in html
    assert "arrow up" in html


def test_specparam_per_vertex_uses_corrected_significant():
    # Per-vertex table; significance must come from the explicit `significant`
    # column (cluster-corrected), NOT the uncorrected per-vertex p.
    tbl = _tbl(
        "vertex_specparam_stats.csv",
        "contrast,parameter,vertex_idx,t,p,hedges_g,cluster_id,cluster_p,significant",
        [
            "disease_effect,exponent,0,3,0.001,-0.9,1,0.02,TRUE",
            "disease_effect,exponent,1,2.8,0.004,-1.3,1,0.02,TRUE",
            "disease_effect,offset,2,2.1,0.03,0.5,0,nan,FALSE",   # uncorrected p<.05 but NOT in sig cluster
        ],
    )
    html = build_significance_summary([tbl])
    assert html is not None
    assert "exponent" in html and "2 vertices" in html
    assert "g=1.30" in html
    assert "offset" not in html   # the offset vertex is not cluster-significant


def test_vertex_cluster_digest_reads_corrected_clusters():
    # cluster_results.csv is the inferential unit (cluster-corrected p_corrected),
    # not the truncated per-vertex stats. Every contrast with a corrected cluster
    # must appear — including an equivalence-declared normalization contrast whose
    # difference clusters the figures draw.
    clusters = _tbl(
        "cluster_results.csv",
        "contrast,band,metric,cluster_id,n_vertices,cluster_stat,peak_t,p_corrected",
        [
            "disease_effect,Low Gamma,absolute,1,80,392.1,6.0,0.002",
            "disease_effect,Delta,relative,1,4,8.7,2.3,0.281",          # ns
            "hd_icv_normalization,Theta,relative,1,59,-184.8,-5.0,0.005",  # sig, normalization
            "hd_icv_normalization,Alpha,relative,1,12,-26.8,-2.8,0.135",   # ns
        ],
    )
    # A per-vertex stats table is present too; the digest must NOT prefer it.
    voxel = _tbl(
        "voxelwise_stats.csv",
        "contrast,band,metric,vertex_idx,t,hedges_g,p,cluster_id",
        ["disease_effect,Low Gamma,absolute,0,6.0,1.4,0.001,1"],
    )
    html = build_significance_summary([voxel, clusters],
                                      contrast_labels={"hd_icv_normalization": "HD-ICV normalization to WT"})
    assert html is not None
    assert "cluster-corrected" in html
    assert "2 significant clusters" in html and "2 of 2 comparisons" in html
    # normalization difference clusters are surfaced (the reported bug)
    assert "HD-ICV normalization to WT" in html
    assert "Low Gamma absolute" in html and "80 vertices" in html
    assert "Theta relative" in html
    # direction: negative peak_t -> down arrow; positive -> up
    assert "arrow up" in html and "arrow down" in html
    # non-significant clusters excluded
    assert "12 vertices" not in html
