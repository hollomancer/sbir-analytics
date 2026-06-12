"""Unit tests for Wilson CI math and OutcomeMetricsCalculator wiring."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from sbir_analytics.assets.agency_private_capital.cohort import AgencyCohortBuilder
from sbir_analytics.assets.agency_private_capital.outcomes import (
    OutcomeMetricsCalculator,
    wilson_interval,
)


pytestmark = pytest.mark.fast


def test_wilson_interval_zero_denominator_yields_nan() -> None:
    wi = wilson_interval(0, 0)
    assert math.isnan(wi["rate"])
    assert math.isnan(wi["ci_low"])
    assert math.isnan(wi["ci_high"])
    assert wi["numerator"] == 0
    assert wi["denominator"] == 0


def test_wilson_interval_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError):
        wilson_interval(5, 3)


def test_wilson_interval_known_values() -> None:
    # Reference values from R's binom::binom.confint(method="wilson") for 5/10
    wi = wilson_interval(5, 10)
    assert wi["rate"] == pytest.approx(0.5)
    assert wi["ci_low"] == pytest.approx(0.2365, abs=1e-3)
    assert wi["ci_high"] == pytest.approx(0.7635, abs=1e-3)


def test_wilson_interval_clipped_to_unit_interval() -> None:
    wi = wilson_interval(0, 5)
    assert wi["rate"] == pytest.approx(0.0)
    assert wi["ci_low"] == pytest.approx(0.0)
    assert 0 < wi["ci_high"] < 1
    wi = wilson_interval(5, 5)
    assert wi["rate"] == pytest.approx(1.0)
    assert 0 < wi["ci_low"] < 1
    assert wi["ci_high"] == pytest.approx(1.0)


def _nsf_awards() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "award_id": "I-A",
                "agency": "NSF",
                "phase": "Phase I",
                "award_year": 2016,
                "uei": "AAA",
                "company_name": "Alpha",
            },
            {
                "award_id": "I-B",
                "agency": "NSF",
                "phase": "Phase I",
                "award_year": 2016,
                "uei": "BBB",
                "company_name": "Beta",
            },
            {
                "award_id": "I-C",
                "agency": "NSF",
                "phase": "Phase I",
                "award_year": 2016,
                "uei": "CCC",
                "company_name": "Gamma",
            },
            {
                "award_id": "I-D",
                "agency": "NSF",
                "phase": "Phase I",
                "award_year": 2016,
                "uei": "DDD",
                "company_name": "Delta",
            },
            {
                "award_id": "II-A",
                "agency": "NSF",
                "phase": "Phase II",
                "award_year": 2017,
                "uei": "AAA",
                "company_name": "Alpha",
            },
            {
                "award_id": "II-B",
                "agency": "NSF",
                "phase": "Phase II",
                "award_year": 2018,
                "uei": "BBB",
                "company_name": "Beta",
            },
        ]
    )


def test_phase_i_to_ii_graduation_uses_company_match() -> None:
    cohort = AgencyCohortBuilder(agency_code="NSF").build(_nsf_awards())
    outcomes = OutcomeMetricsCalculator().compute(cohort)
    grad_rows = outcomes[outcomes["metric"] == "phase_i_to_ii_graduation"]
    assert len(grad_rows) == 1
    row = grad_rows.iloc[0]
    assert row["denominator"] == 4
    assert row["numerator"] == 2
    assert row["rate"] == pytest.approx(0.5)
    assert bool(row["available"]) is True


def test_metrics_with_missing_inputs_marked_unavailable() -> None:
    cohort = AgencyCohortBuilder(agency_code="NSF").build(_nsf_awards())
    outcomes = OutcomeMetricsCalculator().compute(cohort)
    for metric in (
        "phase_ii_to_federal_contract_transition",
        "five_year_survival_proxy",
        "ma_exit_rate",
    ):
        rows = outcomes[outcomes["metric"] == metric]
        assert not rows.empty, metric
        assert (rows["available"] == False).all(), metric  # noqa: E712


def test_transition_rate_consumes_score_threshold() -> None:
    cohort = AgencyCohortBuilder(agency_code="NSF").build(_nsf_awards())
    transitions = pd.DataFrame(
        [
            {"award_id": "II-A", "score": 0.90, "method": "uei"},
            {"award_id": "II-B", "score": 0.40, "method": "name_fuzzy"},
        ]
    )
    outcomes = OutcomeMetricsCalculator(
        transition_scores=transitions,
        transition_score_threshold=0.65,
    ).compute(cohort)
    rows = outcomes[outcomes["metric"] == "phase_ii_to_federal_contract_transition"]
    # Phase II awards span vintages 2015-2019 (II-A in 2017) and 2015-2019 (II-B in 2018).
    # Same bucket -> one row.
    assert len(rows) == 1
    row = rows.iloc[0]
    assert row["denominator"] == 2
    assert row["numerator"] == 1
    assert bool(row["available"]) is True


def test_ma_exit_rate_joins_on_uei_keyed_cohort_via_name_fallback() -> None:
    """Bug fix 1: M&A events JSONL is name-keyed; cohort rows with UEI should
    still match when the company name is provided in the M&A set.

    Previously the join used only _company_key (UEI/DUNS-first), so a cohort
    row with UEI=AAA and company_name=Alpha would resolve to 'uei:AAA' and
    never match the M&A key 'name:alpha'. After the fix, the name-key fallback
    allows the match.
    """
    cohort = AgencyCohortBuilder(agency_code="NSF").build(_nsf_awards())
    # M&A events are name-keyed (as sbir_ma_events.jsonl is)
    ma_keys = {"name:alpha"}
    outcomes = OutcomeMetricsCalculator(ma_event_companies=ma_keys).compute(cohort)
    rows = outcomes[outcomes["metric"] == "ma_exit_rate"]
    # Alpha has UEI AAA; with the name-key fallback, the match should succeed.
    phase_ii_row = rows[rows["phase_label"] == "II"].iloc[0]
    assert phase_ii_row["numerator"] == 1


def test_ma_event_rate_matches_when_uei_missing() -> None:
    awards = pd.DataFrame(
        [
            {
                "award_id": "II-X",
                "agency": "NSF",
                "phase": "Phase II",
                "award_year": 2017,
                "company_name": "Alpha",
            },
        ]
    )
    cohort = AgencyCohortBuilder(agency_code="NSF").build(awards)
    outcomes = OutcomeMetricsCalculator(ma_event_companies={"name:alpha"}).compute(cohort)
    rows = outcomes[outcomes["metric"] == "ma_exit_rate"]
    assert rows.iloc[0]["numerator"] == 1
    assert rows.iloc[0]["denominator"] == 1


def test_five_year_survival_denominator_is_company_level() -> None:
    """Bug fix 2: denominator for five_year_survival_proxy should be unique
    companies, not award rows. A company with two Phase II awards in the same
    vintage should count as 1 in the denominator, not 2.
    """
    awards = pd.DataFrame(
        [
            # Company AAA has two Phase II awards in the same vintage
            {
                "award_id": "II-A1",
                "agency": "NSF",
                "phase": "Phase II",
                "award_year": 2016,
                "uei": "AAA",
                "company_name": "Alpha",
            },
            {
                "award_id": "II-A2",
                "agency": "NSF",
                "phase": "Phase II",
                "award_year": 2017,
                "uei": "AAA",
                "company_name": "Alpha",
            },
            # Company BBB has one Phase II award
            {
                "award_id": "II-B1",
                "agency": "NSF",
                "phase": "Phase II",
                "award_year": 2016,
                "uei": "BBB",
                "company_name": "Beta",
            },
        ]
    )
    cohort = AgencyCohortBuilder(agency_code="NSF").build(awards)
    federal_activity = {"uei:AAA"}  # only Alpha survives
    outcomes = OutcomeMetricsCalculator(federal_activity_companies=federal_activity).compute(cohort)
    rows = outcomes[outcomes["metric"] == "five_year_survival_proxy"]
    assert len(rows) == 1
    row = rows.iloc[0]
    # 2 unique companies (AAA, BBB), 1 survived => denominator=2, numerator=1
    assert row["denominator"] == 2
    assert row["numerator"] == 1


def test_empty_cohort_returns_empty_metrics_frame() -> None:
    cohort = AgencyCohortBuilder(agency_code="NSF").build(pd.DataFrame(columns=["agency", "phase"]))
    outcomes = OutcomeMetricsCalculator().compute(cohort)
    assert outcomes.empty
    assert set(outcomes.columns) >= {
        "vintage_bucket",
        "phase_label",
        "metric",
        "numerator",
        "denominator",
        "rate",
        "ci_low",
        "ci_high",
        "available",
    }
