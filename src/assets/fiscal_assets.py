"""Dagster assets for fiscal analysis pipeline."""

from pathlib import Path
from typing import Any

import pandas as pd
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MetadataValue,
    Output,
    asset,
    asset_check,
)
from loguru import logger

from ..config.loader import get_config
from ..enrichers.fiscal_bea_mapper import NAICSToBEAMapper, enrich_awards_with_bea_sectors
from ..enrichers.fiscal_naics_enricher import enrich_sbir_awards_with_fiscal_naics
from ..utils.performance_monitor import performance_monitor


@asset(
    description="SBIR awards enriched with NAICS codes for fiscal analysis",
    group_name="enrichment",
    compute_kind="pandas",
)
def fiscal_naics_enriched_awards(
    context: AssetExecutionContext,
    enriched_sbir_awards: pd.DataFrame,
    raw_usaspending_recipients: pd.DataFrame | None = None,
) -> Output[pd.DataFrame]:
    """
    Enrich SBIR awards with NAICS codes using hierarchical fallback strategy.

    Uses the following fallback chain:
    1. Original SBIR data (confidence: 0.95)
    2. Existing USAspending matches in enriched_sbir_awards (confidence: 0.85-0.90)
    3. Fresh USAspending recipient lookup (confidence: 0.85-0.90)
    4. Agency defaults (confidence: 0.50)
    5. Sector fallback (confidence: 0.30)

    Args:
        enriched_sbir_awards: SBIR awards with USAspending enrichment
        raw_usaspending_recipients: Optional USAspending recipient data for fresh lookups

    Returns:
        Enriched DataFrame with NAICS codes and confidence metadata
    """
    config = get_config()

    context.log.info(
        "Starting NAICS enrichment for fiscal analysis",
        extra={
            "sbir_records": len(enriched_sbir_awards),
            "usaspending_recipients_available": raw_usaspending_recipients is not None,
        },
    )

    # Perform NAICS enrichment with performance monitoring
    with performance_monitor.monitor_block("fiscal_naics_enrichment"):
        enriched_df, quality_metrics = enrich_sbir_awards_with_fiscal_naics(
            awards_df=enriched_sbir_awards,
            usaspending_df=raw_usaspending_recipients,
        )

    # Extract statistics
    total_awards = len(enriched_df)
    naics_coverage = enriched_df["fiscal_naics_code"].notna().sum()
    coverage_rate = naics_coverage / total_awards if total_awards > 0 else 0

    # Source distribution
    source_counts = enriched_df["fiscal_naics_source"].value_counts(dropna=False).to_dict()

    # Confidence statistics
    confidence_stats = enriched_df["fiscal_naics_confidence"].dropna().describe()
    avg_confidence = confidence_stats.get("mean", 0.0)
    min_confidence = confidence_stats.get("min", 0.0)
    max_confidence = confidence_stats.get("max", 1.0)

    context.log.info(
        "NAICS enrichment complete",
        extra={
            "total_awards": total_awards,
            "naics_coverage": naics_coverage,
            "coverage_rate": f"{coverage_rate:.1%}",
            "source_distribution": source_counts,
            "avg_confidence": round(avg_confidence, 3),
            "confidence_range": f"{min_confidence:.2f}-{max_confidence:.2f}",
        },
    )

    # Get performance metrics
    perf_summary = performance_monitor.get_metrics_summary()
    perf_metrics = perf_summary.get("fiscal_naics_enrichment", {})
    duration = perf_metrics.get("total_duration", 0.0)
    peak_memory = perf_metrics.get("max_peak_memory_mb", 0.0)
    records_per_second = total_awards / duration if duration > 0 else 0

    # Create metadata
    metadata = {
        "num_records": len(enriched_df),
        "naics_coverage": f"{coverage_rate:.1%}",
        "naics_coverage_count": naics_coverage,
        "source_distribution": MetadataValue.json(source_counts),
        "confidence_stats": MetadataValue.json({
            "mean": round(avg_confidence, 3),
            "min": round(min_confidence, 3),
            "max": round(max_confidence, 3),
            "std": round(confidence_stats.get("std", 0.0), 3),
        }),
        "preview": MetadataValue.md(enriched_df.head(10).to_markdown()),
        # Performance metrics
        "performance_duration_seconds": round(duration, 2),
        "performance_records_per_second": round(records_per_second, 2),
        "performance_peak_memory_mb": round(peak_memory, 2),
        # Quality metrics
        "quality_coverage_threshold": f"{quality_metrics['naics_coverage_threshold']:.1%}",
        "quality_coverage_meets_threshold": quality_metrics["coverage_meets_threshold"],
        "quality_avg_confidence": round(avg_confidence, 3),
    }

    return Output(value=enriched_df, metadata=metadata)


