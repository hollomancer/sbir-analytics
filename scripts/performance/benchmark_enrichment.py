#!/usr/bin/env python3
"""Benchmark script for enrichment pipeline performance testing.

Measures execution time, memory usage, and throughput for the SBIR-USAspending
enrichment pipeline.  Supports comparison against a historical baseline and
saves results as JSON.

Usage:
    python scripts/performance/benchmark_enrichment.py [--sample-size 1000] [--output path.json]
    python scripts/performance/benchmark_enrichment.py --baseline reports/benchmarks/baseline.json
    python scripts/performance/benchmark_enrichment.py --save-as-baseline
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from loguru import logger

# Ensure workspace root is importable
_workspace_root = str(Path(__file__).resolve().parent.parent.parent)
if _workspace_root not in sys.path:
    sys.path.insert(0, _workspace_root)

from scripts.performance.benchmark_base import (
    load_baseline,
    load_sample_data,
    load_usaspending_lookup,
    run_enrichment_benchmark,
    save_benchmark,
    save_json,
)


# ---------------------------------------------------------------------------
# Regression detection (self-contained for standalone benchmark runs)
# ---------------------------------------------------------------------------


def detect_regressions(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    """Compare current results against baseline and flag regressions."""
    regressions: dict[str, Any] = {"warnings": [], "failures": []}

    current_perf = current["performance_metrics"]
    baseline_perf = baseline["performance_metrics"]

    current_time = current_perf["total_duration_seconds"]
    baseline_time = baseline_perf["total_duration_seconds"]
    current_memory = current_perf["peak_memory_mb"]
    baseline_memory = baseline_perf["peak_memory_mb"]

    time_delta_pct = (
        ((current_time - baseline_time) / baseline_time * 100) if baseline_time > 0 else 0
    )
    memory_delta_pct = (
        ((current_memory - baseline_memory) / baseline_memory * 100) if baseline_memory > 0 else 0
    )

    if time_delta_pct > 25:
        regressions["failures"].append(
            f"Time regression: +{time_delta_pct:.1f}% "
            f"({baseline_time:.2f}s -> {current_time:.2f}s)"
        )
    elif time_delta_pct > 10:
        regressions["warnings"].append(
            f"Time warning: +{time_delta_pct:.1f}% ({baseline_time:.2f}s -> {current_time:.2f}s)"
        )

    if memory_delta_pct > 50:
        regressions["failures"].append(
            f"Memory regression: +{memory_delta_pct:.1f}% "
            f"({baseline_memory:.0f}MB -> {current_memory:.0f}MB)"
        )
    elif memory_delta_pct > 20:
        regressions["warnings"].append(
            f"Memory warning: +{memory_delta_pct:.1f}% "
            f"({baseline_memory:.0f}MB -> {current_memory:.0f}MB)"
        )

    current_match = current["enrichment_stats"]["match_rate"]
    baseline_match = baseline["enrichment_stats"]["match_rate"]
    match_delta = (current_match - baseline_match) * 100
    if match_delta < -5:
        regressions["failures"].append(
            f"Match rate regression: {baseline_match:.1%} -> {current_match:.1%}"
        )

    regressions["analysis"] = {
        "time_delta_percent": round(time_delta_pct, 1),
        "memory_delta_percent": round(memory_delta_pct, 1),
        "match_rate_delta_percent": round(match_delta, 1),
    }
    return regressions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )

    parser = argparse.ArgumentParser(
        description="Benchmark the SBIR-USAspending enrichment pipeline",
        prog="benchmark_enrichment",
    )
    parser.add_argument("--sample-size", type=int, help="Number of records to process")
    parser.add_argument("--output", type=str, default="", help="Output path for benchmark JSON")
    parser.add_argument("--baseline", type=str, help="Baseline benchmark file for comparison")
    parser.add_argument("--save-as-baseline", action="store_true", help="Save results as baseline")
    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("SBIR-USAspending Enrichment Pipeline Benchmark".center(80))
    logger.info("=" * 80)

    try:
        # Load data
        logger.info("\n--- Loading data ---")
        sbir_df, _ = load_sample_data(args.sample_size)
        usaspending_df = load_usaspending_lookup()

        # Run enrichment benchmark
        logger.info("\n--- Running enrichment benchmark ---")
        results = run_enrichment_benchmark(sbir_df, usaspending_df)

        # Baseline comparison
        baseline = load_baseline(Path(args.baseline) if args.baseline else None)
        if baseline:
            logger.info("\n--- Detecting regressions ---")
            regressions = detect_regressions(results, baseline)
            results["regressions"] = regressions
            if regressions["failures"]:
                for f in regressions["failures"]:
                    logger.error(f"  {f}")
            if regressions["warnings"]:
                for w in regressions["warnings"]:
                    logger.warning(f"  {w}")

        # Save
        logger.info("\n--- Saving benchmark results ---")
        output_path = save_benchmark(results, args.output)
        if args.save_as_baseline:
            save_json(results, Path("reports/benchmarks/baseline.json"))

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info(f"Sample size:  {len(sbir_df)}")
        logger.info(f"Match rate:   {results['enrichment_stats']['match_rate']:.1%}")
        logger.info(f"Duration:     {results['performance_metrics']['total_duration_seconds']:.2f}s")
        logger.info(f"Throughput:   {results['performance_metrics']['records_per_second']:.0f} rec/s")
        logger.info(f"Peak memory:  {results['performance_metrics']['peak_memory_mb']:.0f}MB")
        logger.info(f"Output:       {output_path}")
        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Benchmark failed: {e}", exc_info=True)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
