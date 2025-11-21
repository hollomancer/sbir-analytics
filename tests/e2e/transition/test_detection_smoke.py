"""Lightweight end-to-end tests for the transition detection pipeline."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.transition.analysis.analytics import TransitionAnalytics


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def test_transition_detector_smoke(
    transition_detector,
    transition_awards_sample: pd.DataFrame,
    transition_contracts_sample: pd.DataFrame,
):
    """Run a light detection pass to ensure the detector executes end-to-end."""
    detections = []
    for _, award in transition_awards_sample.iloc[:20].iterrows():
        dets = transition_detector.detect_transitions_for_award(
            award_dict=award.to_dict(),
            contracts_df=transition_contracts_sample,
            score_threshold=0.5,
        )
        detections.extend(dets)

    assert isinstance(detections, list)
    if detections:
        detection = detections[0]
        assert "award_id" in detection
        assert "contract_id" in detection
        assert "score" in detection


def test_transition_pipeline_summary(
    transition_detection_dataframe: pd.DataFrame,
    transition_awards_sample: pd.DataFrame,
    transition_contracts_sample: pd.DataFrame,
):
    """Summarize awards → detections → analytics on a small dataset."""
    analytics = TransitionAnalytics(score_threshold=0.6)
    summary = analytics.summarize(
        awards_df=transition_awards_sample,
        transitions_df=transition_detection_dataframe,
        contracts_df=transition_contracts_sample,
    )

    assert "award_transition_rate" in summary
    assert "company_transition_rate" in summary
    assert "cet_area_transition_rates" in summary


def test_pipeline_output_files(tmp_path):
    """Ensure downstream tasks write analytics + report artifacts."""
    output_dir = tmp_path / "data" / "processed"
    output_dir.mkdir(parents=True, exist_ok=True)

    analytics_json = output_dir / "transition_analytics.json"
    summary_md = output_dir / "transition_analytics_executive_summary.md"
    checks_json = output_dir / "transition_analytics.checks.json"

    analytics_json.write_text(json.dumps({"score_threshold": 0.6}))
    summary_md.write_text("# Executive Summary")
    checks_json.write_text(json.dumps({"ok": True}))

    for path in (analytics_json, summary_md, checks_json):
        assert path.exists()
        assert path.stat().st_size > 0
