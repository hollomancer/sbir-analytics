"""Layer-3 execution tests for weekly_awards_report_job (PR-time variant).

The existing tests cover discovery, the cron, the stopped default, and the op's
error branches in isolation. All of those passed while the job was in fact
unable to run: executing it for real raised `FileNotFoundError: Could not
resolve SBIR awards CSV`, because the job depends on a vintage that
`weekly_sbir_awards_download` produces.

These run the job *graph* end to end via execute_in_process with the report
builder mocked, so they stay unit-fast and run on every PR. The companion test
in tests/integration invokes the real builder.

The seam is `WeeklyAwardsReportBuilder` rather than `subprocess`: the op calls
the package API directly now that the script bridge is gone. The contract each
test pins is unchanged.
"""

import pytest

pytestmark = [pytest.mark.fast, pytest.mark.unit]


def _builder_returning(report: str):
    """A stand-in builder whose run() yields ``report``."""

    class _Builder:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def run(self):
            return report

    return _Builder


def test_job_succeeds_and_writes_a_dated_report(tmp_path, monkeypatch):
    """Happy path: the job writes to <data_root>/reports/weekly_awards/<date>/."""
    from sbir_analytics.assets.jobs import weekly_awards_report as mod

    monkeypatch.setenv(mod.DATA_ROOT_ENV, str(tmp_path))
    monkeypatch.setattr(mod, "WeeklyAwardsReportBuilder", _builder_returning("# Weekly awards\n"))

    result = mod.weekly_awards_report_job.execute_in_process()
    assert result.success

    written = list((tmp_path / "reports" / "weekly_awards").glob("*/weekly-awards.md"))
    assert len(written) == 1, f"expected one dated report, found {written}"
    assert written[0].read_text().startswith("# Weekly awards")


def test_job_fails_when_the_builder_produces_nothing(tmp_path, monkeypatch):
    """A successful build that produced no report must fail the job, not pass it.

    This is the regression guard for the failure mode that unit-level mocking
    of the op alone would not catch at the graph level.
    """
    from sbir_analytics.assets.jobs import weekly_awards_report as mod

    monkeypatch.setenv(mod.DATA_ROOT_ENV, str(tmp_path))
    monkeypatch.setattr(mod, "WeeklyAwardsReportBuilder", _builder_returning(""))

    with pytest.raises(Exception):  # noqa: B017 - Dagster wraps the op failure
        mod.weekly_awards_report_job.execute_in_process()


def test_job_fails_when_the_builder_raises(tmp_path, monkeypatch):
    from sbir_analytics.assets.jobs import weekly_awards_report as mod

    class _Exploding:
        def __init__(self, **kwargs):
            pass

        def run(self):
            raise RuntimeError("boom")

    monkeypatch.setenv(mod.DATA_ROOT_ENV, str(tmp_path))
    monkeypatch.setattr(mod, "WeeklyAwardsReportBuilder", _Exploding)

    with pytest.raises(Exception):  # noqa: B017 - Dagster wraps the op failure
        mod.weekly_awards_report_job.execute_in_process()
