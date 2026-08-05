"""Layer-3 execution test invoking the real script (main-time variant).

The PR-time companion in tests/unit mocks subprocess, so it verifies the job
graph but never the script. This one runs `scripts/data/weekly_awards_report.py`
for real.

The assertion is deliberately an *invariant* rather than a fixed outcome. The
script resolves the SBIR awards CSV locally and falls back to downloading it, so
the result legitimately differs by environment: with a vintage on disk or
reachable network it produces a report; without either it raises
`FileNotFoundError: Could not resolve SBIR awards CSV`. Asserting either outcome
specifically would make this flaky on whichever runner disagrees.

What must hold in *both* worlds is the contract the op exists to enforce: the
job never reports success without having written a report. That is the failure
mode that let a broken weekly.yml sit unnoticed, and it is what this pins.

The failure branch is pinned too, or the test would assert nothing at all on the
runner that takes it: the run may only fail *the way unavailable data fails*,
after the script has actually been invoked.
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def test_job_never_succeeds_without_producing_a_report(tmp_path, monkeypatch):
    from sbir_analytics.assets.jobs import weekly_awards_report as mod

    monkeypatch.setenv(mod.DATA_ROOT_ENV, str(tmp_path))
    # Keep the run bounded and offline-ish: shortest lookback, no AI calls, and
    # skip the SBIR.gov API the script offers a flag for.
    monkeypatch.setenv(mod.LOOKBACK_DAYS_ENV, "1")
    monkeypatch.setenv("SKIP_SBIR_API", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = mod.weekly_awards_report_job.execute_in_process(raise_on_error=False)

    if result.success:
        written = list((tmp_path / "reports" / "weekly_awards").glob("*/weekly-awards.md"))
        assert written, (
            "job reported success but wrote no report — the op must treat an "
            "empty result as a failure"
        )
        assert written[0].stat().st_size > 0
        return

    # Failure is a legitimate outcome, but only the *specific* failure of the
    # script running and finding no data. Accepting any failure would make this
    # test vacuous on the runner where it fails: an import error, a config
    # regression or a broken job graph would pass just as quietly. Both messages
    # below are raised by the op after the subprocess returned, so either one
    # proves the real script was reached.
    failure = result.failure_data_for_node("generate_weekly_awards_report_op")
    assert failure is not None, (
        "job failed before reaching the report op — the failure is in the job "
        "graph or op setup, not in unavailable data"
    )
    rendered = failure.error.to_string()
    assert (
        "weekly_awards_report.py failed with exit code" in rendered
        or "Report script wrote no report to" in rendered
    ), f"job failed before running the report script:\n{rendered}"
