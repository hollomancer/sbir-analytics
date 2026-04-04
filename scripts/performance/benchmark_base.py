"""Shared utilities for enrichment benchmark and regression detection scripts.

Provides data loading, enrichment execution, baseline I/O, and JSON output
helpers used by both benchmark_enrichment.py and detect_performance_regression.py.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from sbir_etl.config.loader import get_config
from sbir_etl.enrichers.usaspending import enrich_sbir_with_usaspending
from sbir_etl.extractors.sbir import SbirDuckDBExtractor
from sbir_etl.utils.monitoring import performance_monitor


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_sample_data(sample_size: int | None = None) -> tuple[pd.DataFrame, int]:
    """Load SBIR awards via SbirDuckDBExtractor (S3-first, local fallback).

    Args:
        sample_size: Maximum records to return (None = all).

    Returns:
        (DataFrame, total_available_records)
    """
    config = get_config()
    sbir_config = config.extraction.sbir

    logger.info("Loading SBIR sample data (S3-first, local fallback)")

    with performance_monitor.monitor_block("data_load"):
        extractor = SbirDuckDBExtractor(
            csv_path=sbir_config.csv_path,
            duckdb_path=":memory:",
            table_name="sbir_awards",
            use_s3_first=sbir_config.use_s3_first,
        )
        import_metadata = extractor.import_csv()
        total_records = import_metadata["row_count"]
        logger.info(f"Loaded {total_records} total SBIR records from {extractor.csv_path}")
        full_df = extractor.extract_all()

    if sample_size and sample_size < total_records:
        sample_df = full_df.head(sample_size).copy()
        logger.info(f"Using sample of {len(sample_df)} records")
        return sample_df, total_records

    logger.info(f"Using all {total_records} records")
    return full_df, total_records


def load_usaspending_lookup() -> pd.DataFrame:
    """Load USAspending recipient lookup (parquet preferred, CSV fallback)."""
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


# ---------------------------------------------------------------------------
# Enrichment execution
# ---------------------------------------------------------------------------


def run_enrichment_benchmark(
    sbir_df: pd.DataFrame, usaspending_df: pd.DataFrame
) -> dict[str, Any]:
    """Run enrichment pipeline with performance monitoring.

    Returns dict with ``enrichment_stats`` and ``performance_metrics`` keys.
    """
    logger.info(f"Running enrichment on {len(sbir_df)} SBIR records")
    performance_monitor.reset_metrics()

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


# ---------------------------------------------------------------------------
# Baseline I/O
# ---------------------------------------------------------------------------


def load_baseline(
    baseline_path: Path | None = None,
) -> dict[str, Any] | None:
    """Load historical benchmark baseline JSON, or None if unavailable."""
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

    logger.info(f"No baseline found at {baseline_path}")
    return None


def save_benchmark(
    benchmark_data: dict[str, Any],
    output_path: Path | str | None = None,
) -> Path:
    """Save benchmark results to a timestamped JSON file.

    Returns the path where the file was written.
    """
    if output_path is None or output_path == "":
        benchmarks_dir = Path("reports/benchmarks")
        benchmarks_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = benchmarks_dir / f"benchmark_{timestamp}.json"
    else:
        output_path = Path(output_path)

    benchmark_data["timestamp"] = datetime.now().isoformat()
    benchmark_data["benchmark_version"] = "1.0"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(benchmark_data, f, indent=2, default=str)

    logger.info(f"Benchmark saved to {output_path}")
    return output_path


def save_json(data: dict[str, Any], path: Path) -> None:
    """Write a dict to a JSON file, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)
    logger.info(f"Saved to {path}")
