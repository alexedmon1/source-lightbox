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


# ---- the study's atlas and category map reach the build ----------------------
# Without them the render workers could only guess, and for allen26 data the guess
# was allen32's partition (see test_worker_atlas.py).

def _config_from_study(tmp_path, monkeypatch, study: dict):
    import yaml
    from click.testing import CliRunner

    import source_lightbox.builder as builder
    from source_lightbox.cli import main

    seen = {}
    monkeypatch.setattr(builder, "build", lambda config, verbose=True: seen.setdefault("config", config))
    cfg = tmp_path / "study.yaml"
    cfg.write_text(yaml.safe_dump({"paths": {"gallery": str(tmp_path / "gallery")}, **study}))
    res = CliRunner().invoke(main, ["build", "--config", str(cfg)])
    assert res.exit_code == 0, res.output
    return seen["config"]


def test_study_atlas_and_inline_categories_reach_the_build(tmp_path, monkeypatch):
    cats = {"Deep Subcortical": ["Thalamus", "Cerebellum"], "Motor": ["Motor_L", "Motor_R"]}
    config = _config_from_study(tmp_path, monkeypatch,
                                {"pipeline": {"atlas": "allen26"}, "roi_categories": cats})
    assert config.atlas == "allen26"
    assert config.roi_categories == cats


def test_a_profile_build_uses_the_profile_categories(tmp_path, monkeypatch):
    config = _config_from_study(tmp_path, monkeypatch, {
        "pipeline": {"atlas": "allen26"},
        "roi_categories": {"Motor": ["Motor_L", "Motor_R"], "Deep": ["Thalamus"]},
        "gallery_profile": "external",
        "external": {"roi_categories": {"Motor": ["Motor_L", "Motor_R"]}},
    })
    assert config.roi_categories == {"Motor": ["Motor_L", "Motor_R"]}


def test_an_explicit_categories_path_still_wins(tmp_path, monkeypatch):
    path = tmp_path / "cats.yaml"
    path.write_text("roi_categories: {Motor: [Motor_L]}\n")
    config = _config_from_study(tmp_path, monkeypatch, {
        "paths": {"gallery": str(tmp_path / "gallery"), "roi_categories": str(path)},
        "roi_categories": {"Other": ["Thalamus"]},
    })
    assert config.roi_categories == str(path)
