"""Unit tests for transition report path conventions."""

from pathlib import Path

import pytest

from sbir_etl.utils.transition_report_paths import ReportPaths


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
