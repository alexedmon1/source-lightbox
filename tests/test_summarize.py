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
