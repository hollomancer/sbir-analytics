"""
Core evaluation utilities for the SBIR transition detection pipeline.

This module provides a `TransitionEvaluator` class that measures how well the
detector recovers known Phase III transitions. It focuses on computing classic
classification metrics (precision, recall, F1) along with a confusion matrix
and confidence-band summaries suitable for regression tracking.

Typical usage::

    evaluator = TransitionEvaluator(score_threshold=0.60)

    result = evaluator.evaluate(
        detections_df=transition_detections,
        ground_truth_df=phase3_awards,
        detection_id_columns=("award_id", "contract_id"),
    )

    print(result.precision, result.recall, result.confusion.tp)

The evaluator is intentionally lightweight and does not require Dagster or
other orchestration-specific dependencies; it operates purely on pandas
DataFrames so it can be reused in notebooks, CLI scripts, and CI checks.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass
class ConfusionMatrix:
    """Simple container for binary classification counts."""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0

    @property
    def total(self) -> int:
        """Total observations represented by the confusion matrix."""
        return self.tp + self.fp + self.fn + self.tn

    def to_dict(self) -> dict[str, int]:
        """Serialize the confusion matrix into a plain dictionary."""
        return {"tp": self.tp, "fp": self.fp, "fn": self.fn, "tn": self.tn, "total": self.total}


@dataclass
class EvaluationResult:
    """High-level summary of evaluation metrics."""

    precision: float
    recall: float
    f1: float
    support: int
    confusion: ConfusionMatrix
    by_confidence: dict[str, dict[str, Any]] = field(default_factory=dict)
    thresholds: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert the evaluation result to a JSON-serializable dict."""
        return {
            "precision": self.precision,
            "recall": self.recall,
            "f1": self.f1,
            "support": self.support,
            "confusion": self.confusion.to_dict(),
            "by_confidence": self.by_confidence,
            "thresholds": self.thresholds,
            "metadata": self.metadata,
        }


