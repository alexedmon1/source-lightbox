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


def test_no_effect_size_table_returns_none():
    tbl = _tbl("roi_psd_omnibus.csv", "contrast,band,group_F,group_p",
              ["disease_effect,Alpha,0.2,0.6"])
    assert build_significance_summary([tbl]) is None


def test_no_significant_rows_states_so():
    tbl = _tbl("x_global.csv", "contrast,band,hedges_g,significant",
              ["disease_effect,Alpha,0.1,FALSE"])
    html = build_significance_summary([tbl])
    assert html is not None and "No significant" in html
