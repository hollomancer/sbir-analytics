"""Layer-3 execution tests for phase_transition_archive_job.

The job had no test at any layer while `sbir_etl/reporting/phase_transition_analysis.py`
was promoted out of `scripts/` and the op rewired to call it directly.

What is worth pinning here is the staleness guard rather than the copy itself.
The archive replaces an S3 publish step that gave the analysis a dated history,
and the op's own docstring states the risk: without a freshness check it would
"capture whatever stale report happened to be on disk", producing a dated
snapshot that silently mixes fresh parquet with an old report. A dated archive
that looks complete but isn't is worse than a failed run, because nothing
downstream can tell the difference later.

The op resolves its *sources* relative to the working directory and its
*destination* through the data root, so these tests chdir into a tmp path and
set the data-root env var.
"""

import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast, pytest.mark.unit]


def _write_outputs(root: Path, *, names=None) -> None:
    """Create the archived output set under `root`."""
    from sbir_analytics.assets.jobs import phase_transition_archive as mod

    for relative in names if names is not None else mod.ARCHIVED_OUTPUTS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Run the job with sources under cwd and the archive under the data root."""
    from sbir_analytics.assets.jobs import phase_transition_archive as mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(mod.DATA_ROOT_ENV, str(tmp_path / "data-root"))
    return tmp_path


def _archive_dir(workspace: Path) -> Path:
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    return workspace / "data-root" / "processed" / "phase_transition" / "history" / date_str


def test_job_archives_every_output_the_run_produced(workspace, monkeypatch):
    from sbir_analytics.assets.jobs import phase_transition_archive as mod

    monkeypatch.setattr(
        mod, "generate_phase_transition_report", lambda *args: _write_outputs(workspace)
    )

    result = mod.phase_transition_archive_job.execute_in_process()

    assert result.success
    archived = sorted(p.name for p in _archive_dir(workspace).iterdir())
    assert archived == sorted(Path(rel).name for rel in mod.ARCHIVED_OUTPUTS)


def test_job_copies_rather_than_moves(workspace, monkeypatch):
    """Canonical paths stay put; the archive is an additional snapshot."""
    from sbir_analytics.assets.jobs import phase_transition_archive as mod

    monkeypatch.setattr(
        mod, "generate_phase_transition_report", lambda *args: _write_outputs(workspace)
    )

    assert mod.phase_transition_archive_job.execute_in_process().success

    for relative in mod.ARCHIVED_OUTPUTS:
        assert (workspace / relative).is_file(), f"{relative} was moved, not copied"


def test_job_fails_when_an_expected_output_is_missing(workspace, monkeypatch):
    from sbir_analytics.assets.jobs import phase_transition_archive as mod

    incomplete = [rel for rel in mod.ARCHIVED_OUTPUTS if not rel.endswith("_report.json")]
    monkeypatch.setattr(
        mod,
        "generate_phase_transition_report",
        lambda *args: _write_outputs(workspace, names=incomplete),
    )

    result = mod.phase_transition_archive_job.execute_in_process(raise_on_error=False)

    assert not result.success
    message = result.failure_data_for_node(
        "archive_phase_transition_outputs_op"
    ).error.cause.message
    # Assert the op's own refusal, not just the filename: a plain crash from
    # stat() or copy2() also names the missing path, so matching on the path
    # alone cannot tell a deliberate guard from an incidental traceback.
    assert "Refusing to archive an incomplete or stale phase-transition snapshot" in message
    assert "Missing: reports/phase_transition/phase_transition_report.json" in message
    # Nothing is copied until the whole set validates, so a failed run leaves
    # no dated directory a later reader could mistake for a complete snapshot.
    assert not _archive_dir(workspace).exists()


def test_job_fails_on_a_stale_output_rather_than_archiving_it(workspace, monkeypatch):
    """A file left from an earlier run must not ride along into a dated snapshot.

    This is the guard the op exists for: the parquet is regenerated upstream but
    the report is written by this job, so a run that silently skipped the report
    would otherwise archive last month's alongside this month's data.
    """
    from sbir_analytics.assets.jobs import phase_transition_archive as mod

    stale = "reports/phase_transition/phase_transition_report.json"
    stale_path = workspace / stale
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_path.write_text("{}")
    old = time.time() - 86_400
    import os

    os.utime(stale_path, (old, old))

    fresh = [rel for rel in mod.ARCHIVED_OUTPUTS if rel != stale]
    monkeypatch.setattr(
        mod,
        "generate_phase_transition_report",
        lambda *args: _write_outputs(workspace, names=fresh),
    )

    result = mod.phase_transition_archive_job.execute_in_process(raise_on_error=False)

    assert not result.success
    message = result.failure_data_for_node(
        "archive_phase_transition_outputs_op"
    ).error.cause.message
    assert "Refusing to archive an incomplete or stale phase-transition snapshot" in message
    assert "Not written by this run" in message
    assert stale in message
