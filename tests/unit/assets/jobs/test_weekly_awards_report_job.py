"""Guards for the weekly awards report job carried over from weekly.yml."""

import pytest

pytestmark = [pytest.mark.fast, pytest.mark.unit]


def test_job_is_discovered_and_scheduled():
    """The job must be auto-discovered and hold weekly.yml's Monday 12:00 slot."""
    from sbir_analytics.definitions import auto_jobs, source_download_schedules

    assert "weekly_awards_report_job" in auto_jobs

    schedule = next(s for s in source_download_schedules if s.name == "weekly_awards_report")
    assert schedule.cron_schedule == "0 12 * * 1"


def test_schedule_defaults_to_stopped():
    """Runbook convention: an operator confirms a manual run before enabling."""
    from dagster import DefaultScheduleStatus

    from sbir_analytics.definitions import source_download_schedules

    schedule = next(s for s in source_download_schedules if s.name == "weekly_awards_report")
    assert schedule.default_status == DefaultScheduleStatus.STOPPED


def test_empty_report_fails_rather_than_passing_silently(tmp_path, monkeypatch):
    """An exit-0 run that writes nothing must raise, not report success.

    The script can exit 0 having produced no report. Trusting the exit code
    would reproduce the failure mode that kept weekly.yml broken unnoticed.
    """
    from dagster import build_op_context

    from sbir_analytics.assets.jobs import weekly_awards_report as mod

    monkeypatch.setenv(mod.DATA_ROOT_ENV, str(tmp_path))

    class _Result:
        returncode = 0
        stderr = ""
        stdout = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Result())

    with pytest.raises(FileNotFoundError, match="wrote no report"):
        mod.generate_weekly_awards_report_op(build_op_context())


def test_nonzero_exit_raises(tmp_path, monkeypatch):
    """A failing script must surface as a job failure, not a quiet no-op."""
    from dagster import build_op_context

    from sbir_analytics.assets.jobs import weekly_awards_report as mod

    monkeypatch.setenv(mod.DATA_ROOT_ENV, str(tmp_path))

    class _Result:
        returncode = 2
        stderr = "boom"
        stdout = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Result())

    with pytest.raises(RuntimeError, match="exit code 2"):
        mod.generate_weekly_awards_report_op(build_op_context())
