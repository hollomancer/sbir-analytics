"""Contracts for the Dagster definition entry points."""

from __future__ import annotations

import os
import subprocess
import sys

import pytest


pytestmark = pytest.mark.fast


@pytest.mark.parametrize(
    ("module_name", "load_heavy"),
    [
        ("sbir_analytics.definitions", "false"),
        ("sbir_analytics.definitions", "true"),
        ("sbir_analytics.definitions_ml", "false"),
    ],
)
def test_definition_entry_points_validate_in_fresh_processes(module_name, load_heavy):
    """Each supported code-location entry point must resolve independently."""

    code = f"""
import importlib
import os
from dagster import Definitions

module = importlib.import_module({module_name!r})
Definitions.validate_loadable(module.defs)
if {module_name!r} == "sbir_analytics.definitions_ml":
    assert os.environ["DAGSTER_LOAD_HEAVY_ASSETS"] == "false"
"""
    env = os.environ.copy()
    env["DAGSTER_LOAD_HEAVY_ASSETS"] = load_heavy
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


_HEAVY_JOBS = {
    "cet_full_pipeline_job",
    "fiscal_returns_full_job",
    "fiscal_returns_mvp_job",
    "modernbert_job",
    "uspto_ai_extraction_job",
}


def _registered_names(defs):
    repo = defs.get_repository_def()
    return {
        "assets": {key.to_user_string() for key in repo.asset_graph.get_all_asset_keys()},
        "checks": {str(key) for key in repo.asset_graph.asset_check_keys},
        "jobs": {job.name for job in repo.get_all_jobs() if not job.name.startswith("__")},
        "schedules": {schedule.name for schedule in repo.schedule_defs},
        "sensors": {sensor.name for sensor in repo.sensor_defs},
    }


def test_ml_entry_point_matches_primary_with_heavy_assets_loaded(monkeypatch):
    """definitions_ml must register what primary registers with heavy loading on."""

    from sbir_analytics.definitions_factory import build_definitions

    monkeypatch.setenv("DAGSTER_LOAD_HEAVY_ASSETS", "true")
    primary = _registered_names(build_definitions("primary").defs)
    heavy = _registered_names(build_definitions("heavy").defs)

    assert heavy == primary
    assert _HEAVY_JOBS <= heavy["jobs"]


def test_ml_entry_point_keeps_heavy_jobs_when_toggle_is_false():
    """The make targets that name definitions_ml must work on a constrained host."""

    code = f"""
import os
from sbir_analytics import definitions_ml

repo = definitions_ml.defs.get_repository_def()
names = {{job.name for job in repo.get_all_jobs()}}
missing = {sorted(_HEAVY_JOBS)!r}
missing = [name for name in missing if name not in names]
assert not missing, missing
assert os.environ["DAGSTER_LOAD_HEAVY_ASSETS"] == "false"
"""
    env = os.environ.copy()
    env["DAGSTER_LOAD_HEAVY_ASSETS"] = "false"
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_unoperated_cet_schedules_are_not_registered():
    """The CET jobs stay runnable by hand; their unowned daily schedules are gone."""

    from sbir_analytics import definitions

    schedule_names = {schedule.name for schedule in definitions.bundle.schedules}
    assert not schedule_names & {
        "daily_cet_full_pipeline",
        "daily_cet_drift_detection",
        "weekly_fiscal_returns",
    }
