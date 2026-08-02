"""Tests for the source-download jobs that replace data-refresh.yml.

Verifies the jobs are discoverable, that their schedules inherit the crons the
workflow used, and that they default to STOPPED per the Mac mini runbook.
"""

import pytest
from dagster import DefaultScheduleStatus

# Cron times carried over from .github/workflows/data-refresh.yml.
EXPECTED_SCHEDULES = {
    "weekly_sbir_awards_download": "0 9 * * 1",
    "monthly_sam_gov_download": "0 3 15 * *",
    "monthly_usaspending_download": "0 2 6 * *",
    "monthly_uspto_download": "0 9 1 * *",
}

EXPECTED_JOBS = {
    "sbir_awards_download_job",
    "sam_gov_download_job",
    "usaspending_download_job",
    "uspto_download_job",
}


@pytest.fixture(scope="module")
def schedules():
    from sbir_analytics.definitions import schedules as all_schedules

    return {s.name: s for s in all_schedules}


class TestJobsAreDiscovered:
    def test_all_download_jobs_exposed(self):
        from sbir_analytics.assets.jobs import source_downloads

        assert EXPECTED_JOBS == set(source_downloads.__all__)

    def test_jobs_registered_in_definitions(self):
        from sbir_analytics.definitions import auto_jobs

        assert EXPECTED_JOBS <= set(auto_jobs)


class TestSchedules:
    @pytest.mark.parametrize(("name", "cron"), sorted(EXPECTED_SCHEDULES.items()))
    def test_cron_matches_data_refresh_workflow(self, schedules, name, cron):
        assert schedules[name].cron_schedule == cron

    @pytest.mark.parametrize("name", sorted(EXPECTED_SCHEDULES))
    def test_defaults_to_stopped(self, schedules, name):
        # The runbook requires a successful manual run before enabling any of
        # these on the always-on host.
        assert schedules[name].default_status is DefaultScheduleStatus.STOPPED

    @pytest.mark.parametrize("name", sorted(EXPECTED_SCHEDULES))
    def test_schedule_present(self, schedules, name):
        assert name in schedules


class TestDataRoot:
    def test_defaults_to_data(self, monkeypatch):
        from sbir_analytics.assets.jobs.source_downloads import DATA_ROOT_ENV, _data_root

        monkeypatch.delenv(DATA_ROOT_ENV, raising=False)
        assert str(_data_root()) == "data"

    def test_honours_env_override(self, monkeypatch):
        from sbir_analytics.assets.jobs.source_downloads import DATA_ROOT_ENV, _data_root

        monkeypatch.setenv(DATA_ROOT_ENV, "/Volumes/SSDmini/sbir-analytics/data")
        assert str(_data_root()) == "/Volumes/SSDmini/sbir-analytics/data"


class TestSamGovOpGuards:
    def test_missing_api_key_raises(self, monkeypatch):
        from dagster import build_op_context

        from sbir_analytics.assets.jobs.source_downloads import download_sam_gov_op

        monkeypatch.delenv("SAM_GOV_API_KEY", raising=False)
        with pytest.raises(ValueError, match="SAM_GOV_API_KEY"):
            download_sam_gov_op(build_op_context())


EXPECTED_SENSORS = {
    "sbir_pipeline_after_download",
    "uspto_pipeline_after_download",
    "usaspending_pipeline_after_download",
}


class TestPipelineChaining:
    """Sensors that replace etl-pipeline.yml's weekly pipeline runs."""

    @pytest.fixture(scope="class")
    def sensors(self):
        from sbir_analytics.definitions import all_sensors

        return {s.name: s for s in all_sensors}

    @pytest.mark.parametrize("name", sorted(EXPECTED_SENSORS))
    def test_sensor_registered(self, sensors, name):
        assert name in sensors

    @pytest.mark.parametrize("name", sorted(EXPECTED_SENSORS))
    def test_defaults_to_stopped(self, sensors, name):
        from dagster import DefaultSensorStatus

        assert sensors[name].default_status is DefaultSensorStatus.STOPPED


class TestHtmlShellGuard:
    """USPTO serves an HTML shell with HTTP 200 to unauthenticated clients."""

    def test_rejects_html_masquerading_as_data(self, tmp_path):
        from sbir_analytics.assets.jobs.source_downloads import _guard_html_shell

        f = tmp_path / "patent.zip"
        f.write_bytes(b"<!DOCTYPE html>\n<html><body>Sign in</body></html>")

        with pytest.raises(ValueError, match="HTML page rather than data"):
            _guard_html_shell(f)

        assert not f.exists()  # the bad file is removed, not left to poison a run

    def test_rejects_implausibly_small_binary(self, tmp_path):
        from sbir_analytics.assets.jobs.source_downloads import _guard_html_shell

        f = tmp_path / "patent.zip"
        f.write_bytes(b"PK\x03\x04short")

        with pytest.raises(ValueError, match="implausibly small"):
            _guard_html_shell(f)

    def test_accepts_plausible_download(self, tmp_path):
        from sbir_analytics.assets.jobs.source_downloads import (
            MIN_PLAUSIBLE_DOWNLOAD_BYTES,
            _guard_html_shell,
        )

        f = tmp_path / "patent.zip"
        f.write_bytes(b"PK\x03\x04" + b"\x00" * MIN_PLAUSIBLE_DOWNLOAD_BYTES)

        _guard_html_shell(f)  # must not raise
