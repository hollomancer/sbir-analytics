import pandas as pd
import pytest

from src.transition import ConfusionMatrix, EvaluationResult, TransitionEvaluator


def _build_detections(rows):
    return pd.DataFrame(rows)


def _build_ground_truth(rows):
    return pd.DataFrame(rows)


def test_evaluator_perfect_precision_recall():
    detections = _build_detections(
        [
            {
                "award_id": "A1",
                "contract_id": "C1",
                "likelihood_score": 0.9,
                "confidence": "high",
            },
            {
                "award_id": "A2",
                "contract_id": "C2",
                "likelihood_score": 0.8,
                "confidence": "likely",
            },
        ]
    )

    ground_truth = _build_ground_truth(
        [
            {"award_id": "A1", "contract_id": "C1"},
            {"award_id": "A2", "contract_id": "C2"},
        ]
    )

    evaluator = TransitionEvaluator(score_threshold=0.75)
    result = evaluator.evaluate(detections, ground_truth)

    assert isinstance(result, EvaluationResult)
    assert result.precision == pytest.approx(1.0)
    assert result.recall == pytest.approx(1.0)
    assert result.f1 == pytest.approx(1.0)
    assert result.support == 2
    assert result.confusion.to_dict() == {"tp": 2, "fp": 0, "fn": 0, "tn": 0, "total": 2}


def test_evaluator_confidence_breakdown_and_false_positive():
    detections = _build_detections(
        [
            {
                "award_id": "A1",
                "contract_id": "C1",
                "likelihood_score": 0.95,
                "confidence": "high",
            },
            {
                "award_id": "A2",
                "contract_id": "C2",
                "likelihood_score": 0.85,
                "confidence": "likely",
            },
            {
                "award_id": "A3",
                "contract_id": "C3",
                "likelihood_score": 0.82,
                "confidence": "likely",
            },
        ]
    )

    ground_truth = _build_ground_truth(
        [
            {"award_id": "A1", "contract_id": "C1"},
            {"award_id": "A2", "contract_id": "C2"},
        ]
    )

    evaluator = TransitionEvaluator(score_threshold=0.80)
    result = evaluator.evaluate(detections, ground_truth)

    assert result.precision == pytest.approx(2 / 3)
    assert result.recall == pytest.approx(1.0)
    assert result.f1 == pytest.approx(0.8)
    assert result.confusion.tp == 2
    assert result.confusion.fp == 1
    assert result.confusion.fn == 0

    high_band = result.by_confidence.get("high")
    likely_band = result.by_confidence.get("likely")
    assert high_band == {
        "detections": 1,
        "true_positives": 1,
        "false_positives": 0,
        "precision": 1.0,
    }
    assert likely_band["detections"] == 2
    assert likely_band["true_positives"] == 1
    assert likely_band["false_positives"] == 1
    assert likely_band["precision"] == pytest.approx(0.5)


def test_evaluator_handles_empty_inputs():
    detections = _build_detections([])
    ground_truth = _build_ground_truth([])

    evaluator = TransitionEvaluator(score_threshold=0.7)
    result = evaluator.evaluate(detections, ground_truth)

    assert result.precision == 0.0
    assert result.recall == 0.0
    assert result.f1 == 0.0
    assert result.support == 0
    assert isinstance(result.confusion, ConfusionMatrix)
    assert result.confusion.to_dict() == {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "total": 0}
    assert result.by_confidence == {}
    assert result.metadata["detections_total"] == 0
    assert result.metadata["ground_truth_total"] == 0


def test_evaluator_raises_when_detections_missing_columns():
    detections = _build_detections(
        [
            {
                "award_id": "A1",
                "contract_id": "C1",
                "confidence": "high",
            }
        ]
    )
    ground_truth = _build_ground_truth([{"award_id": "A1", "contract_id": "C1"}])

    evaluator = TransitionEvaluator(score_threshold=0.6)

    with pytest.raises(ValueError, match="detections_df missing required columns"):
        evaluator.evaluate(detections, ground_truth)
