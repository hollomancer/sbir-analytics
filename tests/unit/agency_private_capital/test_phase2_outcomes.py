"""Tests for Phase 2 matched-cohort outcomes."""

from __future__ import annotations

import pandas as pd
import pytest

from sbir_analytics.assets.agency_private_capital.phase2_outcomes import MatchedCohortOutcomes


pytestmark = pytest.mark.fast


def _pairs() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "treated_company_name": "Acme Corp",
                "treated_company_key": "ACME CORP",
                "treated_form_d_cik": "123",
                "control_issuer_name": "Control One",
                "control_issuer_key": "CONTROL ONE",
                "control_form_d_cik": "999",
            },
            {
                "treated_company_name": "Beta Corp",
                "treated_company_key": "BETA CORP",
                "treated_form_d_cik": "124",
                "control_issuer_name": "Control Two",
                "control_issuer_key": "CONTROL TWO",
                "control_form_d_cik": "998",
            },
        ]
    )


def test_ma_exit_rate_available_for_treated_and_controls() -> None:
    outcomes = MatchedCohortOutcomes(
        ma_event_keys={"name:acme corp", "cik:998"}
    ).compute(_pairs())
    rows = {
        (row["cohort"], row["metric"]): row
        for _, row in outcomes[outcomes["metric"] == "ma_exit_rate"].iterrows()
    }

    assert rows[("agency_sbir", "ma_exit_rate")]["numerator"] == 1
    assert rows[("agency_sbir", "ma_exit_rate")]["denominator"] == 2
    assert rows[("form_d_control", "ma_exit_rate")]["numerator"] == 1
    assert rows[("form_d_control", "ma_exit_rate")]["denominator"] == 2
    assert bool(rows[("form_d_control", "ma_exit_rate")]["available"]) is True


def test_missing_event_sets_are_unavailable_not_zero() -> None:
    outcomes = MatchedCohortOutcomes().compute(_pairs())
    federal = outcomes[outcomes["metric"] == "federal_contract_presence"]
    assert not federal.empty
    assert (federal["available"] == False).all()  # noqa: E712
    assert federal["rate"].isna().all()
