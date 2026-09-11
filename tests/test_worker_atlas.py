"""The render workers get the study's categories and atlas, and their fallback can
see every atlas's category file.

The bug: neither launcher passed an atlas, the circos worker was never given the
study's categories, and the workers' fallback globbed for files named exactly
``roi_categories.yaml``. In a directory shared by allen32, allen26 and allen64
that is only allen32's file. On the FORGE treatment study (allen26) both workers
picked allen32's partition: 20 of 26 parcels, with the six merged parcels
missing from every circos.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from source_lightbox import _worker_atlas as wa
from source_lightbox import brain_mosaic, circos
from source_lightbox.render import render_table_figures

PKG = Path(wa.__file__).resolve().parent

ALLEN26 = [
    "Frontal_Anterior", "Motor_L", "Motor_R", "Somatosensory_L", "Somatosensory_R",
    "Auditory_L", "Auditory_R", "Visual_Parietal_L", "Visual_Parietal_R",
    "Lateral_Cortex_L", "Lateral_Cortex_R", "Retrosplenial_L", "Retrosplenial_R",
    "Olfactory_Bulb", "Hippocampus_Ant_L", "Hippocampus_Ant_R", "Hippocampus_Post_L",
    "Hippocampus_Post_R", "Thalamus", "Hypothalamus", "Amygdalar_Complex_L",
    "Amygdalar_Complex_R", "Basal_Ganglia_L", "Basal_Ganglia_R", "Brainstem_Tectum",
    "Cerebellum",
]


# ---- precedence (pure; no source-analytics needed) ------------------------------

def test_an_explicit_mapping_wins_and_is_unwrapped():
    cats, source = wa.resolve_categories({"roi_categories": {"Motor": ["Motor_L"]}},
                                         "allen26", {"Motor_L"})
    assert cats == {"Motor": ["Motor_L"]} and source == "the study config"


def test_an_explicit_yaml_path_is_read(tmp_path):
    p = tmp_path / "cats.yaml"
    p.write_text(yaml.safe_dump({"roi_categories": {"Hipp": ["Hippocampus_Ant_L"]}}))
    assert wa.load_categories(str(p)) == {"Hipp": ["Hippocampus_Ant_L"]}


def test_the_fallback_sees_atlas_specific_category_files(tmp_path):
    allen = tmp_path / "allen"
    allen.mkdir()
    (allen / "roi_categories.yaml").write_text(yaml.safe_dump(
        {"Frontal": ["Frontal_Anterior_L", "Frontal_Anterior_R"], "Motor": ["Motor_L"]}))
    (allen / "roi_categories_allen26.yaml").write_text(yaml.safe_dump(
        {"Frontal": ["Frontal_Anterior"], "Motor": ["Motor_L"]}))
    picked = wa.guess_from_files(tmp_path, {"Frontal_Anterior", "Motor_L"})
    assert picked == {"Frontal": ["Frontal_Anterior"], "Motor": ["Motor_L"]}


def test_mosaics_get_the_atlas_only_when_source_analytics_can_take_it():
    def new(csv, cats, out, *, atlas=None):  # PR-3-era render_posthoc_mosaics
        return []

    def old(csv, cats, out):
        return []

    assert wa.mosaic_atlas_kwargs("allen26", new) == ({"atlas": "allen26"}, None)
    kw, warning = wa.mosaic_atlas_kwargs("allen26", old)
    assert kw == {} and "blank" in warning
    assert wa.mosaic_atlas_kwargs("allen", old) == ({}, None)   # default draws it already
    assert wa.mosaic_atlas_kwargs(None, new) == ({}, None)


# ---- the launchers carry categories + atlas to the workers -----------------------

class _Done:
    returncode, stdout, stderr = 0, "[]", ""


def test_both_launchers_forward_categories_and_atlas(monkeypatch, tmp_path):
    payloads = []
    monkeypatch.setattr(subprocess, "run",
                        lambda argv, **kw: payloads.append(json.loads(argv[-1])) or _Done())
    cats = {"Motor": ["Motor_L", "Motor_R"]}
    brain_mosaic.render_roi_mosaics(tmp_path / "t.csv", categories=cats, out_dir=tmp_path,
                                    analysis_name="psd", atlas="allen26",
                                    python_path=sys.executable)
    circos.render_circos(tmp_path / "e.csv", tmp_path / "s.csv", tmp_path, [],
                         categories=cats, atlas="allen26", python_path=sys.executable)
    assert [(p["categories"], p["atlas"]) for p in payloads] == [(cats, "allen26")] * 2


def test_render_passes_the_study_atlas_and_categories_to_circos(tmp_path, monkeypatch):
    from source_lightbox.scanner import TableEntry

    tbl = tmp_path / "tables"
    tbl.mkdir()
    sub = tbl / "roi_nbs_subnetwork_edges.csv"
    sub.write_text("hypothesis,band,dv,component_id,component_p,significant,node_i,node_j,roi_i,roi_j,stat\n"
                   "disease_effect,Theta,imag_coherence,1,0.001,True,0,1,Thalamus,Cerebellum,3.1\n")
    edges = tmp_path / "analytics" / "resting" / "roi_connectivity" / "data" / "roi_connectivity_edges.csv"
    edges.parent.mkdir(parents=True)
    edges.write_text("subject,group,band,roi1,roi2,imag_coherence\n")
    seen = {}

    def fake_render(*args, **kw):
        seen.update(kw)
        return []

    monkeypatch.setattr(circos, "circos_available", lambda py=None: True)
    monkeypatch.setattr(circos, "render_circos", fake_render)
    cats = {"Deep Subcortical": ["Thalamus", "Cerebellum"]}
    render_table_figures(
        [TableEntry(src_path=sub, source_label="ROI", paradigm="resting",
                    analysis="roi_nbs", filename=sub.name)],
        tmp_path / "out", dpi=50,
        circos={"analytics_dir": str(tmp_path / "analytics"), "categories": cats,
                "atlas": "allen26",
                "contrasts": [{"name": "disease_effect", "group_a": "KO", "group_b": "WT"}]})
    assert seen["categories"] == cats and seen["atlas"] == "allen26"


# ---- the real lookups, under the source-analytics interpreter -------------------

def _sa_run(code: str) -> subprocess.CompletedProcess:
    py = brain_mosaic.resolve_python(None)
    env = dict(os.environ)
    if os.environ.get("SA_PYTHONPATH"):          # point at an unreleased source-analytics
        env["PYTHONPATH"] = os.environ["SA_PYTHONPATH"]
    return subprocess.run([str(py), "-c", f"import sys; sys.path.insert(0, {str(PKG)!r})\n" + code],
                          capture_output=True, text=True, env=env)


def _sa_can(expr: str) -> bool:
    py = brain_mosaic.resolve_python(None)
    return py.exists() and _sa_run(f"import source_analytics.atlas as a; {expr}").returncode == 0


@pytest.mark.skipif(not _sa_can("a.find_atlas_dir()"), reason="source-analytics atlas data unavailable")
def test_the_fallback_covers_every_allen26_parcel():
    res = _sa_run("import json, _worker_atlas as w\n"
                  f"cats, src = w.resolve_categories(None, None, {ALLEN26!r})\n"
                  "print(json.dumps(sorted(w.members(cats))))")
    assert res.returncode == 0, res.stderr
    assert set(json.loads(res.stdout.splitlines()[-1])) >= set(ALLEN26)


@pytest.mark.skipif(not _sa_can("a.resolve_atlas"), reason="source-analytics predates resolve_atlas")
def test_the_named_atlas_supplies_its_own_categories():
    res = _sa_run("import json, _worker_atlas as w\n"
                  f"cats, src = w.resolve_categories(None, 'allen26', {ALLEN26!r})\n"
                  "print(json.dumps([src, sorted(w.members(cats))]))")
    assert res.returncode == 0, res.stderr
    source, covered = json.loads(res.stdout.splitlines()[-1])
    assert source == "atlas allen26" and set(covered) == set(ALLEN26)
