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


def test_ml_entry_point_aliases_primary_definitions():
    """The retired heavy location must re-export the primary defs, not build its own."""

    from sbir_analytics import definitions, definitions_ml

    assert definitions_ml.defs is definitions.defs


def test_unoperated_cet_schedules_are_not_registered():
    """The CET jobs stay runnable by hand; their unowned daily schedules are gone."""

    from sbir_analytics import definitions

    schedule_names = {schedule.name for schedule in definitions.bundle.schedules}
    assert not schedule_names & {
        "daily_cet_full_pipeline",
        "daily_cet_drift_detection",
        "weekly_fiscal_returns",
    }
