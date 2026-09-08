"""Fast contracts for the complete Dagster code location."""

import pytest
from dagster import AssetKey, DefaultScheduleStatus, Definitions

from sbir_analytics import definitions


pytestmark = pytest.mark.fast


def test_definitions_are_loadable():
    """The registered assets, jobs, checks, schedules, and sensors resolve."""
    Definitions.validate_loadable(definitions.defs)


def test_cet_drift_job_selects_only_the_drift_asset():
    """Keep the reconstructed Layer-3 job in lockstep with the production selection."""
    assert definitions.cet_drift_job is not None
    job = definitions.defs.resolve_job_def("cet_drift_job")
    assert job.asset_layer.executable_asset_keys == {
        AssetKey(["ml", "validated_cet_drift_detection"])
    }


def test_source_download_schedule_contracts():
    """Host download schedules retain their reviewed cadence and safe status."""
    expected_crons = {
        "weekly_sbir_awards_download": "0 9 * * 1",
        "monthly_sam_gov_download": "0 3 15 * *",
        "monthly_usaspending_download": "0 2 6 * *",
        "monthly_uspto_download": "0 9 1 * *",
        "monthly_phase_transition": "0 14 1 * *",
        "weekly_awards_report": "0 12 * * 1",
    }
    schedules = {schedule.name: schedule for schedule in definitions.source_download_schedules}

    assert schedules.keys() == expected_crons.keys()
    for name, cron in expected_crons.items():
        assert schedules[name].cron_schedule == cron
        assert schedules[name].default_status == DefaultScheduleStatus.STOPPED


def test_expected_sensors_are_registered():
    sensor_names = {sensor.name for sensor in definitions.all_sensors}

    assert "usaspending_refresh_sensor" in sensor_names
    assert "sbir_pipeline_after_download" in sensor_names
    assert "uspto_pipeline_after_download" in sensor_names
    assert "usaspending_pipeline_after_download" in sensor_names
