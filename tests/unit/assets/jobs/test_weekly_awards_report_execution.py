"""Layer-3 execution tests for weekly_awards_report_job (PR-time variant).

The existing tests cover discovery, the cron, the stopped default, and the op's
error branches in isolation. All of those passed while the job was in fact
unable to run: executing it for real raised `FileNotFoundError: Could not
resolve SBIR awards CSV`, because the job depends on a vintage that
`weekly_sbir_awards_download` produces.

These run the job *graph* end to end via execute_in_process with the script
mocked, so they stay unit-fast and run on every PR. The companion test in
tests/integration invokes the real script.
"""

import pytest

pytestmark = [pytest.mark.fast, pytest.mark.unit]


class _Result:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr
        self.stdout = ""


def test_job_succeeds_and_writes_a_dated_report(tmp_path, monkeypatch):
    """Happy path: the job writes to <data_root>/reports/weekly_awards/<date>/."""
    from sbir_analytics.assets.jobs import weekly_awards_report as mod

    monkeypatch.setenv(mod.DATA_ROOT_ENV, str(tmp_path))

    def _fake_run(cmd, **kwargs):
        # The script writes to whatever --output it is handed; emulate that.
        out = cmd[cmd.index("--output") + 1]
        with open(out, "w") as fh:
            fh.write("# Weekly awards\n")
        return _Result()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)

    result = mod.weekly_awards_report_job.execute_in_process()
    assert result.success

    written = list((tmp_path / "reports" / "weekly_awards").glob("*/weekly-awards.md"))
    assert len(written) == 1, f"expected one dated report, found {written}"
    assert written[0].read_text().startswith("# Weekly awards")


def test_job_fails_when_the_script_writes_nothing(tmp_path, monkeypatch):
    """An exit-0 run that produced no report must fail the job, not pass it.

    This is the regression guard for the failure mode that unit-level mocking
    of the op alone would not catch at the graph level.
    """
    from sbir_analytics.assets.jobs import weekly_awards_report as mod

    monkeypatch.setenv(mod.DATA_ROOT_ENV, str(tmp_path))
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Result())

    with pytest.raises(Exception):  # noqa: B017 - Dagster wraps the op failure
        mod.weekly_awards_report_job.execute_in_process()


def test_job_fails_when_the_script_exits_nonzero(tmp_path, monkeypatch):
    from sbir_analytics.assets.jobs import weekly_awards_report as mod

    monkeypatch.setenv(mod.DATA_ROOT_ENV, str(tmp_path))
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Result(returncode=2, stderr="boom"))

    with pytest.raises(Exception):  # noqa: B017 - Dagster wraps the op failure
        mod.weekly_awards_report_job.execute_in_process()
