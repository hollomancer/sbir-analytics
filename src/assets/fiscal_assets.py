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
from ..transformers.fiscal_shock_aggregator import FiscalShockAggregator
from ..transformers.r_stateio_adapter import RStateIOAdapter
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
    
    return Output(value=enriched_df, metadata=metadata)  # type: ignore[arg-type]


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


@asset(
    description="Economic shocks aggregated by state, BEA sector, and fiscal year for StateIO model input",
    group_name="economic_modeling",
    compute_kind="pandas",
)
def economic_shocks(
    context: AssetExecutionContext,
    bea_mapped_sbir_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Aggregate SBIR awards into state-by-sector-by-fiscal-year economic shocks.

    This asset maintains award-to-shock traceability for audit purposes and supports
    chunked processing for large datasets. Each shock represents aggregated SBIR spending
    in a specific state, BEA sector, and fiscal year combination.
    """
    config = get_config()
    context.log.info(
        "Starting economic shock aggregation",
        extra={"bea_mapped_records": len(bea_mapped_sbir_awards)},
    )

    # Get chunk size from config
    chunk_size = config.fiscal_analysis.performance.get("chunk_size", 10000)

    # Aggregate shocks
    aggregator = FiscalShockAggregator(config=config)
    with performance_monitor.monitor_block("economic_shock_aggregation"):
        shocks_df = aggregator.aggregate_shocks_to_dataframe(
            awards_df=bea_mapped_sbir_awards,
            chunk_size=chunk_size if len(bea_mapped_sbir_awards) > chunk_size else None,
        )

    # Get statistics
    shocks_list = aggregator.aggregate_shocks(
        awards_df=bea_mapped_sbir_awards,
        chunk_size=chunk_size if len(bea_mapped_sbir_awards) > chunk_size else None,
    )
    stats = aggregator.get_aggregation_statistics(shocks_list)

    context.log.info(
        "Economic shock aggregation complete",
        extra={
            "num_shocks": len(shocks_df),
            "total_awards_aggregated": stats.total_awards_aggregated,
            "unique_states": stats.unique_states,
            "unique_sectors": stats.unique_sectors,
            "unique_fiscal_years": stats.unique_fiscal_years,
            "total_shock_amount": f"${stats.total_shock_amount:,.2f}",
            "avg_confidence": round(stats.avg_confidence, 3),
        },
    )

    # Create metadata
    metadata = {
        "num_shocks": len(shocks_df),
        "total_awards_aggregated": stats.total_awards_aggregated,
        "unique_states": stats.unique_states,
        "unique_sectors": stats.unique_sectors,
        "unique_fiscal_years": stats.unique_fiscal_years,
        "fiscal_year_range": (
            f"{stats.unique_fiscal_years}" if stats.unique_fiscal_years > 0 else "N/A"
        ),
        "total_shock_amount": f"${stats.total_shock_amount:,.2f}",
        "avg_confidence": round(stats.avg_confidence, 3),
        "naics_coverage_rate": f"{stats.naics_coverage_rate:.1%}",
        "geographic_resolution_rate": f"{stats.geographic_resolution_rate:.1%}",
        "awards_per_shock_avg": round(stats.awards_per_shock_avg, 2),
        "preview": MetadataValue.md(shocks_df.head(10).to_markdown()) if not shocks_df.empty else "No shocks",
    }

    return Output(value=shocks_df, metadata=metadata)  # type: ignore[arg-type]


@asset_check(
    asset="economic_shocks",
    description="Validate economic shock aggregation coverage and quality",
)
def economic_shocks_quality_check(economic_shocks: pd.DataFrame) -> AssetCheckResult:
    """Asset check to ensure economic shock aggregation meets quality thresholds."""
    config = get_config()

    if economic_shocks.empty:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description="✗ Economic shocks aggregation FAILED: No shocks generated",
            metadata={"num_shocks": 0},
        )

    # Check minimum shock count
    min_shocks = 10  # Reasonable minimum for analysis
    num_shocks = len(economic_shocks)
    passed_min_count = num_shocks >= min_shocks

    # Check coverage rates
    naics_rates = economic_shocks["naics_coverage_rate"].dropna()
    geo_rates = economic_shocks["geographic_resolution_rate"].dropna()

    avg_naics_coverage = naics_rates.mean() if not naics_rates.empty else 0.0
    avg_geo_coverage = geo_rates.mean() if not geo_rates.empty else 0.0

    # Check confidence scores
    confidences = economic_shocks["confidence"].dropna()
    avg_confidence = confidences.mean() if not confidences.empty else 0.0

    # Get thresholds
    quality_thresholds = config.fiscal_analysis.quality_thresholds
    min_naics_coverage = quality_thresholds.get("naics_coverage_rate", 0.85)
    min_geo_coverage = quality_thresholds.get("geographic_resolution_rate", 0.90)

    # Determine if checks pass
    passed = (
        passed_min_count
        and avg_naics_coverage >= min_naics_coverage * 0.8  # Allow some tolerance
        and avg_geo_coverage >= min_geo_coverage * 0.8
        and avg_confidence >= 0.60
    )

    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR
    description = (
        f"✓ Economic shocks aggregation PASSED: {num_shocks} shocks, "
        f"{avg_naics_coverage:.1%} NAICS coverage, {avg_geo_coverage:.1%} geo coverage"
        if passed
        else f"✗ Economic shocks aggregation FAILED: Quality metrics below thresholds"
    )

    metadata = {
        "num_shocks": num_shocks,
        "avg_naics_coverage": f"{avg_naics_coverage:.1%}",
        "avg_geo_coverage": f"{avg_geo_coverage:.1%}",
        "avg_confidence": round(avg_confidence, 3),
        "total_shock_amount": f"${economic_shocks['shock_amount'].sum():,.2f}",
    }

    return AssetCheckResult(passed=passed, severity=severity, description=description, metadata=metadata)


@asset(
    description="Economic impacts computed from shocks using StateIO model",
    group_name="economic_modeling",
    compute_kind="r",
)
def economic_impacts(
    context: AssetExecutionContext,
    economic_shocks: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Compute economic impacts from spending shocks using StateIO input-output model.

    This asset uses the RStateIOAdapter to call EPA's StateIO R package via rpy2
    to compute multiplier effects and economic impact components from SBIR spending.
    """
    config = get_config()
    context.log.info(
        "Starting economic impact computation",
        extra={"num_shocks": len(economic_shocks)},
    )

    # Check if R adapter is available
    try:
        adapter = RStateIOAdapter(config=config.fiscal_analysis)
        if not adapter.is_available():
            context.log.warning(
                "R StateIO adapter not available. This may require: "
                "1. Install rpy2: poetry install --extras r"
                "2. Install StateIO R package in R: install.packages('stateior')"
            )
            # Return placeholder DataFrame with same structure
            return _create_placeholder_impacts(economic_shocks, context)
    except ImportError as e:
        context.log.warning(f"R StateIO adapter not available: {e}")
        return _create_placeholder_impacts(economic_shocks, context)

    # Prepare shocks DataFrame for model input
    shocks_input = economic_shocks[
        ["state", "bea_sector", "fiscal_year", "shock_amount"]
    ].copy()

    # Compute impacts with performance monitoring
    with performance_monitor.monitor_block("economic_impact_computation"):
        try:
            impacts_df = adapter.compute_impacts(shocks_input)
        except Exception as e:
            context.log.error(f"Failed to compute economic impacts: {e}")
            return _create_placeholder_impacts(economic_shocks, context)

    # Merge back with shock metadata
    result_df = economic_shocks.merge(
        impacts_df,
        on=["state", "bea_sector", "fiscal_year"],
        how="left",
        suffixes=("_shock", "_impact"),
    )

    # Fill any missing impacts with zeros
    impact_cols = [
        "wage_impact",
        "proprietor_income_impact",
        "gross_operating_surplus",
        "consumption_impact",
        "tax_impact",
        "production_impact",
    ]
    for col in impact_cols:
        if col not in result_df.columns:
            result_df[col] = 0.0
        result_df[col] = result_df[col].fillna(0.0)

    context.log.info(
        "Economic impact computation complete",
        extra={
            "num_impacts": len(result_df),
            "total_wage_impact": f"${result_df['wage_impact'].sum():,.2f}",
            "total_production_impact": f"${result_df['production_impact'].sum():,.2f}",
            "model_version": adapter.get_model_version(),
        },
    )

    # Create metadata
    metadata = {
        "num_impacts": len(result_df),
        "model_version": adapter.get_model_version(),
        "total_wage_impact": f"${result_df['wage_impact'].sum():,.2f}",
        "total_proprietor_income_impact": f"${result_df['proprietor_income_impact'].sum():,.2f}",
        "total_gross_operating_surplus": f"${result_df['gross_operating_surplus'].sum():,.2f}",
        "total_production_impact": f"${result_df['production_impact'].sum():,.2f}",
        "preview": MetadataValue.md(result_df.head(10).to_markdown()) if not result_df.empty else "No impacts",
    }

    return Output(value=result_df, metadata=metadata)  # type: ignore[arg-type]


def _create_placeholder_impacts(
    shocks_df: pd.DataFrame, context: AssetExecutionContext
) -> Output[pd.DataFrame]:
    """Create placeholder impacts DataFrame when R adapter is unavailable.

    Args:
        shocks_df: Economic shocks DataFrame
        context: Dagster context

    Returns:
        Output with placeholder impacts DataFrame
    """
    context.log.warning("Creating placeholder impacts (R StateIO adapter unavailable)")

    placeholder_df = shocks_df.copy()
    # Add placeholder impact columns with zero values
    placeholder_df["wage_impact"] = 0.0
    placeholder_df["proprietor_income_impact"] = 0.0
    placeholder_df["gross_operating_surplus"] = 0.0
    placeholder_df["consumption_impact"] = 0.0
    placeholder_df["tax_impact"] = 0.0
    placeholder_df["production_impact"] = 0.0
    placeholder_df["model_version"] = "placeholder"
    placeholder_df["confidence"] = 0.0
    placeholder_df["quality_flags"] = "r_adapter_unavailable"

    metadata = {
        "num_impacts": len(placeholder_df),
        "model_version": "placeholder",
        "warning": "R StateIO adapter unavailable - placeholder impacts generated",
    }

    return Output(value=placeholder_df, metadata=metadata)  # type: ignore[arg-type]


@asset_check(
    asset="economic_impacts",
    description="Validate economic impacts computation quality",
)
def economic_impacts_quality_check(economic_impacts: pd.DataFrame) -> AssetCheckResult:
    """Asset check to ensure economic impacts meet quality thresholds."""
    if economic_impacts.empty:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description="✗ Economic impacts FAILED: No impacts generated",
            metadata={"num_impacts": 0},
        )

    # Check if using placeholder model
    is_placeholder = economic_impacts["model_version"].iloc[0] == "placeholder" if len(economic_impacts) > 0 else False
    if is_placeholder:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description="✗ Economic impacts FAILED: Using placeholder model (R adapter unavailable)",
            metadata={"model_version": "placeholder"},
        )

    # Check impact values are reasonable
    impact_cols = [
        "wage_impact",
        "proprietor_income_impact",
        "gross_operating_surplus",
        "consumption_impact",
        "tax_impact",
        "production_impact",
    ]

    checks_passed = True
    issues = []

    for col in impact_cols:
        if col not in economic_impacts.columns:
            issues.append(f"Missing column: {col}")
            checks_passed = False
            continue

        # Check for negative values (shouldn't occur for economic impacts)
        negative_count = (economic_impacts[col] < 0).sum()
        if negative_count > 0:
            issues.append(f"{col}: {negative_count} negative values")
            checks_passed = False

        # Check for NaN values
        nan_count = economic_impacts[col].isna().sum()
        if nan_count > 0:
            issues.append(f"{col}: {nan_count} NaN values")
            checks_passed = False

    severity = AssetCheckSeverity.WARN if checks_passed else AssetCheckSeverity.ERROR
    description = (
        f"✓ Economic impacts PASSED: {len(economic_impacts)} impacts computed"
        if checks_passed
        else f"✗ Economic impacts FAILED: {', '.join(issues)}"
    )

    metadata = {
        "num_impacts": len(economic_impacts),
        "model_version": economic_impacts["model_version"].iloc[0] if len(economic_impacts) > 0 else "unknown",
        "issues": issues if issues else [],
    }

    return AssetCheckResult(passed=checks_passed, severity=severity, description=description, metadata=metadata)
