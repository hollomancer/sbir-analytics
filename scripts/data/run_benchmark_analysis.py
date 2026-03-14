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

    # Pull USAspending recipient_lookup Parquet from S3 (fastest option)
    python scripts/data/run_benchmark_analysis.py --usaspending-s3
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


def download_usaspending_from_s3(
    dest: Path,
    bucket: str = "sbir-etl-production-data",
    prefix: str = "raw/usaspending/recipient_lookup/",
) -> Path:
    """Download latest USAspending recipient_lookup Parquet from S3."""
    import boto3

    s3 = boto3.client("s3")
    print(f"Listing USAspending files in s3://{bucket}/{prefix}...")

    response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    if not response.get("Contents"):
        print(f"No USAspending files found at s3://{bucket}/{prefix}", file=sys.stderr)
        sys.exit(1)

    # Find the latest Parquet file
    parquet_files = [
        obj for obj in response["Contents"]
        if obj["Key"].endswith(".parquet")
    ]
    if not parquet_files:
        # Fall back to any file
        parquet_files = response["Contents"]

    latest = sorted(parquet_files, key=lambda x: x["LastModified"])[-1]
    s3_key = latest["Key"]
    size_mb = latest["Size"] / 1024 / 1024
    print(f"Latest: s3://{bucket}/{s3_key} ({size_mb:.1f} MB)")

    dest.parent.mkdir(parents=True, exist_ok=True)
    s3.download_file(bucket, s3_key, str(dest))
    print(f"Downloaded to {dest}")
    return dest


def _write_run_manifest(
    output_dir: Path,
    awards_path: Path,
    awards_row_count: int,
    fy: int,
    margin_awards: int,
    margin_ratio: float,
    sbir_source: str,
    usaspending_source: str,
    usaspending_company_count: int,
) -> Path:
    """Write a run manifest capturing all parameters and data provenance."""
    import hashlib

    manifest = {
        "run_timestamp": datetime.now(UTC).isoformat(),
        "parameters": {
            "evaluation_fy": fy,
            "sensitivity_margin_awards": margin_awards,
            "sensitivity_margin_ratio": margin_ratio,
        },
        "data_sources": {
            "sbir_awards": {
                "source": sbir_source,
                "path": str(awards_path),
                "row_count": awards_row_count,
                "sha256": hashlib.sha256(awards_path.read_bytes()).hexdigest(),
            },
            "usaspending": {
                "source": usaspending_source,
                "companies_queried": usaspending_company_count,
            },
        },
    }
    path = output_dir / "run_manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    print(f"Run manifest: {path}")
    return path


