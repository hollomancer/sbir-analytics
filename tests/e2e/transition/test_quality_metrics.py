"""Transition quality and performance metric tests."""

from __future__ import annotations

import pandas as pd
import pytest

from src.transition.evaluation.evaluator import TransitionEvaluator
from src.transition.performance.monitoring import PerformanceTracker, profile_detection_performance


pytestmark = [pytest.mark.e2e, pytest.mark.slow]


def _build_evaluation_payload(num_detections: int = 200, tp_count: int = 150):
    detections = pd.DataFrame(
        {
            "award_id": [f"SBIR-{i:05d}" for i in range(num_detections)],
            "contract_id": [f"CONTRACT-{i:05d}" for i in range(num_detections)],
            "score": [0.55 + (i % 20) / 100 for i in range(num_detections)],
            "confidence": [
                "high" if i % 100 < 40 else ("likely" if i % 100 < 70 else "possible")
                for i in range(num_detections)
            ],
        }
    )
    ground_truth = pd.DataFrame(
        {
            "award_id": [f"SBIR-{i:05d}" for i in range(tp_count)],
            "contract_id": [f"CONTRACT-{i:05d}" for i in range(tp_count)],
        }
    )
    return detections, ground_truth


def test_transition_quality_metrics_smoke():
    """Precision/recall evaluation meets reasonable bounds."""
    detections, ground_truth = _build_evaluation_payload()
    evaluator = TransitionEvaluator(score_threshold=0.6)
    result = evaluator.evaluate(
        detections_df=detections,
        ground_truth_df=ground_truth,
        score_column="score",
    )

    assert 0 <= result.precision <= 1
    assert 0 <= result.recall <= 1
    assert 0 <= result.f1 <= 1


def test_transition_confidence_band_metrics():
    """Confidence breakdown includes high-confidence improvements."""
    detections, ground_truth = _build_evaluation_payload()
    evaluator = TransitionEvaluator(score_threshold=0.6)
    result = evaluator.evaluate(
        detections_df=detections,
        ground_truth_df=ground_truth,
        score_column="score",
    )

    assert result.by_confidence
    high_metrics = result.by_confidence.get("high")
    if high_metrics:
        assert "precision" in high_metrics


def test_detection_performance_targets():
    """Throughput calculation meets and fails targets as expected."""
    metrics = profile_detection_performance(
        awards_count=10000,
        contracts_count=50000,
        detections_count=10000,
        total_time_ms=60000,
    )
    assert metrics["detections_per_minute"] >= 10000
    assert metrics["detections_per_minute_meets_target"] is True

    slow_metrics = profile_detection_performance(
        awards_count=1000,
        contracts_count=5000,
        detections_count=200,
        total_time_ms=120000,
    )
    assert slow_metrics["detections_per_minute"] < 10000
    assert slow_metrics["detections_per_minute_meets_target"] is False


def test_performance_tracker_smoke():
    """Performance tracker captures throughput stats."""
    tracker = PerformanceTracker("transition_e2e")
    tracker.start()
    tracker.end(items_processed=5000)
    metrics = tracker.get_metrics()

    assert metrics["items_processed"] == 5000
    assert metrics["duration_ms"] >= 0
    assert metrics["throughput_per_second"] >= 0
