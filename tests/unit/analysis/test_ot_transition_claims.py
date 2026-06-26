"""Tests for generic external OT Phase III transition claim classification."""

import pytest

from sbir_ml.transition.analysis.ot_transition_claims import (
    classify_external_ot_transition_claim,
)


@pytest.fixture
def external_ot_transition_claims():
    """Generic OT-transition claim fixtures spanning expected T1-T4 tiers."""

    return {
        "explicit_ot_phase_iii_transition": (
            "The OT consortium award is an SBIR Phase III transition for follow-on "
            "prototype production derived from the prior Phase II effort."
        ),
        "phase_iii_lineage_without_ot_vehicle": (
            "Analyst note: Phase III follow-on production derives from the prior "
            "SBIR Phase II award."
        ),
        "ot_transition_without_phase_iii": (
            "The OTA prototype transitioned to a follow-on production effort "
            "through the consortium."
        ),
        "unrelated_market_update": (
            "Company announced a commercial product update with no federal transition claim."
        ),
    }


@pytest.mark.parametrize(
    ("fixture_name", "expected_tier"),
    [
        ("explicit_ot_phase_iii_transition", "T1"),
        ("phase_iii_lineage_without_ot_vehicle", "T2"),
        ("ot_transition_without_phase_iii", "T3"),
        ("unrelated_market_update", "T4"),
    ],
)
def test_external_transition_claim_fixtures_produce_expected_tiers(
    external_ot_transition_claims, fixture_name, expected_tier
):
    result = classify_external_ot_transition_claim(external_ot_transition_claims[fixture_name])

    assert result.tier == expected_tier
    assert result.benchmark_neutral is True
    assert not hasattr(result, "benchmark_tier")
    assert not hasattr(result, "commercialization_benchmark_status")


def test_input_mode_classifies_external_transition_claims(external_ot_transition_claims):
    """Input mode accepts an analyst-supplied OT Phase III assertion, not covered sales."""

    analyst_supplied_input = {
        "source_type": "analyst_supplied_assertion",
        "claim_text": external_ot_transition_claims["explicit_ot_phase_iii_transition"],
    }

    result = classify_external_ot_transition_claim(analyst_supplied_input["claim_text"])

    assert analyst_supplied_input["source_type"] == "analyst_supplied_assertion"
    assert result.tier == "T1"
    assert result.benchmark_neutral is True
    assert "ot_vehicle" in result.matched_signals
    assert "phase_iii" in result.matched_signals
    assert "transition_language" in result.matched_signals
