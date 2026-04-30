"""Unit tests for Wilson CI math and OutcomeMetricsCalculator wiring."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from sbir_analytics.assets.nsf_vc.cohort import NSFCohortBuilder
from sbir_analytics.assets.nsf_vc.outcomes import OutcomeMetricsCalculator, wilson_interval


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
    cohort = NSFCohortBuilder().build(_nsf_awards())
    outcomes = OutcomeMetricsCalculator().compute(cohort)
    grad_rows = outcomes[outcomes["metric"] == "phase_i_to_ii_graduation"]
    assert len(grad_rows) == 1
    row = grad_rows.iloc[0]
    assert row["denominator"] == 4
    assert row["numerator"] == 2
    assert row["rate"] == pytest.approx(0.5)
    assert bool(row["available"]) is True


def test_metrics_with_missing_inputs_marked_unavailable() -> None:
    cohort = NSFCohortBuilder().build(_nsf_awards())
    outcomes = OutcomeMetricsCalculator().compute(cohort)
    for metric in (
        "phase_ii_to_federal_contract_transition",
        "five_year_survival_proxy",
        "patent_rate",
        "ma_exit_rate",
    ):
        rows = outcomes[outcomes["metric"] == metric]
        assert not rows.empty, metric
        assert (rows["available"] == False).all(), metric  # noqa: E712


def test_transition_rate_consumes_score_threshold() -> None:
    cohort = NSFCohortBuilder().build(_nsf_awards())
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


def test_ma_event_rate_joins_on_company_name() -> None:
    cohort = NSFCohortBuilder().build(_nsf_awards())
    ma_keys = {"name:alpha"}
    outcomes = OutcomeMetricsCalculator(ma_event_companies=ma_keys).compute(cohort)
    rows = outcomes[outcomes["metric"] == "ma_exit_rate"]
    # Each (vintage, phase) stratum gets its own ma_exit_rate row.
    # Alpha has UEI AAA so its company_key is "uei:AAA", not "name:alpha".
    # Confirms the join uses the cohort's resolved key, not just the name.
    assert (rows["numerator"] == 0).all()


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
    cohort = NSFCohortBuilder().build(awards)
    outcomes = OutcomeMetricsCalculator(ma_event_companies={"name:alpha"}).compute(cohort)
    rows = outcomes[outcomes["metric"] == "ma_exit_rate"]
    assert rows.iloc[0]["numerator"] == 1
    assert rows.iloc[0]["denominator"] == 1


def test_empty_cohort_returns_empty_metrics_frame() -> None:
    cohort = NSFCohortBuilder().build(pd.DataFrame(columns=["agency", "phase"]))
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
