"""Tests for per-subject QC metadata (group + outlier flags)."""

from source_lightbox.qc_meta import compute_subject_meta


def _metrics():
    # 5 normal subjects + one clear stc_amp_mean outlier (sub-803-like).
    rows = []
    for sid, amp in [("801", 1.0), ("802", 1.1), ("804", 0.9), ("805", 1.05), ("806", 0.95)]:
        rows.append({"subject_id": sid, "group": "WT_VEH", "forward_condition_number": "10",
                     "stc_amp_mean": str(amp), "stc_amp_max": "2.0", "stc_n_times": "1000"})
    rows.append({"subject_id": "803", "group": "WT_VEH", "forward_condition_number": "10",
                 "stc_amp_mean": "5.0", "stc_amp_max": "2.0", "stc_n_times": "1000"})
    return rows


def test_group_and_outlier_flagging():
    keys = ["sub-801", "sub-802", "sub-803", "sub-804", "sub-805", "sub-806"]
    meta = compute_subject_meta(_metrics(), keys)
    assert meta["sub-801"]["group"] == "WT_VEH"
    assert meta["sub-803"]["outliers"] == ["stc_amp_mean"]  # the lone high value
    assert meta["sub-801"]["outliers"] == []  # normal subject


def test_constant_metric_not_flagged():
    # stc_amp_max and stc_n_times are constant -> std 0 -> never flagged.
    keys = ["sub-801", "sub-802", "sub-803", "sub-804", "sub-805", "sub-806"]
    meta = compute_subject_meta(_metrics(), keys)
    for m in meta.values():
        assert "stc_amp_max" not in m["outliers"]
        assert "stc_n_times" not in m["outliers"]


def test_missing_subject_defaults():
    meta = compute_subject_meta(_metrics(), ["sub-999"])
    assert meta["sub-999"] == {"group": None, "outliers": []}


def test_empty_metrics():
    meta = compute_subject_meta([], ["sub-801"])
    assert meta["sub-801"] == {"group": None, "outliers": []}
