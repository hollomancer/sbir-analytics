"""Layer-3 execution tests for the four host source-download jobs.

The existing coverage is layers 1 and 2: `test_host_schedules.py` proves each
schedule names a real job, and `test_source_download_jobs.py` exercises ops in
isolation with `build_op_context`. That combination is exactly what
`specs/actions-migration-followups/remaining-dagster-migrations.md` records as
insufficient — `weekly_awards_report_job` held five passing tests at those two
layers while being unable to run at all.

These run each job *graph* through `execute_in_process` with the package API
mocked, so they stay unit-fast. What they pin is the wiring the ops own rather
than the downloaders' behaviour: that each op routes its destination through
`_data_root()`, and that the guards which turn a "successful" fetch into a
failure actually fire when the job runs.

Destination routing is the specific thing worth a graph-level test. Promoting
these downloaders out of `scripts/` changed what every op calls, and a
regression that sent a fetch to a path outside the configured data root would
leave every unit test passing and quietly write to the wrong volume on the
server.
"""

from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast, pytest.mark.unit]


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """Point the jobs at an isolated data root."""
    from sbir_analytics.assets.jobs import source_downloads as mod

    monkeypatch.setenv(mod.DATA_ROOT_ENV, str(tmp_path))
    return tmp_path


def test_sbir_awards_job_routes_the_destination_through_the_data_root(data_root, monkeypatch):
    from sbir_analytics.assets.jobs import source_downloads as mod

    seen: dict[str, Path] = {}

    def _fake(destination: Path) -> dict:
        seen["destination"] = destination
        return {"changed": True, "path": str(destination / "award_data.csv"), "sha256": "a" * 64}

    monkeypatch.setattr(mod, "download_sbir_awards", _fake)

    result = mod.sbir_awards_download_job.execute_in_process()

    assert result.success
    assert seen["destination"] == data_root / "raw" / "sbir"


def test_usaspending_job_routes_the_destination_through_the_data_root(data_root, monkeypatch):
    from sbir_analytics.assets.jobs import source_downloads as mod

    seen: dict[str, Path] = {}

    def _fake(destination: Path) -> dict:
        seen["destination"] = destination
        return {"status": "downloaded", "path": str(destination / "dump.zip"), "size": 1}

    monkeypatch.setattr(mod, "download_local", _fake)

    result = mod.usaspending_download_job.execute_in_process()

    assert result.success
    assert seen["destination"] == data_root / "usaspending"


def test_sam_gov_job_counts_the_rows_it_actually_wrote(data_root, monkeypatch):
    """The op reports `rows` by reading the parquet back, not by trusting a count."""
    import pandas as pd

    from sbir_analytics.assets.jobs import source_downloads as mod
    from sbir_etl.extractors.source_downloads import sam_gov

    seen: dict[str, Path] = {}

    def _fake(destination: Path) -> Path:
        seen["destination"] = destination
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / "sam_public.parquet"
        pd.DataFrame({"uei": ["A" * 12, "B" * 12, "C" * 12]}).to_parquet(path)
        return path

    monkeypatch.setattr(sam_gov, "download_sam_public_extract", _fake)

    result = mod.sam_gov_download_job.execute_in_process()

    assert result.success
    assert seen["destination"] == data_root / "raw" / "sam_gov"
    assert result.output_for_node("download_sam_gov_op")["rows"] == 3


def test_uspto_job_fails_without_an_api_key(data_root, monkeypatch):
    """The keyless path stopped working on 2026-06-18; the job must say so."""
    from sbir_analytics.assets.jobs import source_downloads as mod

    monkeypatch.delenv("USPTO_ODP_API_KEY", raising=False)

    result = mod.uspto_download_job.execute_in_process(raise_on_error=False)

    assert not result.success
    failure = result.failure_data_for_node("download_uspto_op")
    assert "USPTO_ODP_API_KEY" in failure.error.cause.message


def test_uspto_job_fails_when_an_assignment_file_fails(data_root, monkeypatch):
    """`download_assignments` records per-file errors instead of raising.

    Without the op's own check the job would report success while holding a
    partial assignment set, which is the failure mode the guard exists for.
    """
    from sbir_analytics.assets.jobs import source_downloads as mod
    from sbir_etl.extractors.source_downloads import uspto, uspto_browser

    monkeypatch.setenv("USPTO_ODP_API_KEY", "test-key")
    monkeypatch.setattr(uspto, "create_session_with_retries", lambda: object())

    def _write_plausible_file(*args, **kwargs):
        destination = next(a for a in args if isinstance(a, Path))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"0" * (mod.MIN_PLAUSIBLE_DOWNLOAD_BYTES + 1))
        return {"status": "downloaded"}

    monkeypatch.setattr(uspto, "download_odp_file", _write_plausible_file)
    monkeypatch.setattr(uspto, "stream_download", _write_plausible_file)

    async def _partial_failure(output_dir: Path):
        return [{"file": "assignment", "error": "403 Forbidden"}]

    monkeypatch.setattr(uspto_browser, "download_assignments", _partial_failure)

    result = mod.uspto_download_job.execute_in_process(raise_on_error=False)

    assert not result.success
    failure = result.failure_data_for_node("download_uspto_op")
    assert "403 Forbidden" in failure.error.cause.message


def test_uspto_job_fails_when_no_assignment_file_is_produced(data_root, monkeypatch):
    """An empty result set is a failed download, not an empty success."""
    from sbir_analytics.assets.jobs import source_downloads as mod
    from sbir_etl.extractors.source_downloads import uspto, uspto_browser

    monkeypatch.setenv("USPTO_ODP_API_KEY", "test-key")
    monkeypatch.setattr(uspto, "create_session_with_retries", lambda: object())

    def _write_plausible_file(*args, **kwargs):
        destination = next(a for a in args if isinstance(a, Path))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"0" * (mod.MIN_PLAUSIBLE_DOWNLOAD_BYTES + 1))
        return {"status": "downloaded"}

    monkeypatch.setattr(uspto, "download_odp_file", _write_plausible_file)
    monkeypatch.setattr(uspto, "stream_download", _write_plausible_file)

    async def _no_files(output_dir: Path):
        return []

    monkeypatch.setattr(uspto_browser, "download_assignments", _no_files)

    result = mod.uspto_download_job.execute_in_process(raise_on_error=False)

    assert not result.success
    failure = result.failure_data_for_node("download_uspto_op")
    assert "no files" in failure.error.cause.message
