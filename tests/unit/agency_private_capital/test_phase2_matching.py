"""Tests for Phase 2 treated/control cohort construction and matching."""

from __future__ import annotations

import pandas as pd
import pytest

from sbir_analytics.assets.agency_private_capital.control_cohort import (
    AgencyAwardeeFilter,
    PrivateCapitalControlCohortBuilder,
    agency_leverage_cross_check,
)
from sbir_analytics.assets.agency_private_capital.matching import CohortMatcher


pytestmark = pytest.mark.fast


def test_agency_awardee_filter_intersects_agency_awards_with_form_d_matches() -> None:
    awards = pd.DataFrame(
        [
            {
                "agency": "NSF",
                "phase": "Phase II",
                "award_year": 2020,
                "award_amount": "1000000",
                "company_name": "Acme Corp",
                "state": "CA",
            },
            {
                "agency": "Department of Defense",
                "phase": "Phase II",
                "award_year": 2020,
                "award_amount": "1000000",
                "company_name": "Defense Corp",
                "state": "CA",
            },
        ]
    )
    matches = pd.DataFrame(
        [
            {
                "company_name": "Acme Corp",
                "company_key": "ACME CORP",
                "form_d_cik": "123",
                "state": "CA",
                "industry_group": "Other Technology",
                "first_form_d_year": 2021,
                "total_form_d_raised": 5_000_000,
            }
        ]
    )

    treated = AgencyAwardeeFilter(agency_code="NSF").build(awards, matches)

    assert len(treated) == 1
    assert treated.iloc[0]["company_key"] == "ACME CORP"
    assert treated.iloc[0]["agency_sbir_amount"] == 1_000_000
    assert treated.iloc[0]["vintage_year"] == 2020


def test_private_capital_control_builder_shapes_control_rows() -> None:
    universe = pd.DataFrame(
        [
            {
                "issuer_name": "Control One",
                "issuer_key": "CONTROL ONE",
                "form_d_cik": "999",
                "state": "CA",
                "industry_group": "Other Technology",
                "first_form_d_year": 2020,
                "total_form_d_raised": 2_000_000,
                "offering_count": 1,
            }
        ]
    )

    controls = PrivateCapitalControlCohortBuilder().build(universe)

    assert len(controls) == 1
    assert controls.iloc[0]["cohort"] == "form_d_control"
    assert controls.iloc[0]["issuer_key"] == "CONTROL ONE"


def test_agency_leverage_cross_check_uses_full_agency_award_denominator() -> None:
    awards = pd.DataFrame(
        [
            {
                "agency": "NSF",
                "award_year": 2020,
                "award_amount": "1000000",
                "company_name": "Acme Corp",
            },
            {
                "agency": "National Science Foundation",
                "award_year": 2020,
                "award_amount": "2000000",
                "company_name": "Unmatched Corp",
            },
            {
                "agency": "Department of Defense",
                "award_year": 2020,
                "award_amount": "9000000",
                "company_name": "Defense Corp",
            },
        ]
    )
    treated = pd.DataFrame(
        [
            {
                "company_name": "Acme Corp",
                "company_key": "ACME CORP",
                "agency_sbir_amount": 1_000_000,
                "total_form_d_raised": 6_000_000,
            }
        ]
    )

    summary = agency_leverage_cross_check("NSF", awards, treated)

    assert summary["agency_award_rows"] == 2
    assert summary["agency_program_sbir_amount"] == 3_000_000
    assert summary["matched_agency_sbir_amount"] == 1_000_000
    assert summary["matched_form_d_raised"] == 6_000_000
    assert summary["form_d_to_agency_program_ratio"] == pytest.approx(2.0)
    assert summary["form_d_to_matched_sbir_ratio"] == pytest.approx(6.0)


def test_cohort_matcher_matches_exact_vintage_industry_state() -> None:
    treated = pd.DataFrame(
        [
            {
                "company_name": "Acme Corp",
                "company_key": "ACME CORP",
                "form_d_cik": "123",
                "vintage_year": 2020,
                "state": "CA",
                "industry_group": "Other Technology",
                "total_form_d_raised": 5_000_000,
            },
            {
                "company_name": "Unmatched Corp",
                "company_key": "UNMATCHED CORP",
                "form_d_cik": "124",
                "vintage_year": 2020,
                "state": "MA",
                "industry_group": "Biotechnology",
                "total_form_d_raised": 1_000_000,
            },
        ]
    )
    controls = pd.DataFrame(
        [
            {
                "issuer_name": "Control One",
                "issuer_key": "CONTROL ONE",
                "form_d_cik": "999",
                "vintage_year": 2020,
                "state": "CA",
                "industry_group": "Other Technology",
                "total_form_d_raised": 2_000_000,
            },
            {
                "issuer_name": "Control Two",
                "issuer_key": "CONTROL TWO",
                "form_d_cik": "998",
                "vintage_year": 2021,
                "state": "CA",
                "industry_group": "Other Technology",
                "total_form_d_raised": 2_000_000,
            },
        ]
    )

    pairs, balance = CohortMatcher(controls_per_treated=2).match(treated, controls)

    assert len(pairs) == 1
    assert pairs.iloc[0]["treated_company_key"] == "ACME CORP"
    assert balance["treated_count"] == 2
    assert balance["matched_treated_count"] == 1
    assert balance["unmatched_treated_count"] == 1
