"""
Tests for src/transition/evaluation/evaluator.py

Tests the TransitionEvaluator for measuring transition detection quality
against ground truth using precision, recall, F1, and confusion matrices.
"""

import pandas as pd
import pytest

from src.transition.evaluation.evaluator import (
    ConfusionMatrix,
    EvaluationResult,
    TransitionEvaluator,
)


@pytest.fixture
def evaluator():
    """Default TransitionEvaluator for testing."""
    return TransitionEvaluator(score_threshold=0.60)


@pytest.fixture
def sample_detections():
    """Sample detection DataFrame."""
    return pd.DataFrame(
        {
            "award_id": ["AWD001", "AWD001", "AWD002", "AWD003"],
            "contract_id": ["CTR001", "CTR002", "CTR001", "CTR003"],
            "likelihood_score": [0.85, 0.65, 0.75, 0.55],  # Last one below threshold
            "confidence": ["high", "likely", "likely", "possible"],
        }
    )


@pytest.fixture
def sample_ground_truth():
    """Sample ground truth DataFrame."""
    return pd.DataFrame(
        {
            "award_id": ["AWD001", "AWD002", "AWD004"],
            "contract_id": ["CTR001", "CTR001", "CTR004"],
        }
    )


class TestConfusionMatrix:
    """Tests for ConfusionMatrix dataclass."""

    def test_confusion_matrix_creation(self):
        """Test creating a ConfusionMatrix."""
        cm = ConfusionMatrix(tp=10, fp=5, fn=3, tn=2)

        assert cm.tp == 10
        assert cm.fp == 5
        assert cm.fn == 3
        assert cm.tn == 2

    def test_confusion_matrix_defaults(self):
        """Test ConfusionMatrix default values."""
        cm = ConfusionMatrix()

        assert cm.tp == 0
        assert cm.fp == 0
        assert cm.fn == 0
        assert cm.tn == 0

    def test_confusion_matrix_total(self):
        """Test ConfusionMatrix total property."""
        cm = ConfusionMatrix(tp=10, fp=5, fn=3, tn=2)

        assert cm.total == 20

    def test_confusion_matrix_to_dict(self):
        """Test ConfusionMatrix serialization to dict."""
        cm = ConfusionMatrix(tp=10, fp=5, fn=3, tn=2)

        result = cm.to_dict()

        assert result["tp"] == 10
        assert result["fp"] == 5
        assert result["fn"] == 3
        assert result["tn"] == 2
        assert result["total"] == 20


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_evaluation_result_creation(self):
        """Test creating an EvaluationResult."""
        cm = ConfusionMatrix(tp=10, fp=5, fn=3, tn=2)
        result = EvaluationResult(
            precision=0.85,
            recall=0.75,
            f1=0.80,
            support=100,
            confusion=cm,
            by_confidence={"high": {"precision": 0.90}},
            thresholds={"score": 0.60},
            metadata={"test": "data"},
        )

        assert result.precision == 0.85
        assert result.recall == 0.75
        assert result.f1 == 0.80
        assert result.support == 100
        assert result.confusion == cm

    def test_evaluation_result_defaults(self):
        """Test EvaluationResult default values."""
        cm = ConfusionMatrix()
        result = EvaluationResult(precision=0.0, recall=0.0, f1=0.0, support=0, confusion=cm)

        assert result.by_confidence == {}
        assert result.thresholds == {}
        assert result.metadata == {}

    def test_evaluation_result_to_dict(self):
        """Test EvaluationResult serialization to dict."""
        cm = ConfusionMatrix(tp=10, fp=5, fn=3, tn=0)
        result = EvaluationResult(
            precision=0.85,
            recall=0.75,
            f1=0.80,
            support=100,
            confusion=cm,
        )

        result_dict = result.to_dict()

        assert result_dict["precision"] == 0.85
        assert result_dict["recall"] == 0.75
        assert result_dict["f1"] == 0.80
        assert result_dict["support"] == 100
        assert result_dict["confusion"]["tp"] == 10