def run_analysis(
    awards_path: Path,
    fy: int,
    margin_awards: int,
    margin_ratio: float,
    usaspending_path: Path | None = None,
    usaspending_api: bool = False,
    sbir_source: str = "sbir-gov",
):
    """Run benchmark evaluation and sensitivity analysis."""
    import pandas as pd

    from src.transition.analysis.benchmark_evaluator import BenchmarkEligibilityEvaluator

    output_dir = Path("data/scripts_output")
    output_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Load SBIR awards ──────────────────────────────────────
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

    # Create evaluator early so we can use it for candidate identification
    evaluator = BenchmarkEligibilityEvaluator(
        evaluation_fy=fy,
        sensitivity_margin_awards=margin_awards,
        sensitivity_margin_ratio=margin_ratio,
    )

    # ── Step 2: Identify commercialization candidates, then fetch ─────
    # Run a lightweight pass to find companies with enough Phase II awards
    # to be subject to the commercialization benchmark.  This lets us query
    # USAspending only for ~50-100 companies instead of all ~17K UEIs.
    commercialization_df = None
    usaspending_source = "none"
    usaspending_company_count = 0

    if usaspending_api or usaspending_path:
        candidates = evaluator.get_commercialization_candidates(df)
        print(f"\nCommercialization benchmark candidates: {len(candidates)} companies")
        for c in candidates[:10]:
            print(f"  {c.company_name or c.company_id}: {c.phase2_count_commercialization} Phase II awards")
        if len(candidates) > 10:
            print(f"  ... and {len(candidates) - 10} more")

        # Extract UEIs from candidates for targeted querying
        candidate_ueis: set[str] = set()
        for c in candidates:
            cid = c.company_id
            if cid.startswith("uei:"):
                candidate_ueis.add(cid[4:])

        if not candidates:
            print("No companies subject to commercialization benchmark; skipping USAspending fetch.")
        elif usaspending_api:
            from src.transition.analysis.usaspending_commercialization import (
                fetch_commercialization_from_api,
            )

            cache_file = output_dir / "usaspending_api_cache.json"
            print(f"\nFetching commercialization data from USAspending API...")
            uei_col = next((c for c in df.columns if c.upper() == "UEI"), None)
            if uei_col:
                print(f"  Querying {len(candidate_ueis)} candidate UEIs (not all {df[uei_col].nunique():,})")
            commercialization_df = fetch_commercialization_from_api(
                df, evaluation_fy=fy, cache_path=cache_file,
                uei_filter=candidate_ueis if candidate_ueis else None,
            )
            usaspending_source = "api.usaspending.gov"
            usaspending_company_count = len(commercialization_df)
            print(f"Commercialization records: {usaspending_company_count:,} companies")
            if not commercialization_df.empty:
                total_obligations = commercialization_df["total_sales_and_investment"].sum()
                print(f"Total federal obligations: ${total_obligations:,.0f}")
        else:
            from src.transition.analysis.usaspending_commercialization import (
                build_commercialization_from_usaspending,
            )

            print(f"\nBuilding commercialization data from USAspending: {usaspending_path}")
            commercialization_df = build_commercialization_from_usaspending(
                usaspending_path, evaluation_fy=fy,
                uei_filter=candidate_ueis if candidate_ueis else None,
            )
            usaspending_source = f"parquet:{usaspending_path}"
            usaspending_company_count = len(commercialization_df)
            print(f"Commercialization records: {usaspending_company_count:,} companies")
            total_obligations = commercialization_df["total_sales_and_investment"].sum()
            print(f"Total federal obligations: ${total_obligations:,.0f}")

    # Save commercialization detail artifact
    if commercialization_df is not None and not commercialization_df.empty:
        comm_path = output_dir / "commercialization_obligations.csv"
        commercialization_df.to_csv(comm_path, index=False)
        print(f"Commercialization detail: {comm_path}")

    # ── Step 3: Run manifest ──────────────────────────────────────────
    _write_run_manifest(
        output_dir, awards_path, len(df), fy, margin_awards, margin_ratio,
        sbir_source, usaspending_source, usaspending_company_count,
    )

    # ── Step 4: Full evaluation ───────────────────────────────────────
    divider = "=" * 60
    print(f"\n{divider}")
    print(f"SBIR/STTR Benchmark Evaluation — FY {fy}")
    if commercialization_df is not None:
        print("(with USAspending commercialization data)")
    print(divider)

    summary = evaluator.evaluate(df, commercialization_df=commercialization_df)

    print(f"Determination date: {summary.determination_date}")
    print(f"Transition window (Phase I): FY {summary.transition_window.start_fy}–{summary.transition_window.end_fy}")
    print(f"Commercialization window: FY {summary.commercialization_window.start_fy}–{summary.commercialization_window.end_fy}")
    print("\nBenchmark results (failures listed first):")
    print(f"  Failing transition benchmark:           {summary.companies_failing_transition:,}")
    print(f"  Failing commercialization benchmark:    {summary.companies_failing_commercialization:,}")
    print(f"  Subject to transition benchmark:        {summary.companies_subject_to_transition:,}")
    print(f"  Subject to commercialization benchmark: {summary.companies_subject_to_commercialization:,}")
    print(f"  Companies evaluated:                    {summary.total_companies_evaluated:,}")

    # ── Step 5: Write per-company transition rate detail ──────────────
    transition_rows = [r.to_dict() for r in summary.transition_results]
    transition_csv = output_dir / "transition_rate_detail.csv"
    pd.DataFrame(transition_rows).to_csv(transition_csv, index=False)
    print(f"Transition rate detail: {transition_csv}")

    # ── Step 6: Write per-company commercialization rate detail ───────
    commercialization_rows = [r.to_dict() for r in summary.commercialization_results]
    commercialization_csv = output_dir / "commercialization_rate_detail.csv"
    pd.DataFrame(commercialization_rows).to_csv(commercialization_csv, index=False)
    print(f"Commercialization rate detail: {commercialization_csv}")

    # ── Step 7: Write full evaluation JSON ────────────────────────────
    eval_path = output_dir / "benchmark_evaluation.json"
    eval_path.write_text(json.dumps(summary.to_dict(), indent=2, default=str))
    print(f"Full evaluation: {eval_path}")

    # ── Step 8: Write markdown report ─────────────────────────────────
    report = evaluator.generate_report(summary)
    report_path = output_dir / f"sensitivity_report_fy{fy}.md"
    report_path.write_text(report)
    print(f"Markdown report: {report_path}")

    # ── Step 9: Sensitivity analysis ──────────────────────────────────
    print(f"\n{divider}")
    print("Sensitivity Analysis")
    print(divider)
    print("Parameters:")
    print(f"  Awards margin: {margin_awards} awards")
    print(f"  Ratio margin:  {margin_ratio:.2%}")

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

    # ── Step 10: Write artifact manifest ──────────────────────────────
    artifacts = {
        "run_manifest": "run_manifest.json",
        "sbir_awards_input": str(awards_path),
        "commercialization_obligations": "commercialization_obligations.csv"
        if (commercialization_df is not None and not commercialization_df.empty) else None,
        "usaspending_api_cache": "usaspending_api_cache.json"
        if usaspending_api else None,
        "transition_rate_detail": "transition_rate_detail.csv",
        "commercialization_rate_detail": "commercialization_rate_detail.csv",
        "benchmark_evaluation": "benchmark_evaluation.json",
        "sensitivity_report": f"sensitivity_report_fy{fy}.md",
        "at_risk": "at_risk.json",
    }
    # Remove None entries
    artifacts = {k: v for k, v in artifacts.items() if v is not None}
    artifact_manifest_path = output_dir / "artifact_manifest.json"
    artifact_manifest_path.write_text(json.dumps(artifacts, indent=2))
    print(f"\nArtifact manifest: {artifact_manifest_path}")

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
    parser.add_argument(
        "--usaspending-s3", action="store_true",
        help="Pull USAspending recipient_lookup Parquet from S3"
    )
    parser.add_argument(
        "--usaspending-s3-prefix",
        default="raw/usaspending/recipient_lookup/",
        help="S3 prefix for USAspending data (default: raw/usaspending/recipient_lookup/)"
    )
    args = parser.parse_args()

    dest = Path("data/raw/sbir/award_data.csv")

    if args.local:
        if not args.local.exists():
            print(f"File not found: {args.local}", file=sys.stderr)
            sys.exit(1)
        awards_path = args.local
        sbir_source = f"local:{args.local}"
    elif args.s3:
        awards_path = download_from_s3(dest, args.s3_bucket)
        sbir_source = f"s3://{args.s3_bucket}"
    else:
        awards_path = download_from_sbir_gov(dest)
        sbir_source = "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv"

    usaspending_path = None
    usaspending_api = args.usaspending_api
    if args.usaspending_s3:
        usa_dest = Path("data/usaspending/recipient_lookup.parquet")
        usaspending_path = download_usaspending_from_s3(
            usa_dest, args.s3_bucket, args.usaspending_s3_prefix,
        )
    elif args.usaspending:
        if not args.usaspending.exists():
            print(f"USAspending file not found: {args.usaspending}", file=sys.stderr)
            sys.exit(1)
        usaspending_path = args.usaspending

    run_analysis(
        awards_path, args.fy, args.margin_awards, args.margin_ratio,
        usaspending_path, usaspending_api, sbir_source,
    )


if __name__ == "__main__":
    main()
