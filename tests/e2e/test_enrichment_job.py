"""End-to-end smoke test for SBIR enrichment via Dagster job."""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.e2e, pytest.mark.slow, pytest.mark.requires_api]


def test_usaspending_enrichment_job_smoke(tmp_path, monkeypatch):
    """Materialize the iterative enrichment job and assert it succeeds.

    Requires dagster, sbir_analytics, and real data files to be available.
    """
    defs = pytest.importorskip("sbir_analytics.definitions").defs

    # Run in temporary working directory to avoid polluting repo
    monkeypatch.chdir(tmp_path)

    # Get the resolved job from defs
    job = defs.get_job_def("usaspending_iterative_enrichment_job")

    # Execute the job
    result = job.execute_in_process()

    assert result.success, "Enrichment job failed"
