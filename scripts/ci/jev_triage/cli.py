"""CLI for no-key Jev CI triage dry runs and offline evaluation."""

import argparse
import hashlib
import json
from pathlib import Path

from .classify import classify_failure
from .client import FakeJevTriageClient
from .evaluate import evaluate_predictions, load_examples, load_predictions, write_evaluation_report
from .models import CommandFamily, JevTriageDecision
from .render import render_triage_summary
from .sanitize import failure_envelope_from_junit


EPISTEMIC_TIER = "exploratory"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes(), usedforsecurity=False).hexdigest()


def _write_jsonl(records: list[str], output: Path) -> None:
    output.write_text("".join(f"{record}\n" for record in records), encoding="utf-8")


def run_dry_run(args: argparse.Namespace) -> int:
    """Classify failed JUnit cases with a fixed fake decision."""

    input_dir = Path(args.junit_dir)
    output_dir = Path(args.output_dir)
    decision = JevTriageDecision.model_validate_json(
        Path(args.fake_decision).read_text(encoding="utf-8")
    )
    reports = sorted(input_dir.rglob("*.xml"))
    if not reports:
        raise ValueError(f"no JUnit XML files found under {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    envelopes: list[str] = []
    results: list[str] = []
    summaries: list[str] = []
    inputs: list[dict[str, object]] = []

    for report in reports:
        envelope = failure_envelope_from_junit(
            report.read_text(encoding="utf-8"),
            check_name=f"{args.check_name}: {report.stem}",
            command_family=CommandFamily(args.command_family),
            exit_code=args.exit_code,
            changed_path_groups=args.changed_path_group,
            runner_os=args.runner_os,
            attempt_number=args.attempt_number,
        )
        inputs.append({"path": report.name, "sha256": _sha256(report)})
        if not envelope.failed_test_ids:
            continue
        client = FakeJevTriageClient(decision)
        result = classify_failure(envelope, client=client)
        envelopes.append(envelope.model_dump_json())
        results.append(result.model_dump_json())
        summaries.append(render_triage_summary(result))

    _write_jsonl(envelopes, output_dir / "failure_envelopes.jsonl")
    _write_jsonl(results, output_dir / "triage_results.jsonl")
    summary = (
        "\n".join(summaries)
        if summaries
        else "## Experimental CI failure triage\n\nNo failed JUnit cases were found.\n"
    )
    (output_dir / "summary.md").write_text(summary, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "epistemic_tier": "exploratory",
        "citable": False,
        "mode": "fake",
        "input_reports": inputs,
        "reports_seen": len(reports),
        "failures_classified": len(results),
        "network_calls": 0,
    }
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


def run_evaluate(args: argparse.Namespace) -> int:
    """Evaluate saved predictions against strict labels."""

    examples = load_examples(Path(args.corpus))
    predictions = load_predictions(Path(args.predictions))
    report = evaluate_predictions(
        examples,
        predictions,
        split=args.split,
        synthetic_fixture=args.synthetic_fixture,
    )
    write_evaluation_report(report, Path(args.output))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the two no-key CLI commands."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    dry_run = subparsers.add_parser("dry-run", help="Run the fake transport over JUnit XML")
    dry_run.add_argument("--junit-dir", type=Path, required=True)
    dry_run.add_argument("--fake-decision", type=Path, required=True)
    dry_run.add_argument("--output-dir", type=Path, required=True)
    dry_run.add_argument("--check-name", default="Fast Tests")
    dry_run.add_argument(
        "--command-family",
        choices=[family.value for family in CommandFamily],
        default=CommandFamily.PYTEST.value,
    )
    dry_run.add_argument("--exit-code", type=int, default=1)
    dry_run.add_argument("--runner-os", default="ubuntu-latest")
    dry_run.add_argument("--attempt-number", type=int, default=1)
    dry_run.add_argument("--changed-path-group", action="append", default=[])
    dry_run.set_defaults(handler=run_dry_run)

    evaluate = subparsers.add_parser("evaluate", help="Score saved predictions")
    evaluate.add_argument("--corpus", type=Path, required=True)
    evaluate.add_argument("--predictions", type=Path, required=True)
    evaluate.add_argument("--output", type=Path, required=True)
    evaluate.add_argument("--split", choices=("development", "holdout"), default="holdout")
    evaluate.add_argument("--synthetic-fixture", action="store_true")
    evaluate.set_defaults(handler=run_evaluate)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
