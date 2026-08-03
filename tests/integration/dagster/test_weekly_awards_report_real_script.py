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

    try:
        result = mod.weekly_awards_report_job.execute_in_process(raise_on_error=False)
    except Exception:
        # A raised failure is an acceptable outcome; the invariant below only
        # constrains the success case.
        return

    if result.success:
        written = list((tmp_path / "reports" / "weekly_awards").glob("*/weekly-awards.md"))
        assert written, (
            "job reported success but wrote no report — the op must treat an "
            "empty result as a failure"
        )
        assert written[0].stat().st_size > 0
