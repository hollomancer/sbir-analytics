"""Layer-3 execution tests for cet_full_pipeline_job.

The job wires 8 ops end-to-end: three CET "compute" assets (taxonomy,
award classification, company aggregation) feeding five Neo4j loader ops
(node upsert, two enrichment upserts, two relationship-creation ops). The
job carries baked-in run config (``config={"ops": {...}}``) supplied at
``define_asset_job`` time, so ``execute_in_process()`` needs no extra
run_config from the caller.

Coverage strategy
------------------
The three compute assets are out of hermetic-test reach as written: they
load a trained ``ApplicabilityModel`` pickle off disk
(``artifacts/models/cet_classifier_v1.pkl``), run real evidence extraction,
and (for the taxonomy asset) parse ``config/cet/taxonomy.yaml`` through
Pydantic -- provisioning or faking all of that at the job-execution layer
would mostly test model-loading plumbing that
``tests/unit/assets/cet/`` already covers at the asset/unit level, not the
job's own wiring contract.

What *is* job-specific and otherwise uncovered is (a) whether the 8 ops are
actually wired together in an executable graph via job's ``AssetSelection``,
and (b) the Neo4j segment's hermetic-skip contract
(``SKIP_NEO4J_LOADING=true``, the same convention already pinned per-asset in
``tests/unit/assets/cet/test_loading_contracts.py``) actually holds when
those 5 ops run back to back inside one job instead of being invoked one at
a time via ``build_op_context``.

So these tests substitute lightweight stand-ins for the three compute assets
(same ``AssetKey``s, trivial bodies) into a job-scoped ``Definitions``, reuse
the *real* five Neo4j loader assets unmodified, and run with
``SKIP_NEO4J_LOADING=true`` so no network call is made. This exercises the
real dependency graph -- including the real ``ins=`` wiring in
``sbir_analytics/assets/cet/loading.py`` -- for all 8 ops without a real
trained model or a real Neo4j instance.
"""

from __future__ import annotations

import pytest
from dagster import Definitions, Output, asset

pytestmark = [pytest.mark.fast, pytest.mark.unit]


@asset(name="raw_cet_taxonomy", key_prefix=["ml"])
def _fake_cet_taxonomy() -> Output:
    """Stand-in for the real taxonomy asset; see module docstring."""
    return Output("stub-taxonomy")


@asset(name="enriched_cet_award_classifications", key_prefix=["ml"])
def _fake_cet_award_classifications() -> Output:
    """Stand-in for the real classification asset; see module docstring."""
    return Output("stub-classifications")


@asset(name="transformed_cet_company_profiles", key_prefix=["ml"])
def _fake_cet_company_profiles() -> Output:
    """Stand-in for the real company-profile asset; see module docstring."""
    return Output("stub-company-profiles")


@asset(name="enriched_cet_award_classifications", key_prefix=["ml"])
def _failing_cet_award_classifications() -> Output:
    raise RuntimeError("classification model unavailable")


def _defs(*, award_classifications_asset=_fake_cet_award_classifications):
    from sbir_analytics.assets.cet import loading
    from sbir_analytics.assets.jobs.cet_pipeline_job import cet_full_pipeline_job

    return Definitions(
        assets=[
            _fake_cet_taxonomy,
            award_classifications_asset,
            _fake_cet_company_profiles,
            loading.loaded_cet_areas,
            loading.loaded_award_cet_enrichment,
            loading.loaded_company_cet_enrichment,
            loading.loaded_award_cet_relationships,
            loading.loaded_company_cet_relationships,
        ],
        jobs=[cet_full_pipeline_job],
    )


def test_job_wires_all_eight_ops_and_succeeds_with_neo4j_skipped(monkeypatch):
    monkeypatch.setenv("SKIP_NEO4J_LOADING", "true")

    job = _defs().resolve_job_def("cet_full_pipeline_job")
    node_names = {node.name for node in job.nodes}
    # The ``key_prefix=["ml"]`` on the three compute assets becomes a
    # ``ml__`` node-name prefix; the five Neo4j ops have no key prefix.
    assert node_names == {
        "ml__raw_cet_taxonomy",
        "ml__enriched_cet_award_classifications",
        "ml__transformed_cet_company_profiles",
        "loaded_cet_areas",
        "loaded_award_cet_enrichment",
        "loaded_company_cet_enrichment",
        "loaded_award_cet_relationships",
        "loaded_company_cet_relationships",
    }

    result = job.execute_in_process()

    assert result.success
    for neo4j_op in (
        "loaded_cet_areas",
        "loaded_award_cet_enrichment",
        "loaded_company_cet_enrichment",
        "loaded_award_cet_relationships",
        "loaded_company_cet_relationships",
    ):
        assert result.output_for_node(neo4j_op) == {
            "status": "skipped",
            "reason": "explicit_skip",
        }


def test_job_fails_when_an_upstream_compute_asset_fails(monkeypatch):
    """A failure in the classification stage must fail the whole job, not just skip onward."""
    monkeypatch.setenv("SKIP_NEO4J_LOADING", "true")

    job = _defs(award_classifications_asset=_failing_cet_award_classifications).resolve_job_def(
        "cet_full_pipeline_job"
    )

    result = job.execute_in_process(raise_on_error=False)

    assert not result.success
    message = result.failure_data_for_node(
        "ml__enriched_cet_award_classifications"
    ).error.cause.message
    assert "classification model unavailable" in message
