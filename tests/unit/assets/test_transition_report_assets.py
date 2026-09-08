"""Unit tests for the tech-area transition-report Dagster assets (spec T9).

The asset module carries a Dagster import shim, so it imports even without
Dagster installed. We load it by file path to test its pure helper
(`_cohort_metrics`) and confirm the per-area asset/check factory wired up all
three areas — no Dagster runtime required.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
MODULE_PATH = (
    REPO / "packages" / "sbir-analytics" / "sbir_analytics" / "assets" / "transition_report.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("_transition_report_asset", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


def test_cohort_metrics_flattens_summary_and_composition(mod):
    summary = {
        "_epistemic": {"tier": "exploratory", "citable": False},
        "area_id": "quantum_information_science",
        "cohort_profile": "tech-area-cohort-v1",
        "phase2_universe": 40000,
        "method_a_source": "keyword_pack",
        "method_b_source": "taxonomy",
        "overlap": {"method_b_n": 512, "intersection_n": 88, "jaccard": 0.123},
        "signals_absent": ["form_d", "ma_signal"],
        "has_deficiency_class": True,
    }
    composition = {
        "n_unique_awards": 640,
        "totals": {"phase2_dollars_m": 512.4, "unique_firms": 410},
        "by_agency": {"DoD": 300, "NSF": 200, "DOE": 140},
    }
    m = mod._cohort_metrics(summary, composition)
    assert m["area_id"] == "quantum_information_science"
    assert m["cohort_profile"] == "tech-area-cohort-v1"
    assert m["epistemic_tier"] == "exploratory"
    assert m["citable"] is False
    assert m["method_a_awards"] == 640
    assert m["method_b_awards"] == 512
    assert m["intersection"] == 88
    assert m["jaccard"] == 0.123
    assert m["phase2_dollars_m"] == 512.4
    assert m["unique_firms"] == 410
    assert m["agencies"] == 3
    assert m["signals_absent"] == 2
    assert m["has_deficiency_class"] is True


def test_cohort_metrics_tolerates_missing_blocks(mod):
    # Missing overlap / totals / by_agency must not raise; scalars degrade to None/0.
    m = mod._cohort_metrics({"area_id": "hypersonics"}, {"n_unique_awards": 0})
    assert m["area_id"] == "hypersonics"
    assert m["method_a_awards"] == 0
    assert m["method_b_awards"] is None
    assert m["jaccard"] is None
    assert m["agencies"] == 0
    assert m["signals_absent"] == 0
    assert m["has_deficiency_class"] is False


def test_repo_root_resolves_to_declared_profiles(mod):
    root = mod._repo_root()
    assert (root / "config" / "transition_reports" / "hypersonics.yaml").exists()


def test_cohort_build_calls_package_api_directly(mod, monkeypatch, tmp_path):
    calls = []

    class _Log:
        def info(self, message):
            calls.append(message)

    monkeypatch.setattr(mod, "materialize_tech_area_cohort", lambda area_id: tmp_path / area_id)

    result = mod._run_cohort_build("hypersonics", _Log())

    assert result == tmp_path / "hypersonics"
    assert any("materializing area=hypersonics" in message for message in calls)


def test_factory_wired_all_three_areas(mod):
    for area in mod.TECH_AREAS:
        assert hasattr(mod, f"tech_area_cohort_{area}")
        assert hasattr(mod, f"tech_area_cohort_{area}_nonempty")


def test_broken_registry_does_not_break_the_module_import(monkeypatch):
    """A bad registry must not abort the whole Dagster definitions load (regression)."""

    import sbir_etl.analysis.registry as registry

    def _boom(*args, **kwargs):
        raise ValueError("unknown analysis_kind")

    monkeypatch.setattr(registry, "load_registry", _boom)

    degraded = _load_module()

    assert degraded.TECH_AREAS == ()
    assert not hasattr(degraded, "tech_area_cohort_hypersonics")
