"""What built a localization run and its analyses, and the analyses that are gone."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from source_lightbox.config import RETIRED_ANALYSES
from source_lightbox.scanner import (
    FigureEntry,
    LocalizationScanner,
    ScanResult,
    TableEntry,
    _read_run,
    _summarise_runs,
)


def _snapshot(sampling="fixed", atlas="allen32", inverse="sLORETA", bem="ellipsoid"):
    return {
        "source_localization_version": "0.5.1",
        "config": {
            "pipeline": {"bem_type": bem, "source_type": "surface"},
            "source_space": ({"surface": {"method": "anatomical"},
                              "source_sampling": "monte_carlo",
                              "monte_carlo": {"n_draws": 100}}
                             if sampling == "monte_carlo" else
                             {"surface": {"method": "anatomical"}}),
            "inverse": {"method": inverse, "orientation": "fixed"},
            "provenance": {"preset": "ellipsoid_surface_anatomical", "atlas": atlas},
        },
    }


def _subject(root, sub_id, snapshot=None):
    data = root / "derivatives" / sub_id / "pipeline" / "data"
    data.mkdir(parents=True)
    figs = root / "derivatives" / sub_id / "pipeline" / "figures"
    figs.mkdir(parents=True)
    (figs / "step1.png").write_bytes(b"PNG")
    if snapshot is not None:
        (data / "config_resolved.yaml").write_text(yaml.safe_dump(snapshot))
    return data


class TestReadRun:
    def test_absent_manifest_reads_as_none(self, tmp_path):
        tmp_path.joinpath("data").mkdir()
        assert _read_run(tmp_path / "data") is None

    def test_malformed_yaml_reads_as_none(self, tmp_path):
        d = tmp_path / "data"
        d.mkdir()
        (d / "config_resolved.yaml").write_text("{[ not yaml")
        assert _read_run(d) is None

    def test_fixed_run_defaults_to_fixed_sampling(self, tmp_path):
        run = _read_run(_subject(tmp_path, "sub-1", _snapshot()))
        assert run["sampling"] == "fixed"
        assert run["atlas"] == "allen32"
        assert run["source_space"] == "surface/anatomical"
        assert run["inverse"] == "sLORETA"

    def test_monte_carlo_run_is_labelled(self, tmp_path):
        run = _read_run(_subject(tmp_path, "sub-1", _snapshot(sampling="monte_carlo")))
        assert run["sampling"] == "monte_carlo"


class TestSummariseRuns:
    def test_no_manifests_summarise_to_none(self):
        assert _summarise_runs({"sub-1": None, "sub-2": None}) is None

    def test_agreeing_subjects_have_no_mismatch(self, tmp_path):
        per = {s: _read_run(_subject(tmp_path, s, _snapshot())) for s in ("sub-1", "sub-2")}
        summary = _summarise_runs(per)
        assert summary["mismatched"] == []
        assert summary["n_subjects"] == 2
        assert summary["n_unrecorded"] == 0

    def test_mixed_sampling_is_reported(self, tmp_path):
        per = {
            "sub-1": _read_run(_subject(tmp_path, "sub-1", _snapshot())),
            "sub-2": _read_run(_subject(tmp_path, "sub-2",
                                        _snapshot(sampling="monte_carlo"))),
        }
        assert "sampling" in _summarise_runs(per)["mismatched"]

    def test_mixed_atlas_is_reported(self, tmp_path):
        per = {
            "sub-1": _read_run(_subject(tmp_path, "sub-1", _snapshot())),
            "sub-2": _read_run(_subject(tmp_path, "sub-2", _snapshot(atlas="allen26"))),
        }
        assert "atlas" in _summarise_runs(per)["mismatched"]

    def test_unrecorded_subjects_are_counted_not_guessed(self, tmp_path):
        per = {
            "sub-1": _read_run(_subject(tmp_path, "sub-1", _snapshot())),
            "sub-legacy": _read_run(_subject(tmp_path, "sub-legacy", None)),
        }
        summary = _summarise_runs(per)
        assert summary["n_subjects"] == 1
        assert summary["n_unrecorded"] == 1
        assert summary["mismatched"] == []


class TestScannerIntegration:
    def test_scan_exposes_the_run_under_the_source_label(self, tmp_path):
        _subject(tmp_path, "sub-1", _snapshot(sampling="monte_carlo"))
        result = LocalizationScanner(tmp_path, "Surface MC").scan()
        assert result.runs["Surface MC"]["sampling"] == "monte_carlo"

    def test_scan_without_manifests_reports_no_run(self, tmp_path):
        _subject(tmp_path, "sub-1", None)
        assert LocalizationScanner(tmp_path, "Old").scan().runs == {}


class TestRetiredAnalyses:
    """The vertex analyses left source-analytics; an old tree still has them."""

    def test_the_retired_set_covers_the_vertex_modules(self):
        for name in ("vertex_cluster", "vertex_specparam", "vertex_signature",
                     "vertex_connectivity", "fcd_comparison"):
            assert name in RETIRED_ANALYSES

    def test_old_spellings_are_retired_too(self):
        for alias in ("wholebrain", "spatial_lmm", "mvpa"):
            assert alias in RETIRED_ANALYSES

    def test_current_analyses_are_not_retired(self):
        for name in ("roi_psd", "roi_connectivity", "electrode_psd", "roi_signature"):
            assert name not in RETIRED_ANALYSES

    @staticmethod
    def _scan_with(analyses):
        scan = ScanResult()
        for a in analyses:
            scan.figures.append(FigureEntry(src_path=Path(f"{a}.png"), category="analytics",
                                            source_label="R", paradigm="resting",
                                            analysis=a, filename=f"{a}.png"))
            scan.tables.append(TableEntry(src_path=Path(f"{a}.csv"), source_label="R",
                                          paradigm="resting", analysis=a,
                                          filename=f"{a}.csv"))
        return scan

    def _filter(self, scan, include_retired=False):
        """The builder's retired filter, isolated from the rest of the build."""
        if include_retired:
            return scan
        def retired(e):
            return (e.analysis in RETIRED_ANALYSES
                    or getattr(e, "paradigm", None) in RETIRED_ANALYSES)
        scan.figures = [e for e in scan.figures if not retired(e)]
        scan.tables = [e for e in scan.tables if not retired(e)]
        return scan

    def test_retired_entries_are_dropped(self):
        scan = self._filter(self._scan_with(["roi_psd", "vertex_specparam"]))
        assert [e.analysis for e in scan.figures] == ["roi_psd"]
        assert [e.analysis for e in scan.tables] == ["roi_psd"]

    def test_include_retired_keeps_them(self):
        scan = self._filter(self._scan_with(["roi_psd", "vertex_specparam"]),
                            include_retired=True)
        assert len(scan.figures) == 2