@asset_check(
    asset="fiscal_naics_enriched_awards",
    description="NAICS coverage rate meets minimum threshold",
)
def fiscal_naics_coverage_check(fiscal_naics_enriched_awards: pd.DataFrame) -> AssetCheckResult:
    """
    Asset check to ensure NAICS coverage rate meets minimum threshold.

    This check will FAIL the asset if coverage falls below the configured threshold,
    preventing downstream fiscal analysis from running with insufficient NAICS data.

    Args:
        fiscal_naics_enriched_awards: DataFrame with NAICS enrichment

    Returns:
        AssetCheckResult with pass/fail status and metrics
    """
    # Get configuration
    config = get_config()
    min_coverage_rate = config.fiscal_analysis.quality_thresholds.get("naics_coverage_rate", 0.85)

    # Calculate coverage
    total_records = len(fiscal_naics_enriched_awards)
    covered_records = fiscal_naics_enriched_awards["fiscal_naics_code"].notna().sum()
    actual_coverage_rate = covered_records / total_records if total_records > 0 else 0.0

    # Determine if check passes
    passed = actual_coverage_rate >= min_coverage_rate

    # Set severity and description
    if passed:
        severity = AssetCheckSeverity.WARN
        description = f"✓ NAICS coverage check PASSED: {actual_coverage_rate:.1%} (threshold: {min_coverage_rate:.1%})"
    else:
        severity = AssetCheckSeverity.ERROR
        description = f"✗ NAICS coverage check FAILED: {actual_coverage_rate:.1%} is below threshold of {min_coverage_rate:.1%}"

    # Create metadata
    metadata = {
        "actual_coverage_rate": f"{actual_coverage_rate:.1%}",
        "threshold": f"{min_coverage_rate:.1%}",
        "total_records": total_records,
        "covered_records": covered_records,
        "uncovered_records": total_records - covered_records,
        "source_distribution": fiscal_naics_enriched_awards["fiscal_naics_source"].value_counts(dropna=False).to_dict(),
    }

    return AssetCheckResult(
        passed=passed, severity=severity, description=description, metadata=metadata
    )


@asset_check(
    asset="fiscal_naics_enriched_awards",
    description="NAICS confidence scores meet minimum quality threshold",
)
def fiscal_naics_quality_check(fiscal_naics_enriched_awards: pd.DataFrame) -> AssetCheckResult:
    """
    Asset check to ensure average NAICS confidence score meets quality threshold.

    This check validates that the enrichment quality is sufficient for fiscal analysis,
    ensuring the NAICS codes are reliable enough for economic modeling.

    Args:
        fiscal_naics_enriched_awards: DataFrame with NAICS enrichment

    Returns:
        AssetCheckResult with pass/fail status and metrics
    """
    # Get configuration
    config = get_config()
    min_confidence_threshold = getattr(
        config.fiscal_analysis.quality_thresholds,
        "naics_confidence_threshold",
        0.60  # Default fallback threshold
    )

    # Calculate average confidence
    confidence_scores = fiscal_naics_enriched_awards["fiscal_naics_confidence"].dropna()
    avg_confidence = confidence_scores.mean() if not confidence_scores.empty else 0.0

    # Determine if check passes
    passed = avg_confidence >= min_confidence_threshold

    # Set severity and description
    if passed:
        severity = AssetCheckSeverity.WARN
        description = f"✓ NAICS quality check PASSED: {avg_confidence:.3f} (threshold: {min_confidence_threshold:.3f})"
    else:
        severity = AssetCheckSeverity.ERROR
        description = f"✗ NAICS quality check FAILED: {avg_confidence:.3f} is below threshold of {min_confidence_threshold:.3f}"

    # Create metadata
    metadata = {
        "avg_confidence": round(avg_confidence, 3),
        "threshold": round(min_confidence_threshold, 3),
        "confidence_distribution": confidence_scores.describe().to_dict(),
        "source_distribution": fiscal_naics_enriched_awards["fiscal_naics_source"].value_counts(dropna=False).to_dict(),
    }

    return AssetCheckResult(
        passed=passed, severity=severity, description=description, metadata=metadata
    )


