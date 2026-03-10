#!/usr/bin/env python3
"""Download SBIR award data and run benchmark sensitivity analysis.

Downloads the latest SBIR awards CSV from sbir.gov (or pulls from S3),
then runs the FY 2026 benchmark evaluation and sensitivity analysis.

Usage:
    # Download from sbir.gov and analyze
    python scripts/data/run_benchmark_analysis.py

    # Use existing local file
    python scripts/data/run_benchmark_analysis.py --local data/raw/sbir/award_data.csv

    # Pull from S3 instead of sbir.gov
    python scripts/data/run_benchmark_analysis.py --s3

    # Customize FY and margins
    python scripts/data/run_benchmark_analysis.py --fy 2026 --margin-awards 5 --margin-ratio 0.05

    # Include USAspending transaction data for commercialization benchmark
    python scripts/data/run_benchmark_analysis.py --usaspending data/usaspending/contracts.parquet

    # Fetch USAspending data live from the API (no files needed)
    python scripts/data/run_benchmark_analysis.py --usaspending-api
"""

import argparse
import json
import os
import sys
from datetime import datetime, UTC
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def download_from_sbir_gov(dest: Path) -> Path:
    """Download latest SBIR awards CSV from sbir.gov."""
    import requests

    url = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"
    print(f"Downloading SBIR awards from: {url}")

    response = requests.get(url, stream=True, timeout=300)
    response.raise_for_status()

    size = int(response.headers.get("content-length", 0))
    print(f"Size: {size / 1024 / 1024:.1f} MB")

    dest.parent.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    with open(dest, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)
            downloaded += len(chunk)
            if size:
                print(f"  {downloaded / size * 100:.0f}%", end="\r")

    print(f"\nSaved to {dest}")
    return dest


def download_from_s3(dest: Path, bucket: str = "sbir-etl-production-data") -> Path:
    """Download latest SBIR awards CSV from S3."""
    import boto3

    s3 = boto3.client("s3")
    print(f"Listing award files in s3://{bucket}/raw/awards/...")

    response = s3.list_objects_v2(Bucket=bucket, Prefix="raw/awards/")
    if not response.get("Contents"):
        print("No award files found in S3.", file=sys.stderr)
        sys.exit(1)

    latest = sorted(response["Contents"], key=lambda x: x["LastModified"])[-1]
    s3_key = latest["Key"]
    print(f"Latest: s3://{bucket}/{s3_key} ({latest['Size'] / 1024 / 1024:.1f} MB)")

    dest.parent.mkdir(parents=True, exist_ok=True)
    s3.download_file(bucket, s3_key, str(dest))
    print(f"Downloaded to {dest}")
    return dest


