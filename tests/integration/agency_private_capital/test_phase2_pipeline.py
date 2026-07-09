"""Integration test for Phase 2 agency-vs-Form-D matched cohort flow."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from sbir_analytics.assets.agency_private_capital.control_cohort import (
    AgencyAwardeeFilter,
    PrivateCapitalControlCohortBuilder,
)
from sbir_analytics.assets.agency_private_capital.form_d_inputs import (
    load_form_d_control_universe,
    load_form_d_matches,
)
from sbir_analytics.assets.agency_private_capital.matching import CohortMatcher
from sbir_analytics.assets.agency_private_capital.phase2_outcomes import MatchedCohortOutcomes
from sbir_analytics.assets.agency_private_capital.threats import ThreatsToValidity


pytestmark = pytest.mark.integration


def _write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def test_phase2_pipeline_produces_pairs_outcomes_and_threats(tmp_path) -> None:
    awards = pd.DataFrame(
        [
            {
                "agency": "NSF",
                "phase": "Phase II",
                "award_year": 2020,
                "award_amount": "1000000",
                "company_name": "Acme Corp",
                "state": "CA",
            }
        ]
    )
    matches_path = tmp_path / "form_d_details.jsonl"
    _write_jsonl(
        matches_path,
        [
            {
                "company_name": "Acme Corp",
                "form_d_cik": "0000123",
                "match_confidence": {"tier": "high"},
                "offerings": [
                    {
                        "entity_name": "ACME CORP",
                        "filing_date": "2021-03-01",
                        "state": "CA",
                        "industry_group": "Other Technology",
                        "total_amount_sold": 5_000_000,
                    }
                ],
            }
        ],
    )
    control_path = tmp_path / "controls.jsonl"
    _write_jsonl(
        control_path,
        [
            {
                "issuer_name": "Control One",
                "cik": "0000999",
                "filing_date": "2020-01-01",
                "state": "CA",
                "industry_group": "Other Technology",
                "total_amount_sold": 2_000_000,
            }
        ],
    )

    matches = load_form_d_matches(matches_path, tier_filter={"high"}, year_min=2009, year_max=2024)
    controls_universe = load_form_d_control_universe(
        control_path, sbir_ciks={"123"}, year_min=2009, year_max=2024
    )
    treated = AgencyAwardeeFilter(agency_code="NSF").build(awards, matches)
    controls = PrivateCapitalControlCohortBuilder().build(controls_universe)
    pairs, balance = CohortMatcher().match(treated, controls)
    outcomes = MatchedCohortOutcomes(ma_event_keys={"name:acme corp"}).compute(pairs)
    threats = ThreatsToValidity().validate()

    assert len(pairs) == 1
    assert balance["match_rate"] == pytest.approx(1.0)
    ma_treated = outcomes[
        (outcomes["cohort"] == "agency_sbir") & (outcomes["metric"] == "ma_exit_rate")
    ].iloc[0]
    assert ma_treated["numerator"] == 1
    assert threats["passed"] is True