@asset(
    description="SBIR awards mapped to BEA Input-Output sectors",
    group_name="economic_modeling",
    compute_kind="pandas",
)
def bea_mapped_sbir_awards(
    context: AssetExecutionContext,
    fiscal_naics_enriched_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Map NAICS codes to BEA Input-Output sectors using hierarchical fallback strategy.
    """
    config = get_config()
    context.log.info("Starting BEA sector mapping", extra={"sbir_records": len(fiscal_naics_enriched_awards)})
    
    mapper = NAICSToBEAMapper()
    with performance_monitor.monitor_block("bea_sector_mapping"):
        enriched_df, mapping_stats = enrich_awards_with_bea_sectors(
            awards_df=fiscal_naics_enriched_awards,
            mapper=mapper,
        )
    
    context.log.info(
        "BEA sector mapping complete",
        extra={
            "mapping_coverage_rate": f"{mapping_stats.coverage_rate:.1%}",
            "avg_confidence": round(mapping_stats.avg_confidence, 3),
        },
    )
    
    metadata = {
        "num_input_records": len(fiscal_naics_enriched_awards),
        "num_output_records": len(enriched_df),
        "mapping_coverage_rate": f"{mapping_stats.coverage_rate:.1%}",
        "avg_confidence": round(mapping_stats.avg_confidence, 3),
    }
    
    return Output(value=enriched_df, metadata=metadata)


@asset_check(
    asset="bea_mapped_sbir_awards",
    description="Validate BEA sector mapping coverage and confidence",
)
def bea_mapping_quality_check(bea_mapped_sbir_awards: pd.DataFrame) -> AssetCheckResult:
    """Asset check to ensure BEA sector mapping coverage meets quality thresholds."""
    config = get_config()
    min_coverage_rate = config.fiscal_analysis.quality_thresholds.get("bea_sector_mapping_rate", 0.90)
    
    total_mappings = len(bea_mapped_sbir_awards)
    valid_mappings = bea_mapped_sbir_awards["bea_sector_code"].notna().sum()
    coverage_rate = valid_mappings / total_mappings if total_mappings > 0 else 0.0
    
    confidence_scores = bea_mapped_sbir_awards["bea_mapping_confidence"].dropna()
    avg_confidence = confidence_scores.mean() if not confidence_scores.empty else 0.0
    
    passed = coverage_rate >= min_coverage_rate and avg_confidence >= 0.70
    
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR
    description = (
        f"✓ BEA mapping PASSED: {coverage_rate:.1%} coverage, {avg_confidence:.3f} confidence"
        if passed
        else f"✗ BEA mapping FAILED: {coverage_rate:.1%} coverage (threshold {min_coverage_rate:.1%})"
    )
    
    metadata = {
        "coverage_rate": f"{coverage_rate:.1%}",
        "avg_confidence": round(avg_confidence, 3),
        "total_mappings": total_mappings,
    }
    
    return AssetCheckResult(passed=passed, severity=severity, description=description, metadata=metadata)
