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

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Sequence, Tuple

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

    def to_dict(self) -> Dict[str, int]:
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
    by_confidence: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    thresholds: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
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
        positive_confidence_levels: Optional[Sequence[str]] = None,
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
        detection_id_columns: Tuple[str, str] = ("award_id", "contract_id"),
        score_column: str = "likelihood_score",
        confidence_column: str = "confidence",
        ground_truth_label_column: Optional[str] = None,
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
            thresholds={"score": self.score_threshold},
        )

    def _extract_pairs(
        self,
        detections_df: pd.DataFrame,
        id_columns: Tuple[str, str],
        score_column: str,
    ) -> Dict[str, Any]:
        """Materialize detected transitions above the score threshold."""
        if detections_df.empty:
            return {"set": set(), "count": 0}

        required_columns = set(id_columns) | {score_column}
        missing = required_columns - set(detections_df.columns)
        if missing:
            raise ValueError(f"detections_df missing required columns: {sorted(missing)}")

        df = detections_df.copy()
        df = df[pd.to_numeric(df[score_column], errors="coerce") >= self.score_threshold]

        pairs = set(
            tuple(str(df[col].iloc[i]).strip() for col in id_columns) for i in range(len(df))
        )
        return {"set": pairs, "count": len(pairs)}

    def _extract_ground_truth_pairs(
        self,
        ground_truth_df: pd.DataFrame,
        id_columns: Tuple[str, str],
        label_column: Optional[str],
    ) -> Dict[str, Any]:
        """Materialize the set of known positive transitions."""
        if ground_truth_df.empty:
            return {"set": set(), "count": 0}

        missing = set(id_columns) - set(ground_truth_df.columns)
        if missing:
            raise ValueError(f"ground_truth_df missing ID columns: {sorted(missing)}")

        df = ground_truth_df.copy()
        if label_column and label_column in df.columns:
            df = df[df[label_column].astype(bool)]

        pairs = set(
            tuple(str(df[col].iloc[i]).strip() for col in id_columns) for i in range(len(df))
        )
        return {"set": pairs, "count": len(pairs)}

    def _build_confusion_matrix(
        self,
        detected_pairs: Dict[str, Any],
        truth_pairs: Dict[str, Any],
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
        truth_pairs: Iterable[Tuple[str, str]],
        id_columns: Tuple[str, str],
        score_column: str,
        confidence_column: str,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Produce per-confidence metrics to highlight band-specific performance.

        Returns a dictionary keyed by confidence band with counts of detections,
        true positives, false positives, and the effective threshold applied.
        """
        if detections_df.empty or confidence_column not in detections_df.columns:
            return {}

        truth_set = set(truth_pairs)
        breakdown: Dict[str, Dict[str, Any]] = {}

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

    @staticmethod
    def _safe_divide(numerator: float, denominator: float) -> float:
        """Guard against division-by-zero, returning 0.0 instead."""
        if denominator == 0:
            return 0.0
        return numerator / denominator
