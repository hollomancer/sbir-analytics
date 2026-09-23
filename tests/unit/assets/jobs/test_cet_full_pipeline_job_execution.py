"""Execution tests for the CET pipeline job."""

from __future__ import annotations

import pytest
from dagster import Definitions, Output, asset


pytestmark = [pytest.mark.fast, pytest.mark.unit]


@asset(name="raw_cet_taxonomy", key_prefix=["ml"])
def _fake_cet_taxonomy() -> Output:
    return Output("stub-taxonomy")


@asset(name="enriched_cet_award_classifications", key_prefix=["ml"])
def _fake_cet_award_classifications() -> Output:
    return Output("stub-classifications")


@asset(name="transformed_cet_company_profiles", key_prefix=["ml"])
def _fake_cet_company_profiles() -> Output:
    return Output("stub-company-profiles")


@asset(name="enriched_cet_award_classifications", key_prefix=["ml"])
def _failing_cet_award_classifications() -> Output:
    raise RuntimeError("classification model unavailable")


def _defs(*, award_classifications_asset=_fake_cet_award_classifications) -> Definitions:
    from sbir_analytics.assets.jobs.cet_pipeline_job import cet_full_pipeline_job

    return Definitions(
        assets=[
            _fake_cet_taxonomy,
            award_classifications_asset,
            _fake_cet_company_profiles,
        ],
        jobs=[cet_full_pipeline_job],
    )


def test_job_wires_all_three_ops_and_succeeds(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    job = _defs().resolve_job_def("cet_full_pipeline_job")
    node_names = {node.name for node in job.nodes}
    assert node_names == {
        "ml__raw_cet_taxonomy",
        "ml__enriched_cet_award_classifications",
        "ml__transformed_cet_company_profiles",
    }

    result = job.execute_in_process()

    assert result.success


def test_job_fails_when_an_upstream_compute_asset_fails(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    job = _defs(award_classifications_asset=_failing_cet_award_classifications).resolve_job_def(
        "cet_full_pipeline_job"
    )

    result = job.execute_in_process(raise_on_error=False)

    assert not result.success
    message = result.failure_data_for_node(
        "ml__enriched_cet_award_classifications"
    ).error.cause.message
    assert "classification model unavailable" in message
