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


class TestSamGovOp:
    def test_keyless_bulk_writes_canonical_snapshot(self, monkeypatch, tmp_path):
        import pandas as pd
        from dagster import build_op_context

        from scripts.data import download_sam_gov as download_module
        from sbir_analytics.assets.jobs.source_downloads import (
            DATA_ROOT_ENV,
            download_sam_gov_op,
        )

        monkeypatch.delenv("SAM_GOV_API_KEY", raising=False)
        monkeypatch.setenv(DATA_ROOT_ENV, str(tmp_path))
        frame = pd.DataFrame({"unique_entity_id": ["CANDIDATE001"]})
        monkeypatch.setattr(download_module, "_download_bulk_extract", lambda: frame)

        result = download_sam_gov_op(build_op_context())

        assert result == {
            "rows": 1,
            "path": str(tmp_path / "raw/sam_gov/sam_entity_records.parquet"),
            "partial": False,
        }
        assert (tmp_path / "raw/sam_gov/sam_entity_records.parquet").is_file()


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


class TestAssignmentArchiveHandoff:
    """Downstream USPTO assets discover .csv, not .csv.zip."""

    def test_archives_are_extracted_in_place(self, tmp_path):
        import zipfile

        from dagster import build_op_context

        from sbir_analytics.assets.jobs.source_downloads import _extract_assignment_archives

        archive = tmp_path / "assignment.csv.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("assignment.csv", "rf_id,x\n1,2\n")

        extracted = _extract_assignment_archives(build_op_context(), tmp_path)

        assert extracted == ["assignment.csv"]
        assert (tmp_path / "assignment.csv").read_text().startswith("rf_id")

    def test_no_archives_is_not_an_error(self, tmp_path):
        from dagster import build_op_context

        from sbir_analytics.assets.jobs.source_downloads import _extract_assignment_archives

        assert _extract_assignment_archives(build_op_context(), tmp_path) == []


class TestUnchangedDetection:
    """The sensor guard reads step-output metadata, not materializations."""

    def _ctx(self, metadata):
        from unittest.mock import MagicMock

        event = MagicMock()
        event.event_specific_data.metadata = metadata
        event.event_specific_data.materialization = None
        record = MagicMock()
        record.dagster_event = event
        ctx = MagicMock()
        ctx.instance.all_logs.return_value = [record]
        ctx.dagster_run.run_id = "r1"
        return ctx

    def test_changed_false_is_detected(self):
        from sbir_analytics.assets.sensors.source_download_chaining import (
            _download_was_unchanged,
        )

        assert _download_was_unchanged(self._ctx({"changed": False})) is True

    def test_changed_true_runs_pipeline(self):
        from sbir_analytics.assets.sensors.source_download_chaining import (
            _download_was_unchanged,
        )

        assert _download_was_unchanged(self._ctx({"changed": True})) is False

    def test_usaspending_skipped_is_detected(self):
        from sbir_analytics.assets.sensors.source_download_chaining import (
            _download_was_unchanged,
        )

        assert _download_was_unchanged(self._ctx({"status": "skipped"})) is True

    def test_usaspending_success_runs_pipeline(self):
        from sbir_analytics.assets.sensors.source_download_chaining import (
            _download_was_unchanged,
        )

        assert _download_was_unchanged(self._ctx({"status": "success"})) is False
