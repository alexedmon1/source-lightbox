"""Tests for study-contrast normalization (legacy contrasts: vs migrated hypotheses:)."""

from source_lightbox.cli import normalize_study_contrasts
from source_lightbox.manifest import build_manifest
from source_lightbox.scanner import ScanResult


def test_legacy_contrasts_pass_through():
    cfg = {"contrasts": [
        {"name": "disease_effect", "label": "Disease effect", "group": "phenotype",
         "group_a": "KO_VEH", "group_b": "WT_VEH"},
    ]}
    out = normalize_study_contrasts(cfg)
    assert len(out) == 1
    assert out[0]["name"] == "disease_effect"
    assert out[0]["group_a"] == "KO_VEH" and out[0]["group_b"] == "WT_VEH"


def test_hypotheses_are_normalized():
    cfg = {"hypotheses": [
        {"name": "group_omnibus", "kind": "omnibus", "label": "Omnibus", "role": "phenotype"},
        {"name": "disease_effect", "kind": "contrast", "label": "Disease effect (KO vs WT)",
         "role": "phenotype", "weights": {"KO_VEH": 1, "WT_VEH": -1}},
        {"name": "hd_icv_rescue", "kind": "contrast", "label": "HD-ICV rescue",
         "role": "rescue", "weights": {"KO_HD_ICV": 1, "KO_VEH": -1}},
    ]}
    out = normalize_study_contrasts(cfg)
    names = [c["name"] for c in out]
    assert names == ["group_omnibus", "disease_effect", "hd_icv_rescue"]

    by = {c["name"]: c for c in out}
    # role carries into `group`; label preserved.
    assert by["disease_effect"]["label"] == "Disease effect (KO vs WT)"
    assert by["disease_effect"]["group"] == "phenotype"
    # +1/-1 weights become the circos group pair.
    assert by["disease_effect"]["group_a"] == "KO_VEH"
    assert by["disease_effect"]["group_b"] == "WT_VEH"
    assert by["hd_icv_rescue"]["group_a"] == "KO_HD_ICV"
    assert by["hd_icv_rescue"]["group_b"] == "KO_VEH"
    # An omnibus (no two-group weights) still appears, without a group pair.
    assert "group_a" not in by["group_omnibus"]


def test_contrasts_take_precedence_over_hypotheses():
    cfg = {
        "contrasts": [{"name": "legacy_only", "label": "L"}],
        "hypotheses": [{"name": "ignored", "weights": {"A": 1, "B": -1}}],
    }
    out = normalize_study_contrasts(cfg)
    assert [c["name"] for c in out] == ["legacy_only"]


def test_manifest_embeds_contrast_labels():
    """contrast_labels must reach the manifest — the frontend groups figures by it."""
    scan = ScanResult(figures=[], tables=[], qc_entries=[])
    labels = {"disease_effect": "Disease effect (KO vs WT)"}
    manifest = build_manifest(scan, title="T", contrast_labels=labels)
    assert manifest["contrast_labels"] == labels
