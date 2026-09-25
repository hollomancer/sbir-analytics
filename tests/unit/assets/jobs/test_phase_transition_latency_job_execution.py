"""Layer-3 execution tests for phase_transition_latency_job.

The job's docstring says it "assumes raw_contracts / enriched_sbir_awards are
already materialized" -- it selects only the four downstream phase_transition
assets (validated_phase_ii_awards, validated_phase_iii_contracts,
transformed_phase_ii_iii_pairs, transformed_phase_transition_survival) and
reads its FPDS/SBIR.gov inputs directly off disk via relative paths (see
``sbir_analytics.assets.phase_transition.phase_ii.DEFAULT_CONTRACTS_PATH`` and
``DEFAULT_SBIR_AWARDS_PATH``), rather than depending on upstream asset
outputs in the Dagster graph.

These tests reproduce that "already materialized" precondition by writing the
upstream parquet directly at those default relative paths under a tmp cwd,
then executing the *job itself* end to end via ``execute_in_process`` so the
Dagster wiring between the four assets (validated_phase_ii_awards /
validated_phase_iii_contracts feeding transformed_phase_ii_iii_pairs feeding
transformed_phase_transition_survival) is exercised for real, not just each
asset function in isolation (that unit coverage already exists in
tests/unit/phase_transition/test_phase_transition_assets.py).

The job itself is an ``UnresolvedAssetJobDefinition`` (built from asset keys
via ``build_job_from_spec``), so it must be resolved against a
``Definitions`` object before it can execute -- a bare
``phase_transition_latency_job.execute_in_process()`` raises. We build a
minimal ``Definitions`` scoped to just these four assets (mirroring the
pattern in test_nih_reporter_iterative_job.py) rather than importing the full
``sbir_analytics.definitions.defs``, which would pull in every heavy asset
module.
"""

from __future__ import annotations

import pandas as pd
import pytest
from dagster import Definitions

pytestmark = [pytest.mark.fast, pytest.mark.unit]


def _defs():
    from sbir_analytics.assets.jobs.phase_transition_job import phase_transition_latency_job
    from sbir_analytics.assets.phase_transition import (
        transformed_phase_ii_iii_pairs,
        transformed_phase_transition_survival,
        validated_phase_ii_awards,
        validated_phase_iii_contracts,
    )

    return Definitions(
        assets=[
            validated_phase_ii_awards,
            validated_phase_iii_contracts,
            transformed_phase_ii_iii_pairs,
            transformed_phase_transition_survival,
        ],
        jobs=[phase_transition_latency_job],
    )


def _write_contracts(workspace) -> None:
    """A minimal Phase II/Phase III pair sharing a recipient UEI."""
    from sbir_analytics.assets.phase_transition.phase_ii import DEFAULT_CONTRACTS_PATH

    contracts = pd.DataFrame(
        [
            {
                "contract_id": "C_II_1",
                "piid": "C_II_1",
                "generated_unique_award_id": "C_II_1",
                "transaction_unique_id": "TX-C_II_1",
                "vendor_uei": "AAAAAAAAAAAA",
                "vendor_duns": "123456789",
                "vendor_name": "Foo Inc",
                "awarding_agency_name": "DOD",
                "action_date": "2020-01-15",
                "period_of_performance_current_end_date": "2022-06-30",
                "research": "SR2",
                "federal_action_obligation": 750_000,
            },
            {
                "contract_id": "C_III_1",
                "generated_unique_award_id": "C_III_1",
                "transaction_unique_id": "TX-C_III_1",
                "vendor_uei": "AAAAAAAAAAAA",
                "vendor_duns": "123456789",
                "vendor_name": "Foo Inc",
                "awarding_agency_name": "DOD",
                "action_date": "2023-02-01",
                "period_of_performance_current_end_date": "2024-12-31",
                "research": "SR3",
                "federal_action_obligation": 5_000_000,
            },
        ]
    )
    path = workspace / DEFAULT_CONTRACTS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    contracts.to_parquet(path, index=False)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """Materialize inputs relative to cwd, matching the assets' default paths."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_job_succeeds_with_no_upstream_inputs_materialized(workspace):
    """Nothing materialized upstream: every asset must still run and emit empty frames.

    This pins the same "run and flag, don't crash" contract that the
    per-asset unit test (test_validated_phase_ii_awards_runs_on_empty_inputs)
    pins for a single asset, but at the job-execution level.
    """
    result = _defs().resolve_job_def("phase_transition_latency_job").execute_in_process()

    assert result.success
    survival = result.output_for_node("transformed_phase_transition_survival")
    assert survival.empty


def test_job_wires_phase_ii_and_phase_iii_into_matched_pairs_and_survival(workspace):
    """End-to-end: a real Phase II/III pair flows through pairs -> survival."""
    _write_contracts(workspace)

    result = _defs().resolve_job_def("phase_transition_latency_job").execute_in_process()

    assert result.success
    phase_ii = result.output_for_node("validated_phase_ii_awards")
    phase_iii = result.output_for_node("validated_phase_iii_contracts")
    pairs = result.output_for_node("transformed_phase_ii_iii_pairs")
    survival = result.output_for_node("transformed_phase_transition_survival")

    assert list(phase_ii["award_id"]) == ["C_II_1"]
    assert list(phase_iii["contract_id"]) == ["C_III_1"]
    assert len(pairs) == 1
    assert pairs.iloc[0]["phase_ii_award_id"] == "C_II_1"
    assert pairs.iloc[0]["phase_iii_contract_id"] == "C_III_1"
    assert len(survival) == 1
    assert bool(survival.iloc[0]["event_observed"]) is True
