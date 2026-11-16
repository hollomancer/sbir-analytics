"""Contracts for the primary and heavy Dagster definition profiles."""

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


def test_heavy_profile_preserves_filtered_jobs_and_schedules(monkeypatch):
    """The shared builder must retain the existing secondary-location contract."""

    monkeypatch.setenv("DAGSTER_LOAD_HEAVY_ASSETS", "false")
    from sbir_analytics.definitions_factory import build_definitions

    bundle = build_definitions("heavy")

    assert {job.name for job in bundle.job_definitions} == {
        "cet_full_pipeline_job",
        "fiscal_returns_full_job",
        "fiscal_returns_mvp_job",
        "modernbert_job",
        "uspto_ai_extraction_job",
        "uspto_download_job",
        "uspto_validation_job",
    }
    assert {(schedule.name, schedule.cron_schedule) for schedule in bundle.schedules} == {
        ("daily_cet_full_pipeline", "0 3 * * *"),
        ("weekly_fiscal_returns", "0 4 * * 1"),
    }
    assert os.environ["DAGSTER_LOAD_HEAVY_ASSETS"] == "false"
