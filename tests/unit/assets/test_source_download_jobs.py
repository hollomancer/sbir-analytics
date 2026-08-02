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
