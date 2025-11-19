"""End-to-end smoke test for SBIR enrichment via Dagster job."""

from __future__ import annotations

import pytest
from dagster import materialize_from_jobs

from src.assets.jobs.usaspending_iterative_job import usaspending_iterative_enrichment_job


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def test_usaspending_enrichment_job_smoke(tmp_path, monkeypatch):
    """Materialize the iterative enrichment job and assert it succeeds."""

    # Run in temporary working directory to avoid polluting repo
    monkeypatch.chdir(tmp_path)
    result = materialize_from_jobs(
        jobs=[usaspending_iterative_enrichment_job],
        raise_on_error=True,
    )

    assert result.success, "Enrichment job failed"
