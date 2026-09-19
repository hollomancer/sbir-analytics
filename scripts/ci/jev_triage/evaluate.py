"""Offline evaluation for labeled Jev CI triage predictions."""

import json
from collections import defaultdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .models import FailureClass, JevTriageDecision, OwnerArea, RecommendedAction


EPISTEMIC_TIER = "exploratory"


class EvaluationExample(BaseModel):
    """One human-labeled failure used by the private evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1, max_length=120)
    split: str = Field(pattern=r"^(development|holdout)$")
    gold_failure_class: FailureClass
    gold_owner_area: OwnerArea
    retry_safe: bool


class EvaluationPrediction(BaseModel):
    """One model or fixture prediction aligned to a labeled failure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1, max_length=120)
    decision: JevTriageDecision
    recommended_action: RecommendedAction
    request_succeeded: bool
    latency_ms: float = Field(ge=0.0)
    sanitizer_accepted: bool


def _read_jsonl(path: Path, model_type: type[BaseModel]) -> list[BaseModel]:
    records: list[BaseModel] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            records.append(model_type.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(f"{path}:{line_number}: invalid record: {exc}") from exc
    return records


def load_examples(path: Path) -> list[EvaluationExample]:
    """Load strict evaluation labels from JSON Lines."""

    return [EvaluationExample.model_validate(record) for record in _read_jsonl(path, EvaluationExample)]


def load_predictions(path: Path) -> list[EvaluationPrediction]:
    """Load strict predictions from JSON Lines."""

    return [
        EvaluationPrediction.model_validate(record)
        for record in _read_jsonl(path, EvaluationPrediction)
    ]


def evaluate_predictions(
    examples: list[EvaluationExample],
    predictions: list[EvaluationPrediction],
    *,
    split: str = "holdout",
    synthetic_fixture: bool = False,
) -> dict[str, object]:
    """Score routing, retry safety, availability, latency, and calibration."""

    selected = [example for example in examples if example.split == split]
    labels = {example.case_id: example for example in selected}
    if len(labels) != len(selected):
        raise ValueError(f"duplicate case_id in {split} labels")
    prediction_map = {prediction.case_id: prediction for prediction in predictions}
    if len(prediction_map) != len(predictions):
        raise ValueError("duplicate case_id in predictions")

    missing = sorted(set(labels) - set(prediction_map))
    unexpected = sorted(set(prediction_map) - set(labels))
    matched_ids = sorted(set(labels) & set(prediction_map))
    matched = [(labels[case_id], prediction_map[case_id]) for case_id in matched_ids]

    successful = [(label, prediction) for label, prediction in matched if prediction.request_succeeded]
    class_correct = sum(
        prediction.decision.failure_class is label.gold_failure_class
        for label, prediction in successful
    )
    owner_correct = sum(
        prediction.decision.owner_area is label.gold_owner_area
        for label, prediction in successful
    )
    retries = [pair for pair in successful if pair[1].recommended_action is RecommendedAction.RETRY_ONCE]
    safe_retries = sum(label.retry_safe for label, _ in retries)

    buckets: dict[int, list[tuple[float, bool]]] = defaultdict(list)
    for label, prediction in successful:
        confidence = prediction.decision.failure_class_confidence
        bucket = min(int(confidence * 5), 4)
        buckets[bucket].append(
            (confidence, prediction.decision.failure_class is label.gold_failure_class)
        )
    calibration = []
    for bucket, values in sorted(buckets.items()):
        mean_confidence = sum(value[0] for value in values) / len(values)
        accuracy = sum(value[1] for value in values) / len(values)
        calibration.append(
            {
                "lower": bucket / 5,
                "upper": (bucket + 1) / 5,
                "count": len(values),
                "mean_confidence": mean_confidence,
                "accuracy": accuracy,
                "absolute_gap": abs(mean_confidence - accuracy),
            }
        )

    def ratio(numerator: int, denominator: int) -> float | None:
        return numerator / denominator if denominator else None

    return {
        "schema_version": 1,
        "epistemic_tier": "exploratory",
        "citable": False,
        "synthetic_fixture": synthetic_fixture,
        "split": split,
        "labeled_cases": len(selected),
        "matched_cases": len(matched),
        "missing_prediction_ids": missing,
        "unexpected_prediction_ids": unexpected,
        "failure_class_accuracy": ratio(class_correct, len(successful)),
        "owner_area_accuracy": ratio(owner_correct, len(successful)),
        "retry_recommendations": len(retries),
        "retry_precision": ratio(safe_retries, len(retries)),
        "unsafe_retry_count": len(retries) - safe_retries,
        "request_availability": ratio(len(successful), len(selected)),
        "mean_latency_ms": (
            sum(prediction.latency_ms for _, prediction in matched) / len(matched)
            if matched
            else None
        ),
        "sanitizer_acceptance_rate": ratio(
            sum(prediction.sanitizer_accepted for _, prediction in matched),
            len(matched),
        ),
        "confidence_calibration": calibration,
    }


def write_evaluation_report(report: dict[str, object], output: Path) -> None:
    """Write one stable JSON report."""

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