def run_analysis(
    awards_path: Path,
    fy: int,
    margin_awards: int,
    margin_ratio: float,
    usaspending_path: Path | None = None,
    usaspending_api: bool = False,
):
    """Run benchmark evaluation and sensitivity analysis."""
    import pandas as pd

    from src.transition.analysis.benchmark_evaluator import BenchmarkEligibilityEvaluator

    output_dir = Path("data/scripts_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    suffix = awards_path.suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(awards_path)
    else:
        df = pd.read_csv(awards_path)
    print(f"\nLoaded {len(df):,} awards from {awards_path}")

    # Count unique companies
    for col in ["Company", "company", "company_name"]:
        if col in df.columns:
            print(f"Unique companies: {df[col].nunique():,}")
            break

    # Build commercialization data from USAspending if provided
    commercialization_df = None
    if usaspending_api:
        from src.transition.analysis.usaspending_commercialization import (
            fetch_commercialization_from_api,
        )

        cache_file = output_dir / "usaspending_api_cache.json"
        print(f"\nFetching commercialization data from USAspending API...")
        commercialization_df = fetch_commercialization_from_api(
            df, evaluation_fy=fy, cache_path=cache_file,
        )
        print(f"Commercialization records: {len(commercialization_df):,} companies")
        if not commercialization_df.empty:
            total_obligations = commercialization_df["total_sales_and_investment"].sum()
            print(f"Total federal obligations: ${total_obligations:,.0f}")
    elif usaspending_path:
        from src.transition.analysis.usaspending_commercialization import (
            build_commercialization_from_usaspending,
        )

        print(f"\nBuilding commercialization data from USAspending: {usaspending_path}")
        commercialization_df = build_commercialization_from_usaspending(
            usaspending_path, evaluation_fy=fy,
        )
        print(f"Commercialization records: {len(commercialization_df):,} companies")
        total_obligations = commercialization_df["total_sales_and_investment"].sum()
        print(f"Total federal obligations: ${total_obligations:,.0f}")

    # Full evaluation
    print(f"\n{'='*60}")
    print(f"SBIR/STTR Benchmark Evaluation — FY {fy}")
    if commercialization_df is not None:
        print("(with USAspending commercialization data)")
    print(f"{'='*60}")

    evaluator = BenchmarkEligibilityEvaluator(
        evaluation_fy=fy,
        sensitivity_margin_awards=margin_awards,
        sensitivity_margin_ratio=margin_ratio,
    )
    summary = evaluator.evaluate(df, commercialization_df=commercialization_df)

    print(f"Determination date: {summary.determination_date}")
    print(f"Transition window (Phase I): FY {summary.transition_window.start_fy}–{summary.transition_window.end_fy}")
    print(f"Commercialization window: FY {summary.commercialization_window.start_fy}–{summary.commercialization_window.end_fy}")
    print(f"\nCompanies evaluated:                    {summary.total_companies_evaluated:,}")
    print(f"Subject to transition benchmark:        {summary.companies_subject_to_transition:,}")
    print(f"Subject to commercialization benchmark:  {summary.companies_subject_to_commercialization:,}")
    print(f"Failing transition benchmark:           {summary.companies_failing_transition:,}")
    print(f"Failing commercialization benchmark:    {summary.companies_failing_commercialization:,}")

    # Write full evaluation JSON
    eval_path = output_dir / "benchmark_evaluation.json"
    eval_path.write_text(json.dumps(summary.to_dict(), indent=2, default=str))
    print(f"\nFull evaluation: {eval_path}")

    # Write markdown report
    report = evaluator.generate_report(summary)
    report_path = output_dir / f"sensitivity_report_fy{fy}.md"
    report_path.write_text(report)
    print(f"Markdown report: {report_path}")

    # Sensitivity analysis
    print(f"\n{'='*60}")
    print(f"Sensitivity Analysis (margin: {margin_awards} awards, {margin_ratio:.0%} ratio)")
    print(f"{'='*60}")

    at_risk = evaluator.get_companies_at_risk(df, commercialization_df=commercialization_df)
    print(f"Companies at risk: {len(at_risk)}")

    for sr in at_risk:
        name = sr.company_name or sr.company_id
        risks = []
        if sr.at_risk_transition:
            risks.append("Transition")
        if sr.at_risk_commercialization:
            risks.append("Commercialization")
        print(f"\n  {name}")
        print(f"    Phase I: {sr.phase1_count}  |  Phase II (comm): {sr.phase2_count_for_commercialization}")
        if sr.transition_rate_margin is not None:
            print(f"    Transition margin: {sr.transition_rate_margin:+.4f}")
        print(f"    At risk for: {', '.join(risks)}")

    # Write sensitivity JSON
    risk_path = output_dir / "at_risk.json"
    risk_path.write_text(json.dumps([sr.to_dict() for sr in at_risk], indent=2, default=str))
    print(f"\nSensitivity results: {risk_path}")

    print(f"\n{'='*60}")
    print("Done.")


def main():
    parser = argparse.ArgumentParser(
        description="Download SBIR data and run benchmark sensitivity analysis"
    )
    parser.add_argument(
        "--local", type=Path, default=None,
        help="Path to existing local awards CSV/Parquet (skip download)"
    )
    parser.add_argument(
        "--s3", action="store_true",
        help="Pull from S3 instead of sbir.gov"
    )
    parser.add_argument(
        "--s3-bucket", default=os.environ.get("S3_BUCKET", "sbir-etl-production-data"),
        help="S3 bucket name (default: sbir-etl-production-data)"
    )
    parser.add_argument(
        "--fy", type=int, default=2026,
        help="Evaluation fiscal year (default: 2026)"
    )
    parser.add_argument(
        "--margin-awards", type=int, default=5,
        help="Awards margin for sensitivity detection (default: 5)"
    )
    parser.add_argument(
        "--margin-ratio", type=float, default=0.05,
        help="Ratio margin for sensitivity detection (default: 0.05)"
    )
    parser.add_argument(
        "--usaspending", type=Path, default=None,
        help="Path to USAspending transactions Parquet for commercialization benchmark"
    )
    parser.add_argument(
        "--usaspending-api", action="store_true",
        help="Fetch commercialization data live from api.usaspending.gov"
    )
    args = parser.parse_args()

    dest = Path("data/raw/sbir/award_data.csv")

    if args.local:
        if not args.local.exists():
            print(f"File not found: {args.local}", file=sys.stderr)
            sys.exit(1)
        awards_path = args.local
    elif args.s3:
        awards_path = download_from_s3(dest, args.s3_bucket)
    else:
        awards_path = download_from_sbir_gov(dest)

    usaspending_path = None
    if args.usaspending:
        if not args.usaspending.exists():
            print(f"USAspending file not found: {args.usaspending}", file=sys.stderr)
            sys.exit(1)
        usaspending_path = args.usaspending

    run_analysis(
        awards_path, args.fy, args.margin_awards, args.margin_ratio,
        usaspending_path, args.usaspending_api,
    )


if __name__ == "__main__":
    main()
