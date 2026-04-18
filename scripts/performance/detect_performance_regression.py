#!/usr/bin/env python3
"""Automated performance regression detection for CI/CD pipelines.

Runs an enrichment benchmark, compares against a historical baseline, and
generates reports in JSON, Markdown, HTML, or GitHub PR comment format.
Designed for integration into GitHub Actions / GitLab CI.

Usage:
    python scripts/performance/detect_performance_regression.py --fail-on-regression
    python scripts/performance/detect_performance_regression.py --output-json report.json
    python scripts/performance/detect_performance_regression.py --time-failure-threshold 20
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

# Ensure workspace root is importable
_workspace_root = str(Path(__file__).resolve().parent.parent.parent)
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)

from sbir_etl.utils.monitoring.metrics import PerformanceMetrics
from sbir_etl.utils.monitoring.reporting import PerformanceReporter

from scripts.performance.benchmark_base import (
    load_baseline,
    load_sample_data,
    load_usaspending_lookup,
    run_enrichment_benchmark,
)


# ---------------------------------------------------------------------------
# Regression analysis (uses PerformanceReporter for threshold-aware comparison)
# ---------------------------------------------------------------------------


def generate_regression_summary(
    current_benchmark: dict[str, Any],
    baseline: dict[str, Any] | None,
    reporter: PerformanceReporter,
) -> dict[str, Any]:
    """Build a structured regression summary dict."""
    current_metrics = PerformanceMetrics.from_benchmark(current_benchmark)
    summary: dict[str, Any] = {
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


def output_github_pr_comment(summary: dict[str, Any], output_path: Path) -> None:
    """Write a GitHub-flavoured Markdown comment summarising the benchmark."""
    emoji_map = {"PASS": "pass", "WARNING": "warning", "FAILURE": "x"}
    emoji = {"PASS": "✅", "WARNING": "⚠️", "FAILURE": "❌"}.get(summary["severity"], "ℹ️")
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
        lines.extend([
            "### Regression Analysis",
            "",
            f"- **Time Delta:** {baseline['time_delta_percent']:+.1f}%",
            f"- **Memory Delta:** {baseline['memory_delta_percent']:+.1f}%",
            "",
        ])
        if summary["issues"]:
            lines.append("### Issues Detected")
            lines.append("")
            for issue in summary["issues"]:
                lines.append(f"- {issue}")
            lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    logger.info(f"GitHub PR comment saved to {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Detect performance regressions in enrichment pipeline"
    )
    parser.add_argument("--sample-size", type=int, default=None, help="Records to benchmark")
    parser.add_argument(
        "--baseline", type=Path, default=Path("reports/benchmarks/baseline.json"),
        help="Path to baseline benchmark",
    )
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-markdown", type=Path, default=None)
    parser.add_argument("--output-html", type=Path, default=None)
    parser.add_argument("--output-github-comment", type=Path, default=None)
    parser.add_argument("--time-warning-threshold", type=float, default=10.0)
    parser.add_argument("--time-failure-threshold", type=float, default=25.0)
    parser.add_argument("--memory-warning-threshold", type=float, default=20.0)
    parser.add_argument("--memory-failure-threshold", type=float, default=50.0)
    parser.add_argument("--fail-on-regression", action="store_true")
    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("Performance Regression Detection")
    logger.info("=" * 80)

    try:
        # 1. Load data
        logger.info("\n1. Loading data...")
        sbir_df, _ = load_sample_data(args.sample_size)
        usaspending_df = load_usaspending_lookup()

        # 2. Run benchmark
        logger.info("\n2. Running enrichment benchmark...")
        current_benchmark = run_enrichment_benchmark(sbir_df, usaspending_df)

        # 3. Load baseline
        logger.info("\n3. Loading baseline...")
        baseline = load_baseline(args.baseline)

        # 4. Analyse regressions
        logger.info("\n4. Analyzing regressions...")
        reporter = PerformanceReporter(
            time_warning_threshold=args.time_warning_threshold,
            time_failure_threshold=args.time_failure_threshold,
            memory_warning_threshold=args.memory_warning_threshold,
            memory_failure_threshold=args.memory_failure_threshold,
        )
        summary = generate_regression_summary(current_benchmark, baseline, reporter)

        # 5. Output results
        logger.info("\n5. Saving results...")
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(json.dumps(summary, indent=2))
            logger.info(f"JSON summary saved to {args.output_json}")

        if args.output_markdown:
            args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
            markdown = reporter.format_benchmark_markdown(current_benchmark)
            args.output_markdown.write_text(markdown)
            logger.info(f"Markdown report saved to {args.output_markdown}")

        if args.output_html:
            args.output_html.parent.mkdir(parents=True, exist_ok=True)
            reporter.save_html_report(current_benchmark, args.output_html)

        if args.output_github_comment:
            output_github_pr_comment(summary, args.output_github_comment)

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info(f"Status:      {summary['severity']}")
        logger.info(f"Duration:    {summary['current_metrics']['duration_seconds']:.2f}s")
        logger.info(f"Peak memory: {summary['current_metrics']['peak_memory_mb']:.0f}MB")
        logger.info(f"Match rate:  {summary['current_metrics']['match_rate']:.1%}")
        if summary.get("baseline_comparison"):
            bc = summary["baseline_comparison"]
            logger.info(f"Time delta:  {bc['time_delta_percent']:+.1f}%")
            logger.info(f"Mem delta:   {bc['memory_delta_percent']:+.1f}%")
        if summary["issues"]:
            logger.warning("Issues:")
            for issue in summary["issues"]:
                logger.warning(f"  - {issue}")
        logger.info("=" * 80)

        if args.fail_on_regression and summary["regression_detected"]:
            logger.error(f"Regression {summary['severity']} detected - exiting with code 1")
            return 1

        return 0

    except Exception as e:
        logger.error(f"Regression detection failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
