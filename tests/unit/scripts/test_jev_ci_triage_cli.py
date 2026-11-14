"""Tests for no-key Jev CI triage execution and evaluation."""

import argparse
import json
from pathlib import Path

import pytest

from scripts.ci.jev_triage.cli import run_dry_run, run_evaluate
from scripts.ci.jev_triage.evaluate import (
    EvaluationExample,
    EvaluationPrediction,
    evaluate_predictions,
    load_examples,
    load_predictions,
)
from scripts.ci.jev_triage.models import RecommendedAction


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPOSITORY_ROOT / "tests" / "fixtures" / "jev_ci_triage"


def test_dry_run_writes_redacted_non_citable_artifacts(tmp_path: Path) -> None:
    output_dir = tmp_path / "output"
    args = argparse.Namespace(
        junit_dir=FIXTURES,
        fake_decision=FIXTURES / "fake-decision.json",
        output_dir=output_dir,
        check_name="Fast Tests",
        command_family="pytest",
        exit_code=1,
        runner_os="ubuntu-latest",
        attempt_number=1,
        changed_path_group=["tests/unit"],
    )

    assert run_dry_run(args) == 0

    envelopes = (output_dir / "failure_envelopes.jsonl").read_text(encoding="utf-8")
    results = (output_dir / "triage_results.jsonl").read_text(encoding="utf-8")
    manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    summary = (output_dir / "summary.md").read_text(encoding="utf-8")

    assert "ghp_abcdefghijklmnop" not in envelopes
    assert "first second" not in envelopes
    assert envelopes.count("[REDACTED]") == 2
    assert '"action":"human_triage"' in results
    assert manifest["citable"] is False
    assert manifest["mode"] == "fake"
    assert manifest["network_calls"] == 0
    assert manifest["failures_classified"] == 1
    assert "not an explanation of hidden model reasoning" in summary


def test_dry_run_requires_at_least_one_junit_report(tmp_path: Path) -> None:
    args = argparse.Namespace(
        junit_dir=tmp_path,
        fake_decision=FIXTURES / "fake-decision.json",
        output_dir=tmp_path / "output",
        check_name="Fast Tests",
        command_family="pytest",
        exit_code=1,
        runner_os="ubuntu-latest",
        attempt_number=1,
        changed_path_group=[],
    )

    with pytest.raises(ValueError, match="no JUnit XML files found"):
        run_dry_run(args)


def test_dry_run_records_no_failures_for_passing_junit(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "passing.xml").write_text(
        '<testsuite tests="1"><testcase classname="suite" name="test_pass" /></testsuite>',
        encoding="utf-8",
    )
    output_dir = tmp_path / "output"
    args = argparse.Namespace(
        junit_dir=input_dir,
        fake_decision=FIXTURES / "fake-decision.json",
        output_dir=output_dir,
        check_name="Fast Tests",
        command_family="pytest",
        exit_code=0,
        runner_os="ubuntu-latest",
        attempt_number=1,
        changed_path_group=[],
    )

    assert run_dry_run(args) == 0
    manifest = json.loads((output_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["failures_classified"] == 0
    assert (output_dir / "failure_envelopes.jsonl").read_text(encoding="utf-8") == ""
    assert "No failed JUnit cases were found" in (output_dir / "summary.md").read_text(
        encoding="utf-8"
    )


def test_synthetic_evaluation_reports_expected_metrics(tmp_path: Path) -> None:
    output = tmp_path / "evaluation.json"
    args = argparse.Namespace(
        corpus=FIXTURES / "evaluation-corpus.jsonl",
        predictions=FIXTURES / "evaluation-predictions.jsonl",
        output=output,
        split="holdout",
        synthetic_fixture=True,
    )

    assert run_evaluate(args) == 0
    report = json.loads(output.read_text(encoding="utf-8"))

    assert report["synthetic_fixture"] is True
    assert report["citable"] is False
    assert report["labeled_cases"] == 3
    assert report["failure_class_accuracy"] == pytest.approx(2 / 3)
    assert report["owner_area_accuracy"] == pytest.approx(2 / 3)
    assert report["retry_precision"] == 0.5
    assert report["unsafe_retry_count"] == 1
    assert report["request_availability"] == 1.0
    assert report["mean_latency_ms"] == 20.0
    assert report["sanitizer_acceptance_rate"] == 1.0
    assert report["confidence_calibration"]


def test_evaluation_detects_missing_and_unexpected_predictions() -> None:
    examples = load_examples(FIXTURES / "evaluation-corpus.jsonl")
    predictions = load_predictions(FIXTURES / "evaluation-predictions.jsonl")
    extra = EvaluationPrediction(
        **{
            **predictions[0].model_dump(),
            "case_id": "unexpected",
            "recommended_action": RecommendedAction.HUMAN_TRIAGE,
        }
    )

    report = evaluate_predictions(
        examples,
        [predictions[0], predictions[1], extra],
        split="holdout",
    )

    assert report["missing_prediction_ids"] == ["holdout-dependency"]
    assert report["unexpected_prediction_ids"] == ["unexpected"]


def test_evaluation_rejects_duplicate_ids() -> None:
    example = EvaluationExample(
        case_id="duplicate",
        split="holdout",
        gold_failure_class="unknown",
        gold_owner_area="general",
        retry_safe=False,
    )

    with pytest.raises(ValueError, match="duplicate case_id in holdout labels"):
        evaluate_predictions([example, example], [], split="holdout")


def test_workflow_keeps_mock_triage_non_blocking_internal_and_secret_free() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = workflow.split("  jev-triage-contract:\n", maxsplit=1)[1].split(
        "\n  docker:\n", maxsplit=1
    )[0]

    assert "continue-on-error: true" in job
    assert "github.event.pull_request.head.repo.full_name == github.repository" in job
    assert "actions: read" in job
    assert "contents: read" in job
    assert "secrets." not in job
    assert "security" not in job
    assert "fake-decision.json" in job