class TestBuildEndToEnd:
    """A build over a tree carrying both current and retired output."""

    @pytest.fixture
    def study(self, tmp_path):
        loc = tmp_path / "localization"
        _subject(loc, "sub-1", _snapshot(sampling="monte_carlo"))

        res = tmp_path / "results"
        for analysis in ("roi_psd", "vertex_specparam"):
            d = res / "tables" / "resting" / analysis
            d.mkdir(parents=True)
            (d / f"{analysis}_summary.csv").write_text("roi,effect\nAuditory_L,0.4\n")
        return loc, res, tmp_path / "gallery"

    def _build(self, study, **over):
        from source_lightbox.builder import build
        from source_lightbox.config import BuildConfig, SourceInput

        loc, res, out = study
        cfg = BuildConfig(
            localizations=[SourceInput(path=loc, label="Surface MC")],
            results=[SourceInput(path=res, label="Resting")],
            output_dir=out, render_figures=False, brain_render=False, **over)
        build(cfg, verbose=False)
        import json
        return json.loads((out / "manifest.json").read_text()) if (
            out / "manifest.json").exists() else _inline_manifest(out)

    def test_retired_tables_do_not_reach_the_gallery(self, study):
        names = _analyses_in(self._build(study))
        assert "roi_psd" in names
        assert "vertex_specparam" not in names

    def test_include_retired_publishes_them(self, study):
        names = _analyses_in(self._build(study, include_retired=True))
        assert "vertex_specparam" in names

    def test_the_run_reaches_the_manifest(self, study):
        manifest = self._build(study)
        run = manifest["localization"]["Surface MC"]["run"]
        assert run["sampling"] == "monte_carlo"
        assert run["atlas"] == "allen32"
        assert run["mismatched"] == []


def _inline_manifest(out: Path) -> dict:
    """The manifest is inlined into index.html when no sidecar is written."""
    import json
    import re

    html = (out / "index.html").read_text()
    m = re.search(r"window\.MANIFEST = (\{.*?\});", html, re.S)
    assert m, "no manifest in the built gallery"
    return json.loads(m.group(1))


def _analyses_in(manifest: dict) -> set:
    """Analysis names the built gallery actually carries."""
    return {
        analysis
        for paradigm in (manifest.get("paradigms") or {}).values()
        for analysis in paradigm
    }


