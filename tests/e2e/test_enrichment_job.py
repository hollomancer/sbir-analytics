"""End-to-end smoke test for SBIR enrichment via Dagster job."""

from __future__ import annotations

import pytest
from dagster import materialize

from src.assets.jobs.usaspending_iterative_job import usaspending_iterative_enrichment_job
from src.definitions import defs


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def test_usaspending_enrichment_job_smoke(tmp_path, monkeypatch):
    """Materialize the iterative enrichment job and assert it succeeds."""

    # Run in temporary working directory to avoid polluting repo
    monkeypatch.chdir(tmp_path)

    # Resolve job assets and materialize them
    selection = usaspending_iterative_enrichment_job.selection
    resolved_assets = selection.resolve(defs.assets)

    result = materialize(
        resolved_assets,
        raise_on_error=True,
    )

    assert result.success, "Enrichment job failed"
