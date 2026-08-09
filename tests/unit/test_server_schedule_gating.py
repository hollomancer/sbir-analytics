"""Tests for server schedule gating in sbir_analytics.definitions.

The repository-wide all-assets schedule must remain absent, and the weekly core
refresh must stay STOPPED until explicitly enabled.

These import the real Dagster definitions module, so they run wherever the
`sbir_analytics` package and Dagster are installed (CI), not in the fast smoke.
"""

import importlib

import pytest


pytestmark = pytest.mark.unit

dagster = pytest.importorskip("dagster")
DefaultScheduleStatus = dagster.DefaultScheduleStatus


def _reload_definitions(monkeypatch, **env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    import sbir_analytics.definitions as definitions

    return importlib.reload(definitions)


def _schedule(defs_module, name):
    for sched in defs_module.schedules:
        if sched.name == name:
            return sched
    raise AssertionError(f"schedule {name!r} not found")


def test_schedule_status_helper(monkeypatch):
    defs = _reload_definitions(monkeypatch)
    status = defs._schedule_status

    monkeypatch.setenv("X_TOGGLE", "true")
    assert status("X_TOGGLE", default_running=False) == DefaultScheduleStatus.RUNNING
    monkeypatch.setenv("X_TOGGLE", "false")
    assert status("X_TOGGLE", default_running=True) == DefaultScheduleStatus.STOPPED
    monkeypatch.delenv("X_TOGGLE", raising=False)
    assert status("X_TOGGLE", default_running=True) == DefaultScheduleStatus.RUNNING
    assert status("X_TOGGLE", default_running=False) == DefaultScheduleStatus.STOPPED


def test_weekly_core_refresh_exists_and_stopped_by_default(monkeypatch):
    defs = _reload_definitions(
        monkeypatch,
        SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_CORE_REFRESH_ENABLED=None,
    )
    weekly = _schedule(defs, "weekly_core_refresh")
    assert weekly.default_status == DefaultScheduleStatus.STOPPED


def test_weekly_core_refresh_opt_in(monkeypatch):
    defs = _reload_definitions(
        monkeypatch,
        SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_CORE_REFRESH_ENABLED="true",
    )
    weekly = _schedule(defs, "weekly_core_refresh")
    assert weekly.default_status == DefaultScheduleStatus.RUNNING


def test_repository_wide_job_and_schedule_are_retired(monkeypatch):
    defs = _reload_definitions(monkeypatch)

    assert "sbir_analytics_job" not in {job.name for job in defs.job_definitions}
    assert "daily_sbir_analytics" not in {schedule.name for schedule in defs.schedules}


@pytest.mark.parametrize(
    ("load_heavy", "heavy_jobs_present"),
    [("false", False), ("true", True)],
)
def test_definitions_are_loadable_with_matching_jobs(monkeypatch, load_heavy, heavy_jobs_present):
    defs = _reload_definitions(monkeypatch, DAGSTER_LOAD_HEAVY_ASSETS=load_heavy)

    dagster.Definitions.validate_loadable(defs.defs)
    job_names = set(defs.auto_jobs)
    for job_name in (
        "cet_full_pipeline_job",
        "fiscal_returns_mvp_job",
        "modernbert_job",
        "uspto_ai_extraction_job",
    ):
        assert (job_name in job_names) is heavy_jobs_present
