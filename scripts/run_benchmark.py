#!/usr/bin/env python3
"""Evaluate benchmark eligibility for SBIR companies.

Usage:
    python scripts/run_benchmark.py evaluate awards.parquet
    python scripts/run_benchmark.py evaluate awards.csv --fy 2023 --output results.json
    python scripts/run_benchmark.py sensitivity awards.parquet --margin-ratio 0.05
    python scripts/run_benchmark.py company awards.parquet --id "COMPANY_UEI"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


def load_awards(path: str) -> pd.DataFrame:
    """Load awards from CSV or Parquet."""
    p = Path(path)
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    elif p.suffix == ".csv":
        return pd.read_csv(p)
    else:
        print(f"Unsupported file format: {p.suffix}", file=sys.stderr)
        sys.exit(1)


def cmd_evaluate(args) -> None:
    from sbir_ml.transition.analysis.benchmark_evaluator import BenchmarkEligibilityEvaluator

    awards = load_awards(args.awards)
    commercialization = load_awards(args.commercialization) if args.commercialization else None

    evaluator = BenchmarkEligibilityEvaluator(
        awards_df=awards,
        commercialization_df=commercialization,
        fiscal_year=args.fy,
    )
    results = evaluator.evaluate()

    if args.subject_only:
        results = [r for r in results if r.get("status") != "NOT_SUBJECT"]

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, default=str)
        print(f"Wrote {len(results)} results to {args.output}")
    elif args.report:
        # Print markdown summary
        subject = [r for r in results if r.get("status") != "NOT_SUBJECT"]
        failing = [r for r in results if r.get("status") == "FAILING"]
        print(f"# Benchmark Evaluation (FY {args.fy or 'latest'})")
        print(f"\n- **Total companies:** {len(results)}")
        print(f"- **Subject to benchmark:** {len(subject)}")
        print(f"- **Failing:** {len(failing)}")
    else:
        print(json.dumps(results, indent=2, default=str))


def cmd_sensitivity(args) -> None:
    from sbir_ml.transition.analysis.benchmark_evaluator import BenchmarkEligibilityEvaluator

    awards = load_awards(args.awards)
    evaluator = BenchmarkEligibilityEvaluator(awards_df=awards, fiscal_year=args.fy)
    at_risk = evaluator.get_companies_at_risk(
        margin_awards=args.margin_awards,
        margin_ratio=args.margin_ratio,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(at_risk, f, indent=2, default=str)
        print(f"Wrote {len(at_risk)} at-risk companies to {args.output}")
    else:
        print(json.dumps(at_risk, indent=2, default=str))


def cmd_company(args) -> None:
    from sbir_ml.transition.analysis.benchmark_evaluator import BenchmarkEligibilityEvaluator

    awards = load_awards(args.awards)
    evaluator = BenchmarkEligibilityEvaluator(awards_df=awards, fiscal_year=args.fy)
    result = evaluator.evaluate_single_company(args.id)
    print(json.dumps(result, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark eligibility evaluation")
    sub = parser.add_subparsers(dest="command", required=True)

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Full benchmark evaluation")
    p_eval.add_argument("awards", help="Path to awards file (CSV or Parquet)")
    p_eval.add_argument("--fy", type=int, help="Fiscal year")
    p_eval.add_argument("--commercialization", help="Path to commercialization data file")
    p_eval.add_argument("--output", help="Output JSON file path")
    p_eval.add_argument("--report", action="store_true", help="Print markdown summary")
    p_eval.add_argument("--subject-only", action="store_true", help="Only show subject companies")

    # sensitivity
    p_sens = sub.add_parser("sensitivity", help="Find companies near threshold boundaries")
    p_sens.add_argument("awards", help="Path to awards file (CSV or Parquet)")
    p_sens.add_argument("--fy", type=int, help="Fiscal year")
    p_sens.add_argument("--margin-awards", type=int, default=5, help="Award count margin")
    p_sens.add_argument("--margin-ratio", type=float, default=0.05, help="Ratio margin")
    p_sens.add_argument("--output", help="Output JSON file path")

    # company
    p_comp = sub.add_parser("company", help="Evaluate a single company")
    p_comp.add_argument("awards", help="Path to awards file (CSV or Parquet)")
    p_comp.add_argument("--id", required=True, help="Company identifier (UEI, DUNS, or name)")
    p_comp.add_argument("--fy", type=int, help="Fiscal year")

    args = parser.parse_args()

    if args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "sensitivity":
        cmd_sensitivity(args)
    elif args.command == "company":
        cmd_company(args)


if __name__ == "__main__":
    main()
