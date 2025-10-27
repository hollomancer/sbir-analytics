#!/usr/bin/env python3
"""Benchmark script for enrichment pipeline performance testing.

This script measures and records performance metrics for the SBIR-USAspending
enrichment pipeline, including execution time, memory usage, and throughput.

It supports:
- Loading SBIR sample data
- Running enrichment with performance monitoring enabled
- Outputting timing and memory metrics to JSON
- Comparing against historical baselines if available
- Detecting performance regressions

Usage:
    python scripts/benchmark_enrichment.py [--sample-size 1000] [--output reports/benchmarks/baseline.json]
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
from src.enrichers.usaspending_enricher import enrich_sbir_with_usaspending
from src.extractors.sbir import SbirDuckDBExtractor
from src.utils.performance_monitor import performance_monitor


def load_sample_data(sample_size: Optional[int] = None) -> tuple[pd.DataFrame, int]:
    """
    Load sample SBIR data for benchmarking.

    Args:
        sample_size: Maximum number of records to load (None = all)

    Returns:
        Tuple of (SBIR DataFrame, total available records)
    """
    config = get_config()
    sbir_config = config.extraction.sbir

    logger.info(f"Loading SBIR sample data from {sbir_config.csv_path}")

    try:
        # Load full data
        with performance_monitor.monitor_block("data_load"):
            full_df = pd.read_csv(sbir_config.csv_path)

        total_records = len(full_df)
        logger.info(f"Loaded {total_records} total SBIR records")

        # Apply sample limit if specified
        if sample_size and sample_size < total_records:
            sample_df = full_df.head(sample_size).copy()
            logger.info(f"Using sample of {len(sample_df)} records for benchmarking")
            return sample_df, total_records
        else:
            logger.info(f"Using all {total_records} records for benchmarking")
            return full_df, total_records

    except Exception as e:
        logger.error(f"Failed to load SBIR data: {e}")
        raise


def load_usaspending_lookup() -> pd.DataFrame:
    """
    Load USAspending recipient lookup data.

    Returns:
        USAspending recipient DataFrame
    """
    logger.info("Loading USAspending recipient lookup data")

    try:
        # Try to load from processed data
        processed_path = Path("data/processed/usaspending_recipients.parquet")
        if processed_path.exists():
            with performance_monitor.monitor_block("usaspending_load"):
                df = pd.read_parquet(processed_path)
            logger.info(f"Loaded {len(df)} USAspending recipients from parquet")
            return df

        # Fallback: load from CSV if available
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


def run_enrichment_benchmark(sbir_df: pd.DataFrame, usaspending_df: pd.DataFrame) -> Dict[str, Any]:
    """
    Run enrichment pipeline with performance monitoring.

    Args:
        sbir_df: SBIR awards DataFrame
        usaspending_df: USAspending recipients DataFrame

    Returns:
        Dictionary with enrichment results and metrics
    """
    logger.info(f"Running enrichment on {len(sbir_df)} SBIR records")

    # Reset performance monitor for clean metrics
    performance_monitor.reset_metrics()

    try:
        # Run enrichment with monitoring
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

        # Calculate enrichment statistics
        total_awards = len(enriched_df)
        matched_awards = enriched_df["_usaspending_match_method"].notna().sum()
        exact_matches = (
            enriched_df["_usaspending_match_method"].str.contains("exact", na=False).sum()
        )
        fuzzy_matches = (
            enriched_df["_usaspending_match_method"].str.contains("fuzzy", na=False).sum()
        )
        match_rate = matched_awards / total_awards if total_awards > 0 else 0

        # Get performance metrics
        perf_summary = performance_monitor.get_metrics_summary()
        enrichment_perf = perf_summary.get("enrichment_full", {})

        # Build results
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


def load_baseline(baseline_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """
    Load historical benchmark baseline if it exists.

    Args:
        baseline_path: Optional path to baseline file

    Returns:
        Baseline benchmark dict or None if not found
    """
    if baseline_path is None:
        baseline_path = Path("reports/benchmarks/baseline.json")

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


def detect_regressions(current: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
    """
    Detect performance regressions by comparing current to baseline.

    Args:
        current: Current benchmark results
        baseline: Historical baseline results

    Returns:
        Regression analysis results
    """
    regressions = {"warnings": [], "failures": []}

    # Extract metrics
    current_perf = current["performance_metrics"]
    baseline_perf = baseline["performance_metrics"]

    current_time = current_perf["total_duration_seconds"]
    baseline_time = baseline_perf["total_duration_seconds"]
    current_memory = current_perf["peak_memory_mb"]
    baseline_memory = baseline_perf["peak_memory_mb"]

    # Calculate deltas
    time_delta_percent = (
        ((current_time - baseline_time) / baseline_time * 100) if baseline_time > 0 else 0
    )
    memory_delta_percent = (
        ((current_memory - baseline_memory) / baseline_memory * 100) if baseline_memory > 0 else 0
    )

    # Check thresholds
    # Time regressions
    if time_delta_percent > 25:
        regressions["failures"].append(
            f"Time regression: +{time_delta_percent:.1f}% "
            f"({baseline_time:.2f}s → {current_time:.2f}s)"
        )
    elif time_delta_percent > 10:
        regressions["warnings"].append(
            f"Time warning: +{time_delta_percent:.1f}% "
            f"({baseline_time:.2f}s → {current_time:.2f}s)"
        )

    # Memory regressions
    if memory_delta_percent > 50:
        regressions["failures"].append(
            f"Memory regression: +{memory_delta_percent:.1f}% "
            f"({baseline_memory:.0f}MB → {current_memory:.0f}MB)"
        )
    elif memory_delta_percent > 20:
        regressions["warnings"].append(
            f"Memory warning: +{memory_delta_percent:.1f}% "
            f"({baseline_memory:.0f}MB → {current_memory:.0f}MB)"
        )

    # Match rate regression
    current_match_rate = current["enrichment_stats"]["match_rate"]
    baseline_match_rate = baseline["enrichment_stats"]["match_rate"]
    match_rate_delta = (current_match_rate - baseline_match_rate) * 100

    if match_rate_delta < -5:
        regressions["failures"].append(
            f"Match rate regression: {baseline_match_rate:.1%} → {current_match_rate:.1%}"
        )

    # Add regression analysis
    regressions["analysis"] = {
        "time_delta_percent": round(time_delta_percent, 1),
        "memory_delta_percent": round(memory_delta_percent, 1),
        "match_rate_delta_percent": round(match_rate_delta, 1),
    }

    return regressions


def save_benchmark(
    benchmark_data: Dict[str, Any],
    output_path: Optional[Path] = None,
) -> Path:
    """
    Save benchmark results to JSON file.

    Args:
        benchmark_data: Benchmark data to save
        output_path: Path to save to (default: reports/benchmarks/<timestamp>.json)

    Returns:
        Path where benchmark was saved
    """
    if output_path is None:
        benchmarks_dir = Path("reports/benchmarks")
        benchmarks_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = benchmarks_dir / f"benchmark_{timestamp}.json"

    # Add timestamp and metadata
    benchmark_data["timestamp"] = datetime.now().isoformat()
    benchmark_data["benchmark_version"] = "1.0"

    # Save to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(benchmark_data, f, indent=2, default=str)

    logger.info(f"Benchmark saved to {output_path}")
    return output_path


def main():
    """Run the benchmarking script."""
    parser = argparse.ArgumentParser(
        description="Benchmark the SBIR-USAspending enrichment pipeline"
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="Maximum number of SBIR records to benchmark (default: all)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for benchmark JSON (default: reports/benchmarks/benchmark_<timestamp>.json)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="Path to baseline benchmark for regression detection (default: reports/benchmarks/baseline.json)",
    )
    parser.add_argument(
        "--save-as-baseline",
        action="store_true",
        help="Save this benchmark as the new baseline",
    )

    args = parser.parse_args()

    logger.info("=" * 80)
    logger.info("SBIR-USAspending Enrichment Pipeline Benchmark")
    logger.info("=" * 80)

    try:
        # Load data
        logger.info("\n1. Loading data...")
        sbir_df, total_sbir = load_sample_data(args.sample_size)
        usaspending_df = load_usaspending_lookup()

        # Run enrichment benchmark
        logger.info("\n2. Running enrichment benchmark...")
        benchmark_results = run_enrichment_benchmark(sbir_df, usaspending_df)

        # Load baseline if available
        baseline = load_baseline(args.baseline)
        if baseline:
            logger.info("\n3. Detecting regressions...")
            regressions = detect_regressions(benchmark_results, baseline)
            benchmark_results["regressions"] = regressions

            # Log results
            if regressions["failures"]:
                logger.error("REGRESSION FAILURES DETECTED:")
                for failure in regressions["failures"]:
                    logger.error(f"  ✗ {failure}")
            if regressions["warnings"]:
                logger.warning("Performance warnings:")
                for warning in regressions["warnings"]:
                    logger.warning(f"  ⚠ {warning}")
        else:
            logger.info("No baseline available for comparison (creating new)")

        # Save benchmark
        logger.info("\n4. Saving benchmark results...")
        output_path = save_benchmark(benchmark_results, args.output)

        # Optionally save as baseline
        if args.save_as_baseline:
            baseline_path = Path("reports/benchmarks/baseline.json")
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            with open(baseline_path, "w") as f:
                json.dump(benchmark_results, f, indent=2, default=str)
            logger.info(f"Saved as new baseline: {baseline_path}")

        # Print summary
        logger.info("\n" + "=" * 80)
        logger.info("BENCHMARK SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Sample size: {len(sbir_df)} records")
        logger.info(f"USAspending records: {len(usaspending_df)}")
        logger.info(f"Match rate: {benchmark_results['enrichment_stats']['match_rate']:.1%}")
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
