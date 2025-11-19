#!/usr/bin/env python3
"""Automated performance regression detection for CI/CD pipelines.

This script runs performance benchmarks and detects regressions against a
historical baseline. It's designed to be integrated into CI/CD workflows
(GitHub Actions, GitLab CI, etc.) to automatically flag performance issues.

Features:
- Runs benchmark and compares against baseline
- Generates detailed regression report
- Outputs results in machine-readable format (JSON) and human-readable (Markdown)
- Configurable exit codes for CI integration (fail on regression)
- Optional Slack/GitHub PR comment integration

Usage:
    # Run and fail on regression
    python scripts/detect_performance_regression.py --fail-on-regression

    # Run and save comparison report
    python scripts/detect_performance_regression.py --output-comparison report.md

    # Run with custom thresholds
    python scripts/detect_performance_regression.py --time-failure-threshold 20
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from src.config.loader import get_config
from src.enrichers.usaspending import enrich_sbir_with_usaspending
from src.utils.monitoring import performance_monitor
from src.utils.performance_reporting import PerformanceMetrics, PerformanceReporter


def load_sample_data(sample_size: int | None = None) -> tuple[pd.DataFrame, int]:
    """Load sample SBIR data for benchmarking."""
    config = get_config()
    sbir_config = config.extraction.sbir

    logger.info(f"Loading SBIR sample data from {sbir_config.csv_path}")

    try:
        with performance_monitor.monitor_block("data_load"):
            full_df = pd.read_csv(sbir_config.csv_path)

        total_records = len(full_df)
        logger.info(f"Loaded {total_records} total SBIR records")

        if sample_size and sample_size < total_records:
            sample_df = full_df.head(sample_size).copy()
            logger.info(f"Using sample of {len(sample_df)} records")
            return sample_df, total_records
        else:
            logger.info(f"Using all {total_records} records")
            return full_df, total_records

    except Exception as e:
        logger.error(f"Failed to load SBIR data: {e}")
        raise


def load_usaspending_lookup() -> pd.DataFrame:
    """Load USAspending recipient lookup data."""
    logger.info("Loading USAspending recipient lookup data")

    try:
        processed_path = Path("data/processed/usaspending_recipients.parquet")
        if processed_path.exists():
            with performance_monitor.monitor_block("usaspending_load"):
                df = pd.read_parquet(processed_path)
            logger.info(f"Loaded {len(df)} USAspending recipients from parquet")
            return df

        csv_path = Path("data/raw/usaspending/recipients.csv")
        if csv_path.exists():
            with performance_monitor.monitor_block("usaspending_load"):
                df = pd.read_csv(csv_path)
            logger.info(f"Loaded {len(df)} USAspending recipients from CSV")
            return df

        logger.warning("USAspending data not found; using empty lookup")
        return pd.DataFrame()

    except Exception as e:
        logger.error(f"Failed to load USAspending data: {e}")
        return pd.DataFrame()


def run_enrichment_benchmark(sbir_df: pd.DataFrame, usaspending_df: pd.DataFrame) -> dict[str, Any]:
    """Run enrichment pipeline with performance monitoring."""
    logger.info(f"Running enrichment on {len(sbir_df)} SBIR records")

    performance_monitor.reset_metrics()

    try:
        with performance_monitor.monitor_block("enrichment_full"):
            enriched_df = enrich_sbir_with_usaspending(
                sbir_df=sbir_df,
                recipient_df=usaspending_df,
                sbir_company_col="Company",
                sbir_uei_col="UEI",
                sbir_duns_col="Duns",
                recipient_name_col="recipient_name" if not usaspending_df.empty else None,
                recipient_uei_col="recipient_uei" if not usaspending_df.empty else None,
                recipient_duns_col="recipient_duns" if not usaspending_df.empty else None,
                high_threshold=90,
                low_threshold=75,
                return_candidates=True,
            )

        logger.info(f"Enrichment complete: {len(enriched_df)} records processed")

        total_awards = len(enriched_df)
        matched_awards = enriched_df["_usaspending_match_method"].notna().sum()
        exact_matches = (
            enriched_df["_usaspending_match_method"].str.contains("exact", na=False).sum()
        )
        fuzzy_matches = (
            enriched_df["_usaspending_match_method"].str.contains("fuzzy", na=False).sum()
        )
        match_rate = matched_awards / total_awards if total_awards > 0 else 0

        perf_summary = performance_monitor.get_metrics_summary()
        enrichment_perf = perf_summary.get("enrichment_full", {})

        results = {
            "enrichment_stats": {
                "total_awards": total_awards,
                "matched_awards": matched_awards,
                "exact_matches": exact_matches,
                "fuzzy_matches": fuzzy_matches,
                "match_rate": match_rate,
                "unmatched_awards": total_awards - matched_awards,
            },
            "performance_metrics": {
                "total_duration_seconds": enrichment_perf.get("total_duration", 0),
                "avg_duration_seconds": enrichment_perf.get("avg_duration", 0),
                "records_per_second": (
                    total_awards / enrichment_perf.get("total_duration", 1)
                    if enrichment_perf.get("total_duration", 0) > 0
                    else 0
                ),
                "peak_memory_mb": enrichment_perf.get("max_peak_memory_mb", 0),
                "avg_memory_delta_mb": enrichment_perf.get("avg_memory_delta_mb", 0),
                "max_memory_delta_mb": enrichment_perf.get("total_memory_delta_mb", 0),
            },
        }

        logger.info(
            f"Benchmark results: {match_rate:.1%} match rate, "
            f"{results['performance_metrics']['records_per_second']:.0f} records/sec, "
            f"{results['performance_metrics']['peak_memory_mb']:.0f}MB peak memory"
        )

        return results

    except Exception as e:
        logger.error(f"Enrichment benchmark failed: {e}")
        raise


def load_baseline(
    baseline_path: Path = Path("reports/benchmarks/baseline.json"),
) -> dict[str, Any] | None:
    """Load historical benchmark baseline."""
    if baseline_path.exists():
        try:
            with open(baseline_path) as f:
                baseline = json.load(f)
            logger.info(f"Loaded baseline from {baseline_path}")
            return baseline
        except Exception as e:
            logger.warning(f"Failed to load baseline: {e}")
            return None
    else:
        logger.info(f"No baseline found at {baseline_path}")
        return None


def generate_regression_summary(
    current_benchmark: dict[str, Any],
    baseline: dict[str, Any] | None,
    reporter: PerformanceReporter,
) -> dict[str, Any]:
    """Generate comprehensive regression summary."""
    current_metrics = PerformanceMetrics.from_benchmark(current_benchmark)
    summary = {
        "timestamp": datetime.now().isoformat(),
        "current_metrics": {
            "duration_seconds": current_metrics.total_duration_seconds,
            "throughput_records_per_sec": current_metrics.records_per_second,
            "peak_memory_mb": current_metrics.peak_memory_mb,
            "match_rate": current_metrics.match_rate,
        },
        "regression_detected": False,
        "severity": "PASS",
        "issues": [],
        "baseline_comparison": None,
    }

    if baseline:
        baseline_metrics = PerformanceMetrics.from_benchmark(baseline)
        comparison = reporter.compare_metrics(baseline_metrics, current_metrics)

        summary["baseline_comparison"] = {
            "baseline_duration_seconds": baseline_metrics.total_duration_seconds,
            "baseline_peak_memory_mb": baseline_metrics.peak_memory_mb,
            "baseline_match_rate": baseline_metrics.match_rate,
            "time_delta_percent": comparison.time_delta_percent,
            "memory_delta_percent": comparison.memory_delta_percent,
            "match_rate_delta_percent": comparison.match_rate_delta_percent,
        }

        if comparison.regression_messages:
            summary["regression_detected"] = True
            summary["severity"] = comparison.regression_severity
            summary["issues"] = comparison.regression_messages

    return summary


def output_github_pr_comment(
    summary: dict[str, Any],
    output_path: Path,
) -> None:
    """Generate GitHub PR comment format output."""
    severity_emoji = {
        "PASS": "✅",
        "WARNING": "⚠️",
        "FAILURE": "❌",
    }

    emoji = severity_emoji.get(summary["severity"], "ℹ️")
    current = summary["current_metrics"]
    baseline = summary.get("baseline_comparison")

    lines = [
        f"## {emoji} Performance Benchmark Results",
        "",
        "### Current Metrics",
        "",
        f"- **Duration:** {current['duration_seconds']:.2f}s",
        f"- **Throughput:** {current['throughput_records_per_sec']:.0f} records/sec",
        f"- **Peak Memory:** {current['peak_memory_mb']:.0f} MB",
        f"- **Match Rate:** {current['match_rate']:.1%}",
        "",
    ]

    if baseline:
        lines.extend(
            [
                "### Regression Analysis",
                "",
                f"- **Time Delta:** {baseline['time_delta_percent']:+.1f}%",
                f"- **Memory Delta:** {baseline['memory_delta_percent']:+.1f}%",
                "",
            ]
        )

        if summary["issues"]:
            lines.append("### Issues Detected")
            lines.append("")
            for issue in summary["issues"]:
                lines.append(f"- {issue}")
            lines.append("")

    with open(output_path, "w") as f:
        f.write("\n".join(lines))

    logger.info(f"GitHub PR comment saved to {output_path}")


def main():
    """Run regression detection."""
    parser = argparse.ArgumentParser(
        description="Detect performance regressions in enrichment pipeline"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Number of SBIR records to benchmark",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=Path("reports/benchmarks/baseline.json"),
        help="Path to baseline benchmark",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Save regression summary as JSON",
    )
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=None,
        help="Save regression summary as Markdown",
    )
    parser.add_argument(
        "--output-html",
        type=Path,
        default=None,
        help="Save regression summary as HTML",
    )
    parser.add_argument(
        "--output-github-comment",
        type=Path,
        default=None,
        help="Save GitHub PR comment format output",
    )
    parser.add_argument(
        "--time-warning-threshold",
        type=float,
        default=10.0,
        help="Time increase % for warning (default 10)",
    )
    parser.add_argument(
        "--time-failure-threshold",
        type=float,
        default=25.0,
        help="Time increase % for failure (default 25)",
    )
    parser.add_argument(
        "--memory-warning-threshold",
        type=float,
        default=20.0,
        help="Memory increase % for warning (default 20)",
    )
    parser.add_argument(
        "--memory-failure-threshold",
        type=float,
        default=50.0,
        help="Memory increase % for failure (default 50)",
    )
    parser.add_argument(
        "--fail-on-regression",
        action="store_true",
        help="Exit with code 1 if regression detected",
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("Performance Regression Detection")
    logger.info("=" * 80)

    try:
        # Load data
        logger.info("\n1. Loading data...")
        sbir_df, _ = load_sample_data(args.sample_size)
        usaspending_df = load_usaspending_lookup()

        # Run benchmark
        logger.info("\n2. Running enrichment benchmark...")
        current_benchmark = run_enrichment_benchmark(sbir_df, usaspending_df)

        # Load baseline
        logger.info("\n3. Loading baseline...")
        baseline = load_baseline(args.baseline)

        # Create reporter with custom thresholds
        reporter = PerformanceReporter(
            time_warning_threshold=args.time_warning_threshold,
            time_failure_threshold=args.time_failure_threshold,
            memory_warning_threshold=args.memory_warning_threshold,
            memory_failure_threshold=args.memory_failure_threshold,
        )

        # Generate summary
        logger.info("\n4. Analyzing regressions...")
        summary = generate_regression_summary(current_benchmark, baseline, reporter)

        # Output results
        logger.info("\n5. Saving results...")

        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            with open(args.output_json, "w") as f:
                json.dump(summary, f, indent=2)
            logger.info(f"JSON summary saved to {args.output_json}")

        if args.output_markdown:
            args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
            markdown = reporter.format_benchmark_markdown(current_benchmark)
            with open(args.output_markdown, "w") as f:
                f.write(markdown)
            logger.info(f"Markdown report saved to {args.output_markdown}")

        if args.output_html:
            args.output_html.parent.mkdir(parents=True, exist_ok=True)
            reporter.save_html_report(current_benchmark, args.output_html)

        if args.output_github_comment:
            args.output_github_comment.parent.mkdir(parents=True, exist_ok=True)
            output_github_pr_comment(summary, args.output_github_comment)

        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("REGRESSION DETECTION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Status: {summary['severity']}")
        logger.info(f"Duration: {summary['current_metrics']['duration_seconds']:.2f}s")
        logger.info(f"Peak Memory: {summary['current_metrics']['peak_memory_mb']:.0f}MB")
        logger.info(f"Match Rate: {summary['current_metrics']['match_rate']:.1%}")

        if summary.get("baseline_comparison"):
            bc = summary["baseline_comparison"]
            logger.info(f"Time Delta: {bc['time_delta_percent']:+.1f}%")
            logger.info(f"Memory Delta: {bc['memory_delta_percent']:+.1f}%")

        if summary["issues"]:
            logger.warning("Issues detected:")
            for issue in summary["issues"]:
                logger.warning(f"  - {issue}")

        logger.info("=" * 80 + "\n")

        # Exit with appropriate code
        if args.fail_on_regression and summary["regression_detected"]:
            if summary["severity"] == "FAILURE":
                logger.error("Regression FAILURE detected - exiting with code 1")
                return 1
            elif summary["severity"] == "WARNING" and args.fail_on_regression:
                logger.warning("Regression WARNING detected - exiting with code 1")
                return 1

        return 0

    except Exception as e:
        logger.error(f"Regression detection failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
