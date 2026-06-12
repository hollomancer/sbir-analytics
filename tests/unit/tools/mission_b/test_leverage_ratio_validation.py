"""Invariant and sensitivity tests for federal-to-SBIR leverage ratios."""

from __future__ import annotations

import pandas as pd
import pytest

from sbir_analytics.tools.mission_b.leverage_ratio import LeverageConfig, compute_leverage_ratio
from sbir_analytics.tools.mission_b.leverage_ratio_validation import (
    build_stratified_review_sample,
    enforce_report_gate,
    run_sensitivity_analysis,
    sensitivity_summary,
    validate_run,
)

pytestmark = pytest.mark.fast


def source_fixture() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "obligation_id": "a-sbir",
                "canonical_company_id": "a",
                "agency": "DOD",
                "fiscal_year": 2018,
                "cohort_year": 2018,
                "obligation_amount": 100.0,
                "is_sbir": True,
                "is_sttr": False,
                "match_confidence": 0.99,
                "inflation_factor": 1.2,
            },
            {
                "obligation_id": "a-follow",
                "canonical_company_id": "a",
                "agency": "DOD",
                "fiscal_year": 2019,
                "cohort_year": 2018,
                "obligation_amount": 400.0,
                "is_sbir": False,
                "is_sttr": False,
                "match_confidence": 0.95,
                "inflation_factor": 1.1,
            },
            {
                "obligation_id": "a-deob",
                "canonical_company_id": "a",
                "agency": "DOD",
                "fiscal_year": 2020,
                "cohort_year": 2018,
                "obligation_amount": -40.0,
                "is_sbir": False,
                "is_sttr": False,
                "match_confidence": 0.95,
                "inflation_factor": 1.0,
            },
            {
                "obligation_id": "b-sttr",
                "canonical_company_id": "b",
                "agency": "DOE",
                "fiscal_year": 2020,
                "cohort_year": 2020,
                "obligation_amount": 50.0,
                "is_sbir": False,
                "is_sttr": True,
                "match_confidence": 0.85,
                "inflation_factor": 1.0,
            },
            {
                "obligation_id": "b-follow",
                "canonical_company_id": "b",
                "agency": "DOE",
                "fiscal_year": 2021,
                "cohort_year": 2020,
                "obligation_amount": 100.0,
                "is_sbir": False,
                "is_sttr": False,
                "match_confidence": 0.85,
                "inflation_factor": 1.0,
            },
        ]
    )


def test_invariants_reconcile_and_deobligations_are_net() -> None:
    source = source_fixture()
    config = LeverageConfig()
    outputs = compute_leverage_ratio(source, config)
    checks = validate_run(source, outputs, config)
    assert all(check.passed for check in checks)
    assert outputs["headline"].iloc[0]["non_sbir_obligations"] == 460.0
    assert outputs["headline"].iloc[0]["sbir_sttr_obligations"] == 150.0
    enforce_report_gate(checks)


def test_gate_rejects_duplicate_after_entity_matching() -> None:
    source = pd.concat([source_fixture(), source_fixture().iloc[[0]]], ignore_index=True)
    config = LeverageConfig()
    checks = validate_run(source, compute_leverage_ratio(source, config), config)
    duplicate = next(
        check for check in checks if check.name == "no_duplicate_obligations_after_matching"
    )
    assert not duplicate.passed
    with pytest.raises(ValueError, match="no_duplicate_obligations"):
        enforce_report_gate(checks)


def test_gate_rejects_tampered_reconciliation_and_missing_dimension() -> None:
    source = source_fixture()
    config = LeverageConfig()
    outputs = compute_leverage_ratio(source, config)
    outputs["headline"].loc[:, "non_sbir_obligations"] += 1
    outputs.pop("cohort")
    checks = validate_run(source, outputs, config)
    failed = {check.name for check in checks if not check.passed}
    assert {
        "source_reconciliation",
        "stable_aggregation_across_dimensions",
        "required_output_dimensions",
    } <= failed


def test_sensitivity_exposes_every_choice_and_ranges() -> None:
    scenarios = run_sensitivity_analysis(
        source_fixture(),
        match_thresholds=(0.8,),
        analysis_windows=((None, None),),
        inflation_adjusted=(False, True),
        include_negative_obligations=(True, False),
        sttr_treatments=("include", "exclude"),
    )
    assert len(scenarios) == 8
    assert scenarios["scenario_id"].nunique() == 8
    assert scenarios["leverage_ratio"].min() != scenarios["leverage_ratio"].max()
    summary = sensitivity_summary(scenarios)
    overall = summary[summary["choice"] == "all_scenarios"].iloc[0]
    assert overall["ratio_min"] == scenarios["leverage_ratio"].min()
    assert overall["ratio_max"] == scenarios["leverage_ratio"].max()


def test_review_sample_uses_high_low_strata_and_evidence_references() -> None:
    source = source_fixture()
    companies = compute_leverage_ratio(source)["company"]
    review = build_stratified_review_sample(source, companies, per_stratum=1)
    assert set(review["review_stratum"]) == {"high_leverage", "low_leverage"}
    assert set(review["review_status"]) == {"pending"}
    assert review["review_evidence_reference"].str.startswith("obligation_ids:").all()
