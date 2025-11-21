"""Transition CET effectiveness analytics tests."""

from __future__ import annotations

import pytest

from src.transition.analysis.analytics import TransitionAnalytics


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def test_cet_effectiveness_computation(cet_effectiveness_dataset):
    """Compute CET rates, time-to-transition, and patent-backed metrics."""
    data = cet_effectiveness_dataset
    analytics = TransitionAnalytics(score_threshold=0.6)

    cet_rates = analytics.compute_transition_rates_by_cet_area(
        data["awards"],
        data["detections"],
    )
    analytics.compute_avg_time_to_transition_by_cet_area(
        data["awards"],
        data["detections"],
        data["contracts"],
    )
    patent_rates = analytics.compute_patent_backed_transition_rates_by_cet_area(
        data["awards"],
        data["detections"],
        data["patents"],
    )

    assert not cet_rates.empty
    assert not patent_rates.empty
    assert (cet_rates["rate"] >= 0).all()
    assert (cet_rates["rate"] <= 1).all()


def test_cet_summary_contains_highlights(cet_effectiveness_dataset):
    """Ensure the summarized analytics expose CET metrics."""
    data = cet_effectiveness_dataset
    analytics = TransitionAnalytics(score_threshold=0.6)

    summary = analytics.summarize(
        awards_df=data["awards"],
        transitions_df=data["detections"],
        contracts_df=data["contracts"],
    )

    assert "cet_area_transition_rates" in summary
    assert "avg_time_to_transition_by_cet_area" in summary
    assert "patent_backed_rates_by_cet_area" in summary
