"""Command line interface for deterministic and shadow study preflight."""

import argparse
from pathlib import Path

from .annual_report import build_annual_report_preflight, load_annual_report_claims
from .engine import assess_readiness
from .evaluate import (
    evaluate_matrix,
    evaluate_shadow_matrix,
    load_matrix,
    load_shadow_bundle,
    write_matrix_report,
    write_shadow_evaluation,
)
from .jev import PrivateShadowBundle, TypeSafeJevClient, run_shadow
from .render import render_result


EPISTEMIC_TIER = "exploratory"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MATRIX = REPOSITORY_ROOT / "tests" / "fixtures" / "jev_preflight" / "readiness-matrix.jsonl"


def _write_result(output: Path, content: str) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")


def run_annual_report(args: argparse.Namespace) -> int:
    """Run deterministic preflight for one annual-report claim."""

    preflight = build_annual_report_preflight(args.repository_root, args.case_id)
    result = assess_readiness(preflight)
    _write_result(args.output_json, result.model_dump_json(indent=2) + "\n")
    if args.output_markdown:
        _write_result(args.output_markdown, render_result(result))
    return 0


def run_matrix(args: argparse.Namespace) -> int:
    """Evaluate the frozen deterministic matrix."""

    report = evaluate_matrix(load_matrix(args.matrix))
    write_matrix_report(report, args.output)
    return 0 if not report.incorrect_case_ids else 1


def run_shadow_matrix(args: argparse.Namespace) -> int:
    """Run a private live Jev shadow over every synthetic case."""

    client = TypeSafeJevClient(timeout_seconds=args.timeout_seconds)
    results = [run_shadow(case.input, client=client) for case in load_matrix(args.matrix)]
    bundle = PrivateShadowBundle(results=results)
    _write_result(args.output, bundle.model_dump_json(indent=2) + "\n")
    return 0


def run_shadow_annual_report(args: argparse.Namespace) -> int:
    """Run a private live Jev shadow over both annual-report claims."""

    client = TypeSafeJevClient(timeout_seconds=args.timeout_seconds)
    case_ids = sorted(load_annual_report_claims(args.repository_root))
    results = [
        run_shadow(
            build_annual_report_preflight(args.repository_root, case_id),
            client=client,
        )
        for case_id in case_ids
    ]
    bundle = PrivateShadowBundle(results=results)
    _write_result(args.output, bundle.model_dump_json(indent=2) + "\n")
    return 0


def run_evaluate_shadow(args: argparse.Namespace) -> int:
    """Compare saved private predictions with the frozen matrix by case ID."""

    report = evaluate_shadow_matrix(load_matrix(args.matrix), load_shadow_bundle(args.predictions))
    write_shadow_evaluation(report, args.output)
    return 0 if not (
        report.missing_case_ids
        or report.unexpected_case_ids
        or report.status_disagreement_case_ids
        or report.first_blocker_disagreement_case_ids
    ) else 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the preflight CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    annual = subparsers.add_parser("annual-report", help="Run deterministic annual-report preflight")
    annual.add_argument("--case-id", required=True)
    annual.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    annual.add_argument("--output-json", type=Path, required=True)
    annual.add_argument("--output-markdown", type=Path)
    annual.set_defaults(handler=run_annual_report)

    matrix = subparsers.add_parser("matrix", help="Evaluate the frozen synthetic matrix")
    matrix.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    matrix.add_argument("--output", type=Path, required=True)
    matrix.set_defaults(handler=run_matrix)

    shadow_matrix = subparsers.add_parser("shadow-matrix", help="Run private live Jev matrix shadow")
    shadow_matrix.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    shadow_matrix.add_argument("--output", type=Path, required=True)
    shadow_matrix.add_argument("--timeout-seconds", type=float, default=10.0)
    shadow_matrix.set_defaults(handler=run_shadow_matrix)

    shadow_annual = subparsers.add_parser(
        "shadow-annual-report", help="Run private live Jev annual-report shadow"
    )
    shadow_annual.add_argument("--repository-root", type=Path, default=REPOSITORY_ROOT)
    shadow_annual.add_argument("--output", type=Path, required=True)
    shadow_annual.add_argument("--timeout-seconds", type=float, default=10.0)
    shadow_annual.set_defaults(handler=run_shadow_annual_report)

    evaluate_shadow = subparsers.add_parser(
        "evaluate-shadow", help="Compare saved private Jev results with the frozen matrix"
    )
    evaluate_shadow.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    evaluate_shadow.add_argument("--predictions", type=Path, required=True)
    evaluate_shadow.add_argument("--output", type=Path, required=True)
    evaluate_shadow.set_defaults(handler=run_evaluate_shadow)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
