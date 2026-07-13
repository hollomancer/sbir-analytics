"""Unit tests for transition report path conventions."""

import argparse
from pathlib import Path
from types import SimpleNamespace

import pytest

from sbir_etl.utils.transition_report_paths import (
    ReportPaths,
    add_area_args,
    resolve_area_paths,
)


def test_canonical_paths():
    p = ReportPaths.for_area("quantum_information_science")
    assert p.report_dir.name == "quantum_information_science"
    assert p.artifact("cohort_keyword").name == "cohort_keyword.csv"
    assert p.artifact("dark_firm_liveness").name == "dark_firm_liveness.csv"
    assert "analysis" in str(p.analysis_dir)


def test_legacy_nano_paths():
    p = ReportPaths.legacy_nano()
    assert p.artifact("cohort_keyword").name == "nano_cohort_keyword.csv"
    assert p.artifact("form_d_post_phase2").name == "nano_form_d_post_phase2.csv"
    assert p.artifact("ws1_contract_evidence").name == "nano_ws1_contract_evidence.csv"
    assert p.artifact("ws2_contract_evidence").name == "nano_ws2_contract_evidence.csv"
    assert p.artifact("no_uei_resolution").name == "nano_no_uei_resolution.csv"
    assert p.analysis_dir.name == "analysis"


def test_legacy_rejected_for_non_nano():
    p = ReportPaths.for_area("hypersonics", legacy=True)
    with pytest.raises(ValueError, match="legacy"):
        p.artifact("cohort_keyword")


def test_unknown_stem():
    p = ReportPaths.for_area("nanotechnology")
    with pytest.raises(KeyError):
        p.artifact("not_a_real_stem")


def test_config_path():
    p = ReportPaths.for_area("hypersonics")
    assert p.config_path == Path("config/transition_reports/hypersonics.yaml") or (
        p.config_path.as_posix().endswith("config/transition_reports/hypersonics.yaml")
    )


def test_resolve_unflagged_uses_area_layout():
    # Post-cutover: unflagged invocation defaults to the nanotechnology area
    # layout, not the pre-cutover data/nano_* paths.
    args = SimpleNamespace(area="nanotechnology", legacy=False)
    p = resolve_area_paths(args, argv=["--refresh"])
    assert p.legacy is False
    assert p.area_id == "nanotechnology"
    assert p.artifact("ws1_contract_evidence").name == "ws1_contract_evidence.csv"
    assert "nanotechnology" in str(p.artifact("ws1_contract_evidence"))


def test_resolve_explicit_legacy_opts_out():
    args = SimpleNamespace(area="nanotechnology", legacy=True)
    p = resolve_area_paths(args, argv=["--legacy"])
    assert p.legacy is True
    assert p.artifact("ws1_contract_evidence").name == "nano_ws1_contract_evidence.csv"


def test_resolve_explicit_area():
    args = SimpleNamespace(area="quantum_information_science", legacy=False)
    p = resolve_area_paths(args, argv=["--area", "quantum_information_science"])
    assert p.legacy is False
    assert p.area_id == "quantum_information_science"
    assert p.artifact("ws2_contract_evidence").name == "ws2_contract_evidence.csv"
    assert "quantum_information_science" in str(p.artifact("ws2_contract_evidence"))


def test_resolve_area_equals_form():
    args = SimpleNamespace(area="hypersonics", legacy=False)
    p = resolve_area_paths(args, argv=["--area=hypersonics", "--refresh"])
    assert p.legacy is False
    assert p.area_id == "hypersonics"


def test_add_area_args_on_parser():
    parser = argparse.ArgumentParser()
    add_area_args(parser)
    ns = parser.parse_args(["--area", "hypersonics"])
    assert ns.area == "hypersonics"
    assert ns.legacy is False


def test_load_config_returns_area_yaml():
    cfg = ReportPaths.for_area("nanotechnology").load_config()
    assert cfg["area_id"] == "nanotechnology"
    # Nanotech enables the WS5c sector-registry gate (biomed slice).
    assert set(cfg.get("sector_registries") or []) == {"clinical_trials", "fda_510k"}


def test_load_config_gate_off_for_non_biomed_areas():
    # Quantum / hypersonics have no biomedical go-to-market pathway → gate off.
    for area in ("quantum_information_science", "hypersonics"):
        cfg = ReportPaths.for_area(area).load_config()
        assert (cfg.get("sector_registries") or []) == []


def test_load_config_missing_area_raises():
    with pytest.raises(FileNotFoundError):
        ReportPaths.for_area("no_such_area").load_config()
