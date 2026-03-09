"""Benchmark eligibility CLI commands.

Provides commands to evaluate which companies are subject to SBIR/STTR
performance benchmarks (transition rate and commercialization rate) for a
given fiscal year, and to run sensitivity analysis for companies near
threshold margins.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import typer

app = typer.Typer(name="benchmark", help="SBIR/STTR benchmark eligibility evaluation")


def _load_awards(path: Path) -> pd.DataFrame:
    """Load awards from CSV or Parquet."""
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    elif suffix == ".csv":
        return pd.read_csv(path)
    else:
        typer.echo(f"Unsupported file format: {suffix}", err=True)
        raise typer.Exit(code=1)


@app.command("evaluate")
def evaluate_benchmarks(
    awards_path: Path = typer.Argument(
        ..., help="Path to awards CSV or Parquet file"
    ),
    evaluation_fy: int = typer.Option(
        2025, "--fy", help="Evaluation fiscal year (determination date = June 1 of this year)"
    ),
    commercialization_path: Path | None = typer.Option(
        None, "--commercialization", help="Path to commercialization data CSV/Parquet"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output path for JSON results"
    ),
    report: bool = typer.Option(
        False, "--report", "-r", help="Generate a markdown report to stdout"
    ),
    subject_only: bool = typer.Option(
        False, "--subject-only", help="Only show companies subject to benchmarks"
    ),
) -> None:
    """Evaluate benchmark eligibility for all companies in the awards dataset.

    Identifies companies subject to the Phase I→II transition rate benchmark
    and the commercialization rate benchmark, determines pass/fail status,
    and computes sensitivity analysis for companies near thresholds.
    """
    from src.transition.analysis.benchmark_evaluator import BenchmarkEligibilityEvaluator

    awards_df = _load_awards(awards_path)
    typer.echo(f"Loaded {len(awards_df)} awards from {awards_path}")

    commercialization_df = None
    if commercialization_path:
        commercialization_df = _load_awards(commercialization_path)
        typer.echo(f"Loaded {len(commercialization_df)} commercialization records")

    evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=evaluation_fy)
    summary = evaluator.evaluate(awards_df, commercialization_df)

    typer.echo(f"\n--- Benchmark Evaluation for FY {evaluation_fy} ---")
    typer.echo(f"Determination date: {summary.determination_date}")
    typer.echo(
        f"Transition window (Phase I): FY {summary.transition_window.start_fy}"
        f"–{summary.transition_window.end_fy}"
    )
    typer.echo(
        f"Commercialization window: FY {summary.commercialization_window.start_fy}"
        f"–{summary.commercialization_window.end_fy}"
    )
    typer.echo(f"\nCompanies evaluated: {summary.total_companies_evaluated}")
    typer.echo(f"Subject to transition benchmark: {summary.companies_subject_to_transition}")
    typer.echo(
        f"Subject to commercialization benchmark: {summary.companies_subject_to_commercialization}"
    )
    typer.echo(f"Failing transition benchmark: {summary.companies_failing_transition}")
    typer.echo(f"Failing commercialization benchmark: {summary.companies_failing_commercialization}")

    if subject_only:
        from src.models.benchmark_models import BenchmarkTier

        summary.transition_results = [
            r for r in summary.transition_results
            if r.tier != BenchmarkTier.NOT_SUBJECT
        ]
        summary.commercialization_results = [
            r for r in summary.commercialization_results
            if r.tier != BenchmarkTier.NOT_SUBJECT
        ]

    if report:
        typer.echo("\n" + evaluator.generate_report(summary))

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(summary.to_dict(), indent=2, default=str))
        typer.echo(f"\nResults written to {output}")


@app.command("sensitivity")
def sensitivity_analysis(
    awards_path: Path = typer.Argument(
        ..., help="Path to awards CSV or Parquet file"
    ),
    evaluation_fy: int = typer.Option(
        2025, "--fy", help="Evaluation fiscal year"
    ),
    margin_awards: int = typer.Option(
        5, "--margin-awards", help="Awards margin for 'approaching threshold' detection"
    ),
    margin_ratio: float = typer.Option(
        0.05, "--margin-ratio", help="Ratio margin for 'at risk of failing' detection"
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Output path for JSON results"
    ),
) -> None:
    """Run sensitivity analysis to find companies near benchmark thresholds.

    Identifies companies that are:
    - Approaching the award count thresholds that trigger benchmark applicability
    - Already subject to benchmarks but close to the pass/fail boundary
    """
    from src.transition.analysis.benchmark_evaluator import BenchmarkEligibilityEvaluator

    awards_df = _load_awards(awards_path)
    typer.echo(f"Loaded {len(awards_df)} awards from {awards_path}")

    evaluator = BenchmarkEligibilityEvaluator(
        evaluation_fy=evaluation_fy,
        sensitivity_margin_awards=margin_awards,
        sensitivity_margin_ratio=margin_ratio,
    )

    at_risk = evaluator.get_companies_at_risk(awards_df)

    typer.echo(f"\n--- Sensitivity Analysis for FY {evaluation_fy} ---")
    typer.echo(f"Margin settings: {margin_awards} awards, {margin_ratio:.0%} ratio")
    typer.echo(f"Companies at risk: {len(at_risk)}")

    for sr in at_risk:
        name = sr.company_name or sr.company_id
        risks = []
        if sr.at_risk_transition:
            risks.append("Transition")
        if sr.at_risk_commercialization:
            risks.append("Commercialization")
        typer.echo(
            f"\n  {name}"
            f"\n    Phase I awards: {sr.phase1_count}"
            f"  (need {sr.phase1_to_standard_transition} more for standard threshold)"
            f"\n    At risk for: {', '.join(risks)}"
        )
        if sr.transition_rate_margin is not None:
            typer.echo(f"    Transition rate margin: {sr.transition_rate_margin:+.4f}")

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        results = [sr.to_dict() for sr in at_risk]
        output.write_text(json.dumps(results, indent=2, default=str))
        typer.echo(f"\nResults written to {output}")


@app.command("company")
def evaluate_company(
    awards_path: Path = typer.Argument(
        ..., help="Path to awards CSV or Parquet file"
    ),
    company: str = typer.Argument(
        ..., help="Company ID (UEI, DUNS, or name) to evaluate"
    ),
    evaluation_fy: int = typer.Option(
        2025, "--fy", help="Evaluation fiscal year"
    ),
) -> None:
    """Evaluate benchmark eligibility for a single company."""
    from src.transition.analysis.benchmark_evaluator import BenchmarkEligibilityEvaluator

    awards_df = _load_awards(awards_path)
    evaluator = BenchmarkEligibilityEvaluator(evaluation_fy=evaluation_fy)
    result = evaluator.evaluate_single_company(awards_df, company)

    if "error" in result:
        typer.echo(f"Error: {result['error']}", err=True)
        raise typer.Exit(code=1)

    typer.echo(json.dumps(result, indent=2, default=str))


def register_command(main_app: typer.Typer) -> None:
    main_app.add_typer(app, name="benchmark")
