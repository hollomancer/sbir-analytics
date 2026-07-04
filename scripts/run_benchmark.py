#!/usr/bin/env python3
"""Evaluate benchmark eligibility for SBIR companies.

Usage:
    python scripts/run_benchmark.py evaluate awards.parquet --fy 2025
    python scripts/run_benchmark.py evaluate awards.csv --fy 2023 --output results.json
    python scripts/run_benchmark.py sensitivity awards.parquet --fy 2025 --margin-ratio 0.05
    python scripts/run_benchmark.py company awards.parquet --fy 2025 --id "COMPANY_UEI"
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd


def _filter_to_subject_only(summary):
    """Return a new summary containing only subject rows, with counters recomputed.

    Applied before generating either JSON or the markdown report so ``--subject-only``
    behaves consistently across output modes and no counter drifts out of sync with the
    row list it summarizes.
    """
    from sbir_etl.models.benchmark_models import BenchmarkStatus, BenchmarkTier

    def _is_subject(r) -> bool:
        return r.tier != BenchmarkTier.NOT_SUBJECT

    transition = [r for r in summary.transition_results if _is_subject(r)]
    commercialization = [r for r in summary.commercialization_results if _is_subject(r)]
    subject_ids = {r.company_id for r in transition} | {r.company_id for r in commercialization}

    return replace(
        summary,
        total_companies_evaluated=len(subject_ids),
        companies_subject_to_transition=len(transition),
        companies_subject_to_commercialization=len(commercialization),
        companies_failing_transition=sum(1 for r in transition if r.status == BenchmarkStatus.FAIL),
        companies_failing_commercialization=sum(
            1 for r in commercialization if r.status == BenchmarkStatus.FAIL
        ),
        transition_results=transition,
        commercialization_results=commercialization,
    )


def load_awards(path: str) -> pd.DataFrame:
    """Load awards from CSV or Parquet."""
    p = Path(path)
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    elif p.suffix == ".csv":
        return pd.read_csv(p, low_memory=False)
    else:
        print(f"Unsupported file format: {p.suffix}", file=sys.stderr)
        sys.exit(1)


# Column aliases the evaluator resolves; without both, it silently evaluates 0 companies.
_PHASE_COLUMNS = ("Phase", "phase")
_FY_COLUMNS = ("fiscal_year", "award_year", "Award Year")


def check_award_columns(df: pd.DataFrame, path: str) -> None:
    """Exit with a clear error if the awards file lacks columns the evaluator requires."""
    missing = []
    if not any(c in df.columns for c in _PHASE_COLUMNS):
        missing.append(f"phase (one of: {', '.join(_PHASE_COLUMNS)})")
    if not any(c in df.columns for c in _FY_COLUMNS):
        missing.append(f"fiscal year (one of: {', '.join(_FY_COLUMNS)})")
    if missing:
        print(
            f"Error: {path} is missing required columns: {'; '.join(missing)}.\n"
            f"Found columns: {', '.join(df.columns)}",
            file=sys.stderr,
        )
        sys.exit(1)


def cmd_evaluate(args) -> None:
    from sbir_ml.transition.analysis.benchmark_evaluator import BenchmarkEligibilityEvaluator

    awards = load_awards(args.awards)
    check_award_columns(awards, args.awards)
    commercialization = load_awards(args.commercialization) if args.commercialization else None

    evaluator = BenchmarkEligibilityEvaluator(
        evaluation_fy=args.fy,
    )
    summary = evaluator.evaluate(awards, commercialization)
    if args.subject_only:
        summary = _filter_to_subject_only(summary)
    results = summary.to_dict()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Wrote benchmark evaluation to {args.output}")
    elif args.report:
        print(evaluator.generate_report(summary))
    else:
        print(json.dumps(results, indent=2, default=str))


def cmd_sensitivity(args) -> None:
    from sbir_ml.transition.analysis.benchmark_evaluator import BenchmarkEligibilityEvaluator

    awards = load_awards(args.awards)
    check_award_columns(awards, args.awards)
    commercialization = load_awards(args.commercialization) if args.commercialization else None
    evaluator = BenchmarkEligibilityEvaluator(
        evaluation_fy=args.fy,
        sensitivity_margin_awards=args.margin_awards,
        sensitivity_margin_ratio=args.margin_ratio,
    )
    at_risk = evaluator.get_companies_at_risk(awards, commercialization)
    at_risk_results = [r.to_dict() for r in at_risk]

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(at_risk_results, f, indent=2, default=str)
        print(f"Wrote {len(at_risk_results)} at-risk companies to {args.output}")
    else:
        print(json.dumps(at_risk_results, indent=2, default=str))


def cmd_company(args) -> None:
    from sbir_ml.transition.analysis.benchmark_evaluator import BenchmarkEligibilityEvaluator

    awards = load_awards(args.awards)
    check_award_columns(awards, args.awards)
    commercialization = load_awards(args.commercialization) if args.commercialization else None
    evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=args.fy)
    result = evaluator.evaluate_single_company(awards, args.id, commercialization)
    print(json.dumps(result, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark eligibility evaluation")
    sub = parser.add_subparsers(dest="command", required=True)

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Full benchmark evaluation")
    p_eval.add_argument("awards", help="Path to awards file (CSV or Parquet)")
    p_eval.add_argument("--fy", type=int, required=True, help="Evaluation fiscal year")
    p_eval.add_argument("--commercialization", help="Path to commercialization data file")
    p_eval.add_argument("--output", help="Output JSON file path")
    p_eval.add_argument("--report", action="store_true", help="Print markdown summary")
    p_eval.add_argument("--subject-only", action="store_true", help="Only show subject companies")

    # sensitivity
    p_sens = sub.add_parser("sensitivity", help="Find companies near threshold boundaries")
    p_sens.add_argument("awards", help="Path to awards file (CSV or Parquet)")
    p_sens.add_argument("--fy", type=int, required=True, help="Evaluation fiscal year")
    p_sens.add_argument("--commercialization", help="Path to commercialization data file")
    p_sens.add_argument("--margin-awards", type=int, default=5, help="Award count margin")
    p_sens.add_argument("--margin-ratio", type=float, default=0.05, help="Ratio margin")
    p_sens.add_argument("--output", help="Output JSON file path")

    # company
    p_comp = sub.add_parser("company", help="Evaluate a single company")
    p_comp.add_argument("awards", help="Path to awards file (CSV or Parquet)")
    p_comp.add_argument("--id", required=True, help="Company identifier (UEI, DUNS, or name)")
    p_comp.add_argument("--fy", type=int, required=True, help="Evaluation fiscal year")
    p_comp.add_argument("--commercialization", help="Path to commercialization data file")

    args = parser.parse_args()

    if args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "sensitivity":
        cmd_sensitivity(args)
    elif args.command == "company":
        cmd_company(args)


if __name__ == "__main__":
    main()