class TransitionEvaluator:
    """
    Compute detection quality metrics against a ground-truth dataset.

    Parameters
    ----------
    score_threshold:
        Minimum detection score required to count as a predicted transition.
    positive_confidence_levels:
        Confidence bands considered "positive" by default for reporting. The
        evaluator still respects the score threshold, but this list lets you
        slice metrics per-band without needing to remember the enum values.
    """

    def __init__(
        self,
        score_threshold: float = 0.60,
        positive_confidence_levels: Sequence[str] | None = None,
    ) -> None:
        self.score_threshold = score_threshold
        self.positive_confidence_levels = tuple(
            positive_confidence_levels or ("high", "likely", "possible")
        )

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def evaluate(
        self,
        detections_df: pd.DataFrame,
        ground_truth_df: pd.DataFrame,
        detection_id_columns: tuple[str, str] = ("award_id", "contract_id"),
        score_column: str = "likelihood_score",
        confidence_column: str = "confidence",
        ground_truth_label_column: str | None = None,
    ) -> EvaluationResult:
        """
        Compare detected transitions against a ground-truth set.

        Parameters
        ----------
        detections_df:
            DataFrame with detector output. Must contain the ID columns,
            likelihood score, and (optionally) confidence band.
        ground_truth_df:
            DataFrame describing known Phase III linkages. Must contain the
            same ID columns; can optionally carry a label column (defaults to
            treating every row as a positive example).
        detection_id_columns:
            Tuple naming the columns that uniquely identify an award→contract
            transition (defaults to `(award_id, contract_id)`).
        score_column:
            Column on `detections_df` containing the numeric likelihood score.
        confidence_column:
            Column on `detections_df` containing the confidence band/category.
        ground_truth_label_column:
            Optional column on `ground_truth_df` that identifies positive rows.
            When provided, only rows with truthy values are treated as positive.

        Returns
        -------
        EvaluationResult
            Precision, recall, F1, confusion matrix, and auxiliary metadata.
        """
        if detections_df.empty and ground_truth_df.empty:
            return self._empty_result()

        detected_pairs = self._extract_pairs(
            detections_df,
            id_columns=detection_id_columns,
            score_column=score_column,
        )
        truth_pairs = self._extract_ground_truth_pairs(
            ground_truth_df,
            id_columns=detection_id_columns,
            label_column=ground_truth_label_column,
        )

        confusion = self._build_confusion_matrix(detected_pairs, truth_pairs)

        precision = self._safe_divide(confusion.tp, confusion.tp + confusion.fp)
        recall = self._safe_divide(confusion.tp, truth_pairs["count"])
        f1 = self._safe_divide(2 * precision * recall, precision + recall)

        result = EvaluationResult(
            precision=precision,
            recall=recall,
            f1=f1,
            support=truth_pairs["count"],
            confusion=confusion,
            by_confidence=self._confidence_breakdown(
                detections_df,
                truth_pairs["set"],
                id_columns=detection_id_columns,
                score_column=score_column,
                confidence_column=confidence_column,
            ),
            thresholds={"score": self.score_threshold},
            metadata={
                "detections_total": len(detections_df),
                "ground_truth_total": truth_pairs["count"],
                "score_threshold": self.score_threshold,
                "positive_confidence_levels": self.positive_confidence_levels,
            },
        )
        return result

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

    def _empty_result(self) -> EvaluationResult:
        """Return a baseline result when both dataframes are empty."""
        return EvaluationResult(
            precision=0.0,
            recall=0.0,
            f1=0.0,
            support=0,
            confusion=ConfusionMatrix(),
            by_confidence={},
            thresholds={"score": self.score_threshold},
            metadata={
                "detections_total": 0,
                "ground_truth_total": 0,
                "score_threshold": self.score_threshold,
                "positive_confidence_levels": self.positive_confidence_levels,
            },
        )

    def _extract_pairs(
        self,
        detections_df: pd.DataFrame,
        id_columns: tuple[str, str],
        score_column: str,
    ) -> dict[str, Any]:
        """Materialize detected transitions above the score threshold."""
        if detections_df.empty:
            return {"set": set(), "count": 0}

        required_columns = set(id_columns) | {score_column}
        missing = required_columns - set(detections_df.columns)
        if missing:
            raise ValueError(f"detections_df missing required columns: {sorted(missing)}")

        df = detections_df.copy()
        df = df[pd.to_numeric(df[score_column], errors="coerce") >= self.score_threshold]

        pairs = {tuple(str(df[col].iloc[i]).strip() for col in id_columns) for i in range(len(df))}
        return {"set": pairs, "count": len(pairs)}

    def _extract_ground_truth_pairs(
        self,
        ground_truth_df: pd.DataFrame,
        id_columns: tuple[str, str],
        label_column: str | None,
    ) -> dict[str, Any]:
        """Materialize the set of known positive transitions."""
        if ground_truth_df.empty:
            return {"set": set(), "count": 0}

        missing = set(id_columns) - set(ground_truth_df.columns)
        if missing:
            raise ValueError(f"ground_truth_df missing ID columns: {sorted(missing)}")

        df = ground_truth_df.copy()
        if label_column and label_column in df.columns:
            df = df[df[label_column].astype(bool)]

        pairs = {tuple(str(df[col].iloc[i]).strip() for col in id_columns) for i in range(len(df))}
        return {"set": pairs, "count": len(pairs)}

    def _build_confusion_matrix(
        self,
        detected_pairs: dict[str, Any],
        truth_pairs: dict[str, Any],
    ) -> ConfusionMatrix:
        """Construct the confusion matrix from detected and true pairs."""
        detected_set = detected_pairs["set"]
        truth_set = truth_pairs["set"]

        tp = len(detected_set & truth_set)
        fp = len(detected_set - truth_set)
        fn = len(truth_set - detected_set)
        # TN is undefined without the full universe; we leave it at zero.
        return ConfusionMatrix(tp=tp, fp=fp, fn=fn, tn=0)

    def _confidence_breakdown(
        self,
        detections_df: pd.DataFrame,
        truth_pairs: Iterable[tuple[str, str]],
        id_columns: tuple[str, str],
        score_column: str,
        confidence_column: str,
    ) -> dict[str, dict[str, Any]]:
        """
        Produce per-confidence metrics to highlight band-specific performance.

        Returns a dictionary keyed by confidence band with counts of detections,
        true positives, false positives, and the effective threshold applied.
        """
        if detections_df.empty or confidence_column not in detections_df.columns:
            return {}

        truth_set = set(truth_pairs)
        breakdown: dict[str, dict[str, Any]] = {}

        df = detections_df.copy()
        df = df[pd.to_numeric(df[score_column], errors="coerce") >= self.score_threshold].copy()
        if df.empty:
            return {}

        for confidence, group in df.groupby(confidence_column):
            if confidence is None:
                confidence = "unknown"
            pairs = [
                tuple(str(group[col].iloc[i]).strip() for col in id_columns)
                for i in range(len(group))
            ]
            pairs_set = set(pairs)
            tp = len(pairs_set & truth_set)
            fp = len(pairs_set - truth_set)

            breakdown[str(confidence)] = {
                "detections": len(group),
                "true_positives": tp,
                "false_positives": fp,
                "precision": self._safe_divide(tp, tp + fp),
            }

        return breakdown

    def identify_false_positives(
        self,
        detections_df: pd.DataFrame,
        ground_truth_df: pd.DataFrame,
        detection_id_columns: tuple[str, str] = ("award_id", "contract_id"),
        score_column: str = "score",
        confidence_column: str = "confidence",
        truth_id_columns: tuple[str, str] = ("award_id", "contract_id"),
    ) -> pd.DataFrame:
        """
        Identify false positive detections for algorithm tuning (Task 18.8).

        Returns detections that do not appear in ground truth, sorted by score.
        These are candidates for algorithm refinement.

        Args:
            detections_df: DataFrame with detected transitions
            ground_truth_df: DataFrame with known Phase III transitions
            detection_id_columns: Columns identifying a detection pair
            score_column: Column name for detection score
            confidence_column: Column name for confidence level
            truth_id_columns: Columns identifying a ground truth pair

        Returns:
            DataFrame of false positive detections with analysis columns
        """
        # Build ground truth set
        truth_pairs = [
            tuple(str(ground_truth_df[col].iloc[i]).strip() for col in truth_id_columns)
            for i in range(len(ground_truth_df))
        ]
        truth_set = set(truth_pairs)

        # Build detection set
        df = detections_df.copy()
        df = df[pd.to_numeric(df[score_column], errors="coerce") >= self.score_threshold].copy()

        if df.empty:
            return pd.DataFrame()

        # Identify pairs
        detection_pairs = [
            tuple(str(df[col].iloc[i]).strip() for col in detection_id_columns)
            for i in range(len(df))
        ]

        # Mark false positives
        is_false_positive = [pair not in truth_set for pair in detection_pairs]
        df["is_false_positive"] = is_false_positive

        # Filter to false positives and sort by score (highest first)
        false_positives = df[df["is_false_positive"]].copy()
        false_positives = false_positives.sort_values(score_column, ascending=False)

        return false_positives

    def generate_evaluation_report(
        self,
        evaluation_result: EvaluationResult,
        detections_count: int = 0,
        ground_truth_count: int = 0,
    ) -> str:
        """
        Generate a human-readable evaluation report (Task 18.9).

        Includes metrics summary, confidence band breakdown, confusion matrix,
        and recommendations for algorithm tuning.

        Args:
            evaluation_result: EvaluationResult from evaluate()
            detections_count: Total number of detections analyzed
            ground_truth_count: Total ground truth samples

        Returns:
            Formatted markdown report string
        """
        lines = [
            "# Transition Detection Evaluation Report",
            "",
            f"**Analysis Date:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"**Score Threshold:** {self.score_threshold}",
            "",
            "## Overall Metrics",
            "",
            f"- **Precision:** {evaluation_result.precision:.1%}",
            "  - Correct detections / Total detections",
            f"  - TP={evaluation_result.confusion.tp}, FP={evaluation_result.confusion.fp}",
            "",
            f"- **Recall:** {evaluation_result.recall:.1%}",
            "  - Detected transitions / Total ground truth transitions",
            f"  - TP={evaluation_result.confusion.tp}, FN={evaluation_result.confusion.fn}",
            "",
            f"- **F1 Score:** {evaluation_result.f1:.3f}",
            "  - Harmonic mean of precision and recall",
            "",
            f"- **Support:** {evaluation_result.support} ground truth samples",
            "",
        ]

        # Confusion matrix
        lines.extend(
            [
                "## Confusion Matrix",
                "",
                "| Metric | Count |",
                "|--------|-------|",
                f"| True Positives (TP) | {evaluation_result.confusion.tp} |",
                f"| False Positives (FP) | {evaluation_result.confusion.fp} |",
                f"| False Negatives (FN) | {evaluation_result.confusion.fn} |",
                f"| True Negatives (TN) | {evaluation_result.confusion.tn} |",
                f"| **Total** | **{evaluation_result.confusion.total}** |",
                "",
            ]
        )

        # Confidence band breakdown
        if evaluation_result.by_confidence:
            lines.extend(
                [
                    "## Performance by Confidence Band",
                    "",
                ]
            )
            for confidence, metrics in evaluation_result.by_confidence.items():
                prec = metrics.get("precision", 0.0)
                lines.append(
                    f"- **{confidence}**: "
                    f"Detections={metrics.get('detections', 0)}, "
                    f"TP={metrics.get('true_positives', 0)}, "
                    f"FP={metrics.get('false_positives', 0)}, "
                    f"Precision={prec:.1%}"
                )
            lines.append("")

        # Recommendations
        lines.extend(
            [
                "## Recommendations for Algorithm Tuning",
                "",
            ]
        )

        if evaluation_result.precision < 0.80:
            lines.append("- ⚠️ **Low Precision:** Many false positives detected")
            lines.append("  - Consider increasing score threshold to reduce false positives")
            lines.append("  - Review false positive cases to identify systematic errors")
            lines.append("  - Adjust signal weights to reduce spurious matches")
            lines.append("")

        if evaluation_result.recall < 0.70:
            lines.append("- ⚠️ **Low Recall:** Missing known transitions")
            lines.append("  - Consider lowering score threshold to catch more transitions")
            lines.append("  - Analyze false negatives to identify missing signal types")
            lines.append("  - Increase weights for signals that correlate with true transitions")
            lines.append("")

        if evaluation_result.precision >= 0.80 and evaluation_result.recall >= 0.70:
            lines.append("- ✓ **Good Performance:** Algorithm meets quality targets")
            lines.append("  - Precision and recall are well-balanced")
            lines.append("  - Continue monitoring with additional validation data")
            lines.append("")

        # Confidence band recommendations
        if evaluation_result.by_confidence:
            low_precision_bands = [
                conf
                for conf, metrics in evaluation_result.by_confidence.items()
                if metrics.get("precision", 0.0) < 0.75
            ]
            if low_precision_bands:
                lines.append(
                    f"- Consider reviewing detection signals for low-precision bands: "
                    f"{', '.join(low_precision_bands)}"
                )
                lines.append("")

        lines.extend(
            [
                "## Next Steps",
                "",
                "1. Review false positive cases to identify systematic issues",
                "2. Validate recall by checking false negatives",
                "3. Test algorithm adjustments on held-out validation set",
                "4. Monitor precision and recall post-deployment",
                "5. Collect feedback on detection quality from domain experts",
                "",
            ]
        )

        return "\n".join(lines)

    @staticmethod
    def _safe_divide(numerator: float, denominator: float) -> float:
        """Guard against division-by-zero, returning 0.0 instead."""
        if denominator == 0:
            return 0.0
        return numerator / denominator
