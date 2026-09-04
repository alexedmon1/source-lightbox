"""Tests for the study-YAML plumbing in the CLI."""

from pathlib import Path

from source_lightbox.cli import (
    normalize_study_contrasts,
    resolve_config_path,
    study_group_display,
)


def test_resolve_config_path_expands_tilde_and_relative(tmp_path):
    home = Path.home()
    assert resolve_config_path("~/x/python", "", tmp_path) == str(home / "x" / "python")
    assert resolve_config_path("./results", "", tmp_path) == str((tmp_path / "results").resolve())
    assert resolve_config_path(None, "./gallery", tmp_path) == str((tmp_path / "gallery").resolve())
    assert resolve_config_path("/abs/p", "", tmp_path) == "/abs/p"


def test_study_group_display_dict_and_list_forms():
    labels, order = study_group_display({"groups": {"WT_VEH": "WT Vehicle", "KO_VEH": "KO Vehicle"},
                                         "group_order": ["KO_VEH", "WT_VEH"]})
    assert labels == {"WT_VEH": "WT Vehicle", "KO_VEH": "KO Vehicle"}
    assert order == ["KO_VEH", "WT_VEH"]
    labels, order = study_group_display({"groups": [{"name": "A", "label": "Group A"}, "B"]})
    assert labels == {"A": "Group A", "B": "B"} and order == ["A", "B"]
    assert study_group_display({}) == (None, None)


def test_normalize_study_contrasts_from_hypotheses():
    cfg = {"hypotheses": [{"name": "disease_effect", "label": "KO vs WT", "role": "confirmatory",
                           "weights": {"KO_VEH": 1, "WT_VEH": -1}}]}
    out = normalize_study_contrasts(cfg)
    assert out[0]["group_a"] == "KO_VEH" and out[0]["group_b"] == "WT_VEH"
    assert out[0]["group"] == "confirmatory"
