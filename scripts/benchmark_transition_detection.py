#!/usr/bin/env python3
"""Benchmark script for transition detection performance testing.
This script measures and records performance metrics for the transition
detection pipeline, including execution time, memory usage, and throughput.
Usage:
    python scripts/benchmark_transition_detection.py [--sample-size 1000] [--output reports/benchmarks/transition_detection_baseline.json]
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from loguru import logger

from src.config.loader import get_config
from src.enrichers.transition_detector import TransitionDetector
from src.utils.performance_monitor import performance_monitor


def load_company_data(sample_size: Optional[int] = None) -> tuple[pd.DataFrame, int]:
    """
    Load company data for benchmarking.
    Args:
        sample_size: Maximum number of records to load (None = all)
    Returns:
        Tuple of (Company DataFrame, total available records)
    """
    # This is a placeholder for loading actual company data.
    # In a real scenario, this would load from a database or a file.
    logger.info("Loading company data...")
    data = {
        "company_id": range(10000),
        "company_name": [f"Company {i}" for i in range(10000)],
        "description": ["This is a test description." for _ in range(10000)],
    }
    full_df = pd.DataFrame(data)
    total_records = len(full_df)

    if sample_size and sample_size < total_records:
        sample_df = full_df.head(sample_size).copy()
        logger.info(f"Using sample of {len(sample_df)} records for benchmarking")
        return sample_df, total_records
    else:
        logger.info(f"Using all {total_records} records for benchmarking")
        return full_df, total_records


def run_transition_detection_benchmark(company_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Run transition detection with performance monitoring.
    Args:
        company_df: Company data DataFrame
    Returns:
        Dictionary with detection results and metrics
    """
    logger.info(f"Running transition detection on {len(company_df)} company records")
    performance_monitor.reset_metrics()
    detector = TransitionDetector()

    with performance_monitor.monitor_block("transition_detection_full"):
        transitions = detector.detect(company_df)

    logger.info(f"Transition detection complete: {len(transitions)} transitions found")

    perf_summary = performance_monitor.get_metrics_summary()
    detection_perf = perf_summary.get("transition_detection_full", {})

    results = {
        "detection_stats": {
            "total_companies": len(company_df),
            "transitions_found": len(transitions),
        },
        "performance_metrics": {
            "total_duration_seconds": detection_perf.get("total_duration", 0),
            "avg_duration_seconds": detection_perf.get("avg_duration", 0),
            "records_per_second": (
                len(company_df) / detection_perf.get("total_duration", 1)
                if detection_perf.get("total_duration", 0) > 0
                else 0
            ),
            "peak_memory_mb": detection_perf.get("max_peak_memory_mb", 0),
        },
    }
    return results


def save_benchmark(
    benchmark_data: Dict[str, Any],
    output_path: Optional[Path] = None,
) -> Path:
    """
    Save benchmark results to JSON file.
    """
    if output_path is None:
        benchmarks_dir = Path("reports/benchmarks")
        benchmarks_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = benchmarks_dir / f"benchmark_transition_{timestamp}.json"

    benchmark_data["timestamp"] = datetime.now().isoformat()
    benchmark_data["benchmark_version"] = "1.0"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(benchmark_data, f, indent=2, default=str)

    logger.info(f"Benchmark saved to {output_path}")
    return output_path


def main():
    """Run the benchmarking script."""
    parser = argparse.ArgumentParser(description="Benchmark the transition detection pipeline")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Maximum number of company records to benchmark (default: all)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for benchmark JSON",
    )
    parser.add_argument(
        "--save-as-baseline",
        action="store_true",
        help="Save this benchmark as the new baseline",
    )
    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("Transition Detection Pipeline Benchmark")
    logger.info("=" * 80)

    try:
        logger.info("\n1. Loading data...")
        company_df, _ = load_company_data(args.sample_size)

        logger.info("\n2. Running transition detection benchmark...")
        benchmark_results = run_transition_detection_benchmark(company_df)

        logger.info("\n3. Saving benchmark results...")
        output_path = save_benchmark(benchmark_results, args.output)

        if args.save_as_baseline:
            baseline_path = Path("reports/benchmarks/transition_detection_baseline.json")
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            with open(baseline_path, "w") as f:
                json.dump(benchmark_results, f, indent=2, default=str)
            logger.info(f"Saved as new baseline: {baseline_path}")

        logger.info("\n" + "=" * 80)
        logger.info("BENCHMARK SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Sample size: {len(company_df)} records")
        logger.info(
            f"Transitions found: {benchmark_results['detection_stats']['transitions_found']}"
        )
        logger.info(
            f"Duration: {benchmark_results['performance_metrics']['total_duration_seconds']:.2f}s"
        )
        logger.info(
            f"Throughput: {benchmark_results['performance_metrics']['records_per_second']:.0f} records/sec"
        )
        logger.info(
            f"Peak memory: {benchmark_results['performance_metrics']['peak_memory_mb']:.0f}MB"
        )
        logger.info(f"Output: {output_path}")
        logger.info("=" * 80 + "\n")

    except Exception as e:
        logger.error(f"Benchmark failed: {e}", exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