class TestTransitionEvaluatorInitialization:
    """Tests for TransitionEvaluator initialization."""

    def test_initialization_defaults(self):
        """Test initialization with default parameters."""
        evaluator = TransitionEvaluator()

        assert evaluator.score_threshold == 0.60
        assert evaluator.positive_confidence_levels == ("high", "likely", "possible")

    def test_initialization_custom_threshold(self):
        """Test initialization with custom score threshold."""
        evaluator = TransitionEvaluator(score_threshold=0.75)

        assert evaluator.score_threshold == 0.75

    def test_initialization_custom_confidence_levels(self):
        """Test initialization with custom confidence levels."""
        evaluator = TransitionEvaluator(positive_confidence_levels=["high", "likely"])

        assert evaluator.positive_confidence_levels == ("high", "likely")


class TestEvaluate:
    """Tests for evaluate method."""

    def test_evaluate_perfect_match(self, evaluator):
        """Test evaluation with perfect precision and recall."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
                "likelihood_score": [0.85, 0.75],
                "confidence": ["high", "likely"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
            }
        )

        result = evaluator.evaluate(detections, ground_truth)

        assert result.precision == 1.0
        assert result.recall == 1.0
        assert result.f1 == 1.0
        assert result.confusion.tp == 2
        assert result.confusion.fp == 0
        assert result.confusion.fn == 0

    def test_evaluate_with_false_positives(self, evaluator):
        """Test evaluation with false positives."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003"],
                "contract_id": ["CTR001", "CTR002", "CTR003"],
                "likelihood_score": [0.85, 0.75, 0.70],
                "confidence": ["high", "likely", "likely"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
            }
        )

        result = evaluator.evaluate(detections, ground_truth)

        # 2 TP, 1 FP, 0 FN
        assert result.confusion.tp == 2
        assert result.confusion.fp == 1
        assert result.confusion.fn == 0
        # Precision = 2/3 = 0.6667
        assert result.precision == pytest.approx(0.6667, rel=0.01)
        # Recall = 2/2 = 1.0
        assert result.recall == 1.0

    def test_evaluate_with_false_negatives(self, evaluator):
        """Test evaluation with false negatives."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001"],
                "contract_id": ["CTR001"],
                "likelihood_score": [0.85],
                "confidence": ["high"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003"],
                "contract_id": ["CTR001", "CTR002", "CTR003"],
            }
        )

        result = evaluator.evaluate(detections, ground_truth)

        # 1 TP, 0 FP, 2 FN
        assert result.confusion.tp == 1
        assert result.confusion.fp == 0
        assert result.confusion.fn == 2
        # Precision = 1/1 = 1.0
        assert result.precision == 1.0
        # Recall = 1/3 = 0.3333
        assert result.recall == pytest.approx(0.3333, rel=0.01)

    def test_evaluate_filters_by_score_threshold(self, evaluator):
        """Test evaluation filters detections by score threshold."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
                "likelihood_score": [0.85, 0.55],  # Second is below 0.60 threshold
                "confidence": ["high", "possible"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
            }
        )

        result = evaluator.evaluate(detections, ground_truth)

        # Only AWD001-CTR001 should be counted (score 0.85 >= 0.60)
        # AWD002-CTR002 is below threshold, so it's a false negative
        assert result.confusion.tp == 1
        assert result.confusion.fp == 0
        assert result.confusion.fn == 1
        # Recall = 1/2 = 0.5
        assert result.recall == 0.5

    def test_evaluate_empty_detections(self, evaluator):
        """Test evaluation with empty detections."""
        detections = pd.DataFrame(
            columns=["award_id", "contract_id", "likelihood_score", "confidence"]
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001"],
                "contract_id": ["CTR001"],
            }
        )

        result = evaluator.evaluate(detections, ground_truth)

        assert result.confusion.tp == 0
        assert result.confusion.fp == 0
        assert result.confusion.fn == 1
        assert result.precision == 0.0
        assert result.recall == 0.0

    def test_evaluate_empty_ground_truth(self, evaluator):
        """Test evaluation with empty ground truth."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001"],
                "contract_id": ["CTR001"],
                "likelihood_score": [0.85],
                "confidence": ["high"],
            }
        )
        ground_truth = pd.DataFrame(columns=["award_id", "contract_id"])

        result = evaluator.evaluate(detections, ground_truth)

        # All detections are false positives
        assert result.confusion.tp == 0
        assert result.confusion.fp == 1
        assert result.confusion.fn == 0
        assert result.precision == 0.0
        assert result.recall == 0.0

    def test_evaluate_both_empty(self, evaluator):
        """Test evaluation with both dataframes empty."""
        detections = pd.DataFrame(columns=["award_id", "contract_id", "likelihood_score"])
        ground_truth = pd.DataFrame(columns=["award_id", "contract_id"])

        result = evaluator.evaluate(detections, ground_truth)

        assert result.precision == 0.0
        assert result.recall == 0.0
        assert result.f1 == 0.0
        assert result.support == 0

    def test_evaluate_with_confidence_breakdown(self, evaluator):
        """Test evaluation includes confidence band breakdown."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003"],
                "contract_id": ["CTR001", "CTR002", "CTR003"],
                "likelihood_score": [0.90, 0.75, 0.65],
                "confidence": ["high", "likely", "possible"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
            }
        )

        result = evaluator.evaluate(detections, ground_truth)

        # Should have breakdown by confidence
        assert "high" in result.by_confidence
        assert "likely" in result.by_confidence
        assert "possible" in result.by_confidence

        # High confidence should have perfect precision
        assert result.by_confidence["high"]["precision"] == 1.0
        assert result.by_confidence["high"]["true_positives"] == 1
        assert result.by_confidence["high"]["false_positives"] == 0

    def test_evaluate_missing_required_columns(self, evaluator):
        """Test evaluation raises error for missing columns."""
        detections = pd.DataFrame({"award_id": ["AWD001"]})  # Missing contract_id and score
        ground_truth = pd.DataFrame({"award_id": ["AWD001"], "contract_id": ["CTR001"]})

        with pytest.raises(ValueError, match="missing required columns"):
            evaluator.evaluate(detections, ground_truth)

    def test_evaluate_with_custom_column_names(self, evaluator):
        """Test evaluation with custom column names."""
        detections = pd.DataFrame(
            {
                "sbir_id": ["AWD001"],
                "fed_contract_id": ["CTR001"],
                "likelihood_score": [0.85],
                "confidence": ["high"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "sbir_id": ["AWD001"],
                "fed_contract_id": ["CTR001"],
            }
        )

        result = evaluator.evaluate(
            detections,
            ground_truth,
            detection_id_columns=("sbir_id", "fed_contract_id"),
        )

        assert result.confusion.tp == 1
        assert result.precision == 1.0

    def test_evaluate_with_ground_truth_label_column(self, evaluator):
        """Test evaluation with ground truth label column."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
                "likelihood_score": [0.85, 0.75],
                "confidence": ["high", "likely"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003"],
                "contract_id": ["CTR001", "CTR002", "CTR003"],
                "is_transition": [True, True, False],  # AWD003 is not a transition
            }
        )

        result = evaluator.evaluate(
            detections,
            ground_truth,
            ground_truth_label_column="is_transition",
        )

        # Should only count AWD001 and AWD002 as ground truth (AWD003 is False)
        assert result.support == 2
        assert result.confusion.tp == 2
        assert result.recall == 1.0


class TestIdentifyFalsePositives:
    """Tests for identify_false_positives method."""

    def test_identify_false_positives_success(self, evaluator):
        """Test identifying false positives."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003"],
                "contract_id": ["CTR001", "CTR002", "CTR003"],
                "score": [0.90, 0.75, 0.65],
                "confidence": ["high", "likely", "possible"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001"],
                "contract_id": ["CTR001"],
            }
        )

        fps = evaluator.identify_false_positives(detections, ground_truth, score_column="score")

        # AWD002 and AWD003 are false positives
        assert len(fps) == 2
        assert "is_false_positive" in fps.columns
        assert all(fps["is_false_positive"])

    def test_identify_false_positives_sorted_by_score(self, evaluator):
        """Test false positives are sorted by score (highest first)."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003"],
                "contract_id": ["CTR001", "CTR002", "CTR003"],
                "score": [0.65, 0.90, 0.75],  # Unsorted
                "confidence": ["possible", "high", "likely"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001"],
                "contract_id": ["CTR001"],
            }
        )

        fps = evaluator.identify_false_positives(detections, ground_truth, score_column="score")

        # Should be sorted by score descending
        assert fps.iloc[0]["score"] == 0.90
        assert fps.iloc[1]["score"] == 0.75

    def test_identify_false_positives_empty_when_all_correct(self, evaluator):
        """Test returns empty DataFrame when all detections are correct."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001"],
                "contract_id": ["CTR001"],
                "score": [0.85],
                "confidence": ["high"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001"],
                "contract_id": ["CTR001"],
            }
        )

        fps = evaluator.identify_false_positives(detections, ground_truth, score_column="score")

        assert len(fps) == 0

    def test_identify_false_positives_filters_by_threshold(self, evaluator):
        """Test false positives are filtered by score threshold."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
                "score": [0.90, 0.50],  # Second is below 0.60 threshold
                "confidence": ["high", "possible"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD003"],
                "contract_id": ["CTR003"],
            }
        )

        fps = evaluator.identify_false_positives(detections, ground_truth, score_column="score")

        # Only AWD001 should be counted (AWD002 is below threshold)
        assert len(fps) == 1
        assert fps.iloc[0]["award_id"] == "AWD001"


class TestGenerateEvaluationReport:
    """Tests for generate_evaluation_report method."""

    def test_generate_evaluation_report_basic(self, evaluator):
        """Test generating basic evaluation report."""
        cm = ConfusionMatrix(tp=10, fp=5, fn=3, tn=0)
        result = EvaluationResult(
            precision=0.667,
            recall=0.769,
            f1=0.714,
            support=13,
            confusion=cm,
        )

        report = evaluator.generate_evaluation_report(result)

        # Check report contains key sections
        assert "# Transition Detection Evaluation Report" in report
        assert "## Overall Metrics" in report
        assert "## Confusion Matrix" in report
        assert "Precision:** 66.7%" in report
        assert "Recall:** 76.9%" in report
        assert "True Positives (TP) | 10" in report

    def test_generate_evaluation_report_with_confidence_breakdown(self, evaluator):
        """Test report includes confidence band breakdown."""
        cm = ConfusionMatrix(tp=10, fp=5, fn=3, tn=0)
        result = EvaluationResult(
            precision=0.667,
            recall=0.769,
            f1=0.714,
            support=13,
            confusion=cm,
            by_confidence={
                "high": {
                    "detections": 5,
                    "true_positives": 5,
                    "false_positives": 0,
                    "precision": 1.0,
                },
                "likely": {
                    "detections": 8,
                    "true_positives": 4,
                    "false_positives": 4,
                    "precision": 0.5,
                },
            },
        )

        report = evaluator.generate_evaluation_report(result)

        assert "## Performance by Confidence Band" in report
        assert "**high**" in report
        assert "Precision=100.0%" in report
        assert "**likely**" in report

    def test_generate_evaluation_report_low_precision_warning(self, evaluator):
        """Test report includes warning for low precision."""
        cm = ConfusionMatrix(tp=5, fp=15, fn=2, tn=0)
        result = EvaluationResult(
            precision=0.25,  # Low precision
            recall=0.714,
            f1=0.370,
            support=7,
            confusion=cm,
        )

        report = evaluator.generate_evaluation_report(result)

        assert "⚠️ **Low Precision:**" in report
        assert "increasing score threshold" in report

    def test_generate_evaluation_report_low_recall_warning(self, evaluator):
        """Test report includes warning for low recall."""
        cm = ConfusionMatrix(tp=3, fp=1, fn=7, tn=0)
        result = EvaluationResult(
            precision=0.75,
            recall=0.30,  # Low recall
            f1=0.429,
            support=10,
            confusion=cm,
        )

        report = evaluator.generate_evaluation_report(result)

        assert "⚠️ **Low Recall:**" in report
        assert "lowering score threshold" in report

    def test_generate_evaluation_report_good_performance(self, evaluator):
        """Test report includes success message for good performance."""
        cm = ConfusionMatrix(tp=80, fp=10, fn=10, tn=0)
        result = EvaluationResult(
            precision=0.889,  # Good precision
            recall=0.889,  # Good recall
            f1=0.889,
            support=90,
            confusion=cm,
        )

        report = evaluator.generate_evaluation_report(result)

        assert "✓ **Good Performance:**" in report
        assert "Algorithm meets quality targets" in report

    def test_generate_evaluation_report_includes_next_steps(self, evaluator):
        """Test report includes next steps section."""
        cm = ConfusionMatrix(tp=10, fp=5, fn=3, tn=0)
        result = EvaluationResult(
            precision=0.667,
            recall=0.769,
            f1=0.714,
            support=13,
            confusion=cm,
        )

        report = evaluator.generate_evaluation_report(result)

        assert "## Next Steps" in report
        assert "Review false positive cases" in report
        assert "Validate recall" in report


class TestInternalHelpers:
    """Tests for internal helper methods."""

    def test_safe_divide_normal(self):
        """Test safe divide with normal values."""
        result = TransitionEvaluator._safe_divide(10.0, 2.0)

        assert result == 5.0

    def test_safe_divide_by_zero(self):
        """Test safe divide returns 0.0 for division by zero."""
        result = TransitionEvaluator._safe_divide(10.0, 0.0)

        assert result == 0.0

    def test_safe_divide_both_zero(self):
        """Test safe divide with both values zero."""
        result = TransitionEvaluator._safe_divide(0.0, 0.0)

        assert result == 0.0

    def test_extract_pairs_success(self, evaluator):
        """Test _extract_pairs extracts detection pairs correctly."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
                "likelihood_score": [0.85, 0.75],
            }
        )

        pairs_dict = evaluator._extract_pairs(
            detections,
            id_columns=("award_id", "contract_id"),
            score_column="likelihood_score",
        )

        assert pairs_dict["count"] == 2
        assert ("AWD001", "CTR001") in pairs_dict["set"]
        assert ("AWD002", "CTR002") in pairs_dict["set"]

    def test_extract_pairs_filters_by_threshold(self, evaluator):
        """Test _extract_pairs filters by score threshold."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003"],
                "contract_id": ["CTR001", "CTR002", "CTR003"],
                "likelihood_score": [0.85, 0.75, 0.55],  # Last is below 0.60
            }
        )

        pairs_dict = evaluator._extract_pairs(
            detections,
            id_columns=("award_id", "contract_id"),
            score_column="likelihood_score",
        )

        # Only first two should be included
        assert pairs_dict["count"] == 2
        assert ("AWD003", "CTR003") not in pairs_dict["set"]

    def test_extract_pairs_empty_dataframe(self, evaluator):
        """Test _extract_pairs with empty DataFrame."""
        detections = pd.DataFrame(columns=["award_id", "contract_id", "likelihood_score"])

        pairs_dict = evaluator._extract_pairs(
            detections,
            id_columns=("award_id", "contract_id"),
            score_column="likelihood_score",
        )

        assert pairs_dict["count"] == 0
        assert len(pairs_dict["set"]) == 0

    def test_extract_ground_truth_pairs_success(self, evaluator):
        """Test _extract_ground_truth_pairs extracts pairs correctly."""
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
            }
        )

        pairs_dict = evaluator._extract_ground_truth_pairs(
            ground_truth,
            id_columns=("award_id", "contract_id"),
            label_column=None,
        )

        assert pairs_dict["count"] == 2
        assert ("AWD001", "CTR001") in pairs_dict["set"]

    def test_extract_ground_truth_pairs_with_label_column(self, evaluator):
        """Test _extract_ground_truth_pairs filters by label column."""
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002", "AWD003"],
                "contract_id": ["CTR001", "CTR002", "CTR003"],
                "is_transition": [True, True, False],
            }
        )

        pairs_dict = evaluator._extract_ground_truth_pairs(
            ground_truth,
            id_columns=("award_id", "contract_id"),
            label_column="is_transition",
        )

        # Only first two should be included
        assert pairs_dict["count"] == 2
        assert ("AWD003", "CTR003") not in pairs_dict["set"]

    def test_build_confusion_matrix(self, evaluator):
        """Test _build_confusion_matrix calculates TP, FP, FN correctly."""
        detected = {"set": {("AWD001", "CTR001"), ("AWD002", "CTR002"), ("AWD003", "CTR003")}}
        truth = {"set": {("AWD001", "CTR001"), ("AWD002", "CTR002"), ("AWD004", "CTR004")}}

        cm = evaluator._build_confusion_matrix(detected, truth)

        # TP: AWD001, AWD002 (in both sets)
        assert cm.tp == 2
        # FP: AWD003 (detected but not in truth)
        assert cm.fp == 1
        # FN: AWD004 (in truth but not detected)
        assert cm.fn == 1
        # TN: undefined without full universe
        assert cm.tn == 0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_evaluate_with_non_numeric_scores(self, evaluator):
        """Test evaluation handles non-numeric scores gracefully."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
                "likelihood_score": ["invalid", 0.85],
                "confidence": ["high", "likely"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
            }
        )

        # Should handle non-numeric values by coercing to NaN
        result = evaluator.evaluate(detections, ground_truth)

        # Only one valid detection (AWD002 with score 0.85)
        assert result.confusion.tp == 1

    def test_evaluate_strips_whitespace_from_ids(self, evaluator):
        """Test evaluation strips whitespace from IDs."""
        detections = pd.DataFrame(
            {
                "award_id": ["  AWD001  ", "AWD002"],
                "contract_id": ["CTR001", "  CTR002  "],
                "likelihood_score": [0.85, 0.75],
                "confidence": ["high", "likely"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
            }
        )

        result = evaluator.evaluate(detections, ground_truth)

        # Should match despite whitespace differences
        assert result.confusion.tp == 2
        assert result.precision == 1.0

    def test_confidence_breakdown_with_none_confidence(self, evaluator):
        """Test confidence breakdown handles None confidence values."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD002"],
                "contract_id": ["CTR001", "CTR002"],
                "likelihood_score": [0.85, 0.75],
                "confidence": ["high", None],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001"],
                "contract_id": ["CTR001"],
            }
        )

        result = evaluator.evaluate(detections, ground_truth)

        # Should handle None confidence as "unknown"
        assert "unknown" in result.by_confidence or len(result.by_confidence) == 1

    def test_evaluate_with_duplicate_pairs(self, evaluator):
        """Test evaluation handles duplicate detection pairs."""
        detections = pd.DataFrame(
            {
                "award_id": ["AWD001", "AWD001"],  # Duplicate pair
                "contract_id": ["CTR001", "CTR001"],
                "likelihood_score": [0.85, 0.75],
                "confidence": ["high", "likely"],
            }
        )
        ground_truth = pd.DataFrame(
            {
                "award_id": ["AWD001"],
                "contract_id": ["CTR001"],
            }
        )

        result = evaluator.evaluate(detections, ground_truth)

        # Duplicate should only count once
        assert result.confusion.tp == 1
