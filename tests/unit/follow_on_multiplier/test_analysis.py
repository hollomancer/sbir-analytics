from pathlib import Path

import pandas as pd
import pytest

from sbir_analytics.assets.follow_on_multiplier.analysis import (
    FollowOnMultiplierPolicy,
    calculate_follow_on_multipliers,
)
from sbir_analytics.assets.follow_on_multiplier.integration import build_canonical_obligations

FIXTURES = Path("tests/fixtures/follow_on_multiplier")


def fixture_input():
    awards = pd.read_csv(FIXTURES / "sbir_awards.csv")
    matches = pd.read_csv(FIXTURES / "entity_matches.csv")
    tx = pd.read_csv(FIXTURES / "usaspending_transactions.csv")
    return build_canonical_obligations(awards, matches, tx)


def test_company_and_agency_multipliers_include_zero_and_negative_values():
    result = calculate_follow_on_multipliers(fixture_input())
    alpha_dod = result.company.query("company_id == 'ALPHA' and agency == 'DOD'").iloc[0]
    beta_dod = result.company.query("company_id == 'BETA' and agency == 'DOD'").iloc[0]
    dod = result.agency.query("agency == 'DOD'").iloc[0]
    assert alpha_dod["sbir_funding_denominator"] == 100
    assert alpha_dod["non_sbir_obligations_numerator"] == 350
    assert alpha_dod["follow_on_multiplier"] == 3.5
    assert beta_dod["non_sbir_obligations_numerator"] == 0
    assert beta_dod["follow_on_multiplier"] == 0
    assert dod["follow_on_multiplier"] == pytest.approx(350 / 300)
    assert dod["company_count"] == 2
    assert result.agency.query("agency == 'DOE'").iloc[0]["follow_on_multiplier"] == 2


def test_cohort_and_fiscal_year_aggregation_and_zero_denominator():
    result = calculate_follow_on_multipliers(fixture_input())
    alpha_cohort = result.cohort.query("agency == 'DOD' and cohort_year == 2020").iloc[0]
    fy_2022 = result.fiscal_year.query("agency == 'DOD' and fiscal_year == 2022").iloc[0]
    assert alpha_cohort["follow_on_multiplier"] == 3.5
    assert alpha_cohort["firm_size"] == "small"
    assert alpha_cohort["technology_area"] == "AI"
    assert alpha_cohort["experience"] == "experienced"
    assert fy_2022["non_sbir_obligations_numerator"] == -50
    assert pd.isna(fy_2022["follow_on_multiplier"])


def test_missing_and_low_confidence_matches_are_reported_and_excluded():
    result = calculate_follow_on_multipliers(fixture_input())
    quality = result.quality.iloc[0]
    assert quality["input_record_count"] == 9
    assert quality["matched_record_count"] == 6
    assert quality["excluded_record_count"] == 3
    assert set(result.company["company_id"]) == {"ALPHA", "BETA"}


def test_adjusted_dollars_apply_to_numerator_and_denominator():
    factors = pd.read_csv(FIXTURES / "inflation_factors.csv")
    result = calculate_follow_on_multipliers(
        fixture_input(),
        policy=FollowOnMultiplierPolicy(dollar_basis="adjusted"),
        adjustment_factors=factors,
    )
    dod = result.agency.query("agency == 'DOD'").iloc[0]
    assert dod["sbir_funding_denominator"] == 500
    assert dod["non_sbir_obligations_numerator"] == 550
    assert dod["follow_on_multiplier"] == pytest.approx(1.1)


def test_sttr_can_be_excluded_and_fiscal_window_is_inclusive():
    result = calculate_follow_on_multipliers(
        fixture_input(),
        policy=FollowOnMultiplierPolicy(
            include_sttr=False, fiscal_year_start=2021, fiscal_year_end=2022
        ),
    )
    assert "DOE" not in set(result.agency["agency"])
    assert result.quality.iloc[0]["input_record_count"] == 7
