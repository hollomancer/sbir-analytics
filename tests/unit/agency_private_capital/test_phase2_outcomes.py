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


def test_form_d_business_combination_proxy_is_unavailable_without_symmetric_coverage() -> None:
    outcomes = MatchedCohortOutcomes().compute(_pairs())
    rows = {
        (row["cohort"], row["metric"]): row
        for _, row in outcomes[
            outcomes["metric"] == "form_d_business_combination_filing_proxy"
        ].iterrows()
    }

    assert rows[("agency_sbir", "form_d_business_combination_filing_proxy")]["denominator"] == 2
    assert rows[("form_d_control", "form_d_business_combination_filing_proxy")]["denominator"] == 2
    assert all(not bool(row["available"]) for row in rows.values())
    assert outcomes["metric"].ne("ma_exit_rate").all()


def test_missing_event_sets_are_unavailable_not_zero() -> None:
    outcomes = MatchedCohortOutcomes().compute(_pairs())
    federal = outcomes[outcomes["metric"] == "federal_contract_presence"]
    assert not federal.empty
    assert (federal["available"] == False).all()  # noqa: E712
    assert federal["rate"].isna().all()