class TestAnalyticsProvenance:
    """source-analytics' provenance.json, surfaced under Analytics."""

    RECORD = {
        "schema": 1,
        "written": "2026-09-18T14:01:36-04:00",
        "analysis": "roi_psd",
        "paradigm": "resting",
        "source_analytics": {"version": "v0.8.2", "git_describe": "v0.8.2"},
        "steps": ["aggregate", "process", "setup"],
        "subjects": {"n": 3, "groups": {"KO": 1, "WT": 2},
                     "ids": ["sub-901", "sub-902", "sub-903"]},
        "localization": {
            "n_with_manifest": 3, "n_unrecorded": 0,
            "description": "ellipsoid_surface_anatomical, allen26, Monte Carlo (K=100)",
            "version": "0.5.1", "atlas": "allen26",
            "source_sampling": "monte_carlo", "inverse_method": "sLORETA",
        },
        "plugins": {"vertex": {"version": "0.1.0", "provides_this_analysis": True},
                    "other": {"version": "2.0"}},
        "parcel_caveats": {"Thalamus": "sampled in 31% of draws"},
    }

    @staticmethod
    def _results(root, record=None, analysis="roi_psd"):
        d = root / "tables" / "resting" / analysis
        d.mkdir(parents=True)
        (d / f"{analysis}_hypotheses.csv").write_text("roi,hedges_g\nAuditory_L,0.4\n")
        if record is not None:
            (d / "provenance.json").write_text(json.dumps(record))
        return root

    def test_scanner_reads_it(self, tmp_path):
        from source_lightbox.scanner import ResultsScanner

        res = ResultsScanner(self._results(tmp_path, self.RECORD), "R").scan()
        assert res.provenance[("resting", "roi_psd")]["analysis"] == "roi_psd"

    def test_scanner_tolerates_absence(self, tmp_path):
        from source_lightbox.scanner import ResultsScanner

        res = ResultsScanner(self._results(tmp_path, None), "R").scan()
        assert res.provenance == {}

    def test_scanner_tolerates_corruption(self, tmp_path):
        from source_lightbox.scanner import ResultsScanner

        root = self._results(tmp_path, self.RECORD)
        (root / "tables" / "resting" / "roi_psd" / "provenance.json").write_text("{ bad")
        assert ResultsScanner(root, "R").scan().provenance == {}

    def test_provenance_is_not_read_as_a_table(self, tmp_path):
        from source_lightbox.scanner import ResultsScanner

        res = ResultsScanner(self._results(tmp_path, self.RECORD), "R").scan()
        assert [t.filename for t in res.tables] == ["roi_psd_hypotheses.csv"]

    def test_trim_keeps_what_is_displayed(self):
        from source_lightbox.manifest import _trim_provenance

        t = _trim_provenance(self.RECORD)
        assert t["source_analytics"] == "v0.8.2"
        assert t["n_subjects"] == 3
        assert t["groups"] == {"KO": 1, "WT": 2}
        assert t["localization"]["atlas"] == "allen26"
        assert t["localization"]["source_sampling"] == "monte_carlo"
        assert t["parcel_caveats"] == {"Thalamus": "sampled in 31% of draws"}

    def test_trim_drops_what_is_not_displayed(self):
        """The manifest is inlined into index.html, once per analysis."""
        from source_lightbox.manifest import _trim_provenance

        blob = json.dumps(_trim_provenance(self.RECORD))
        assert "sub-901" not in blob, "subject ids are provenance, not display"
        assert "steps" not in blob

    def test_trim_names_only_the_plugin_that_provided_the_analysis(self):
        from source_lightbox.manifest import _trim_provenance

        assert _trim_provenance(self.RECORD)["plugin"] == "vertex 0.1.0"

    def test_trim_omits_plugin_when_the_analysis_is_built_in(self):
        from source_lightbox.manifest import _trim_provenance

        rec = json.loads(json.dumps(self.RECORD))
        rec["plugins"] = {"other": {"version": "2.0"}}
        assert "plugin" not in _trim_provenance(rec)

    def test_trim_omits_caveats_for_a_fixed_grid_run(self):
        from source_lightbox.manifest import _trim_provenance

        rec = json.loads(json.dumps(self.RECORD))
        del rec["parcel_caveats"]
        assert "parcel_caveats" not in _trim_provenance(rec)

    def test_it_reaches_the_built_manifest(self, tmp_path):
        from source_lightbox.builder import build
        from source_lightbox.config import BuildConfig, SourceInput

        res = self._results(tmp_path / "results", self.RECORD)
        self._results(tmp_path / "results", None, analysis="roi_aperiodic")
        out = tmp_path / "g"
        build(BuildConfig(localizations=[], results=[SourceInput(path=res, label="R")],
                          output_dir=out, render_figures=False, brain_render=False,
                          thumb_workers=1), verbose=False)
        man = _inline_manifest(out)
        block = man["paradigms"]["resting"]
        assert block["roi_psd"]["provenance"]["localization"]["atlas"] == "allen26"
        assert "provenance" not in block["roi_aperiodic"], "absent must stay absent"
