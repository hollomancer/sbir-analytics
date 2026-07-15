"""Tests for server schedule gating in sbir_analytics.definitions.

The always-on server profile must not auto-launch the heavy daily all-assets
schedule, and the weekly core refresh must stay STOPPED until explicitly enabled.

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


def test_daily_all_assets_can_be_gated_off(monkeypatch):
    defs = _reload_definitions(
        monkeypatch,
        SBIR_ETL__DAGSTER__SCHEDULES__DAILY_ALL_ASSETS_ENABLED="false",
    )
    daily = _schedule(defs, "daily_sbir_analytics")
    assert daily.default_status == DefaultScheduleStatus.STOPPED


def test_daily_all_assets_running_by_default(monkeypatch):
    defs = _reload_definitions(
        monkeypatch,
        SBIR_ETL__DAGSTER__SCHEDULES__DAILY_ALL_ASSETS_ENABLED=None,
    )
    daily = _schedule(defs, "daily_sbir_analytics")
    assert daily.default_status == DefaultScheduleStatus.RUNNING


def test_server_definitions_resolve_without_heavy_assets(monkeypatch):
    """Every registered server job must resolve against the gated asset graph."""

    defs = _reload_definitions(monkeypatch, DAGSTER_LOAD_HEAVY_ASSETS="false")

    defs.defs.get_repository_def().load_all_definitions()
    assert "fiscal_returns_mvp_job" not in defs.auto_jobs
    assert "cet_full_pipeline_job" not in defs.auto_jobs
    assert "modernbert_job" not in defs.auto_jobs
    assert "uspto_ai_extraction_job" not in defs.auto_jobs
