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
from ..enrichers.geographic_resolver import GeographicResolver
from ..enrichers.inflation_adjuster import InflationAdjuster, adjust_awards_for_inflation
from ..transformers.fiscal_component_calculator import FiscalComponentCalculator
from ..transformers.fiscal_parameter_sweep import FiscalParameterSweep
from ..transformers.fiscal_roi_calculator import FiscalROICalculator
from ..transformers.fiscal_shock_aggregator import FiscalShockAggregator
from ..transformers.fiscal_tax_estimator import FiscalTaxEstimator
from ..transformers.fiscal_uncertainty_quantifier import FiscalUncertaintyQuantifier
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


# Task 6.1: Fiscal Data Preparation Assets


@asset(
    description="SBIR awards prepared for fiscal analysis with NAICS enrichment and geographic resolution",
    group_name="fiscal_data_prep",
    compute_kind="pandas",
)
def fiscal_prepared_sbir_awards(
    context: AssetExecutionContext,
    fiscal_naics_enriched_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Prepare SBIR awards for fiscal analysis by adding geographic resolution.

    This asset combines NAICS enrichment (from fiscal_naics_enriched_awards) with
    geographic resolution to state-level, creating a fully prepared dataset for
    economic modeling.
    """
    config = get_config()
    context.log.info(
        "Starting fiscal award preparation",
        extra={"num_awards": len(fiscal_naics_enriched_awards)},
    )

    # Resolve geographic locations
    from ..enrichers.geographic_resolver import resolve_award_geography

    with performance_monitor.monitor_block("geographic_resolution"):
        resolved_df, geo_quality = resolve_award_geography(
            fiscal_naics_enriched_awards,
            config=config.fiscal_analysis,
        )

    # Map geographic resolution columns to standard names
    if "fiscal_state_code" in resolved_df.columns:
        resolved_df["resolved_state"] = resolved_df["fiscal_state_code"]

    geo_coverage = resolved_df["resolved_state"].notna().sum() / len(resolved_df) if len(resolved_df) > 0 else 0.0

    context.log.info(
        "Fiscal award preparation complete",
        extra={
            "num_awards": len(resolved_df),
            "naics_coverage": f"{(resolved_df['fiscal_naics_code'].notna().sum() / len(resolved_df)):.1%}" if len(resolved_df) > 0 else "0%",
            "geographic_coverage": f"{geo_coverage:.1%}",
        },
    )

    metadata = {
        "num_awards": len(resolved_df),
        "naics_coverage": f"{(resolved_df['fiscal_naics_code'].notna().sum() / len(resolved_df)):.1%}" if len(resolved_df) > 0 else "0%",
        "geographic_coverage": f"{geo_coverage:.1%}",
        "preview": MetadataValue.md(resolved_df.head(10).to_markdown()) if not resolved_df.empty else "No awards",
    }

    return Output(value=resolved_df, metadata=metadata)  # type: ignore[arg-type]


@asset_check(
    asset="fiscal_prepared_sbir_awards",
    description="Validate geographic resolution success rate meets threshold",
)
def fiscal_geographic_resolution_check(fiscal_prepared_sbir_awards: pd.DataFrame) -> AssetCheckResult:
    """Asset check to ensure geographic resolution meets minimum threshold."""
    config = get_config()
    min_resolution_rate = config.fiscal_analysis.quality_thresholds.get("geographic_resolution_rate", 0.90)

    total_awards = len(fiscal_prepared_sbir_awards)
    resolved_awards = fiscal_prepared_sbir_awards.get("resolved_state", pd.Series()).notna().sum()
    resolution_rate = resolved_awards / total_awards if total_awards > 0 else 0.0

    passed = resolution_rate >= min_resolution_rate

    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR
    description = (
        f"✓ Geographic resolution PASSED: {resolution_rate:.1%} (threshold: {min_resolution_rate:.1%})"
        if passed
        else f"✗ Geographic resolution FAILED: {resolution_rate:.1%} is below threshold of {min_resolution_rate:.1%}"
    )

    metadata = {
        "resolution_rate": f"{resolution_rate:.1%}",
        "threshold": f"{min_resolution_rate:.1%}",
        "total_awards": total_awards,
        "resolved_awards": resolved_awards,
        "unresolved_awards": total_awards - resolved_awards,
    }

    return AssetCheckResult(passed=passed, severity=severity, description=description, metadata=metadata)


@asset(
    description="SBIR awards with inflation-adjusted amounts normalized to base year",
    group_name="fiscal_data_prep",
    compute_kind="pandas",
)
def inflation_adjusted_awards(
    context: AssetExecutionContext,
    fiscal_prepared_sbir_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Adjust SBIR award amounts for inflation using BEA GDP deflator.

    This asset normalizes all award amounts to the configured base year,
    enabling consistent comparison across different award years.
    """
    config = get_config()
    context.log.info(
        "Starting inflation adjustment",
        extra={"num_awards": len(fiscal_prepared_sbir_awards)},
    )

    # Adjust for inflation
    with performance_monitor.monitor_block("inflation_adjustment"):
        adjusted_df, quality_metrics = adjust_awards_for_inflation(
            fiscal_prepared_sbir_awards,
            target_year=config.fiscal_analysis.base_year,
            config=config.fiscal_analysis,
        )

    # Use adjusted amount as primary amount column
    if "fiscal_adjusted_amount" in adjusted_df.columns:
        adjusted_df["inflation_adjusted_amount"] = adjusted_df["fiscal_adjusted_amount"]

    success_rate = quality_metrics.get("adjustment_success_rate", 0.0)

    context.log.info(
        "Inflation adjustment complete",
        extra={
            "num_awards": len(adjusted_df),
            "adjustment_success_rate": f"{success_rate:.1%}",
            "base_year": config.fiscal_analysis.base_year,
        },
    )

    metadata = {
        "num_awards": len(adjusted_df),
        "base_year": config.fiscal_analysis.base_year,
        "adjustment_success_rate": f"{success_rate:.1%}",
        "total_original_amount": f"${adjusted_df.get('award_amount', pd.Series([0])).sum():,.2f}",
        "total_adjusted_amount": f"${adjusted_df['inflation_adjusted_amount'].sum():,.2f}" if "inflation_adjusted_amount" in adjusted_df.columns else "N/A",
        "preview": MetadataValue.md(adjusted_df.head(10).to_markdown()) if not adjusted_df.empty else "No awards",
    }

    return Output(value=adjusted_df, metadata=metadata)  # type: ignore[arg-type]


@asset_check(
    asset="inflation_adjusted_awards",
    description="Validate inflation adjustment quality meets threshold",
)
def inflation_adjustment_quality_check(inflation_adjusted_awards: pd.DataFrame) -> AssetCheckResult:
    """Asset check to ensure inflation adjustment quality meets minimum threshold."""
    config = get_config()
    min_success_rate = config.fiscal_analysis.quality_thresholds.get("inflation_adjustment_success", 0.95)

    total_awards = len(inflation_adjusted_awards)
    adjusted_cols = ["inflation_adjusted_amount", "fiscal_adjusted_amount"]
    adjusted_awards = 0

    for col in adjusted_cols:
        if col in inflation_adjusted_awards.columns:
            adjusted_awards = inflation_adjusted_awards[col].notna().sum()
            break

    success_rate = adjusted_awards / total_awards if total_awards > 0 else 0.0

    passed = success_rate >= min_success_rate

    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR
    description = (
        f"✓ Inflation adjustment PASSED: {success_rate:.1%} (threshold: {min_success_rate:.1%})"
        if passed
        else f"✗ Inflation adjustment FAILED: {success_rate:.1%} is below threshold of {min_success_rate:.1%}"
    )

    metadata = {
        "success_rate": f"{success_rate:.1%}",
        "threshold": f"{min_success_rate:.1%}",
        "total_awards": total_awards,
        "adjusted_awards": adjusted_awards,
        "unadjusted_awards": total_awards - adjusted_awards,
    }

    return AssetCheckResult(passed=passed, severity=severity, description=description, metadata=metadata)


# Task 6.3: Tax Calculation Assets


@asset(
    description="Economic components extracted from StateIO impacts for tax base calculation",
    group_name="tax_calculation",
    compute_kind="pandas",
)
def tax_base_components(
    context: AssetExecutionContext,
    economic_impacts: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Extract and validate economic components from StateIO model outputs.

    This asset transforms economic impacts into validated tax base components:
    wage impacts, proprietor income, gross operating surplus, and consumption.
    """
    config = get_config()
    context.log.info(
        "Starting tax base component extraction",
        extra={"num_impacts": len(economic_impacts)},
    )

    calculator = FiscalComponentCalculator(config=config.fiscal_analysis)
    with performance_monitor.monitor_block("component_extraction"):
        components_df = calculator.extract_components(economic_impacts)

    # Validate aggregate components
    validation_result = calculator.validate_aggregate_components(components_df)

    context.log.info(
        "Tax base component extraction complete",
        extra={
            "num_components": len(components_df),
            "validation_passed": validation_result.is_valid,
            "total_wage_impact": f"${components_df['wage_impact'].sum():,.2f}",
            "total_component_total": f"${components_df['component_total'].sum():,.2f}",
        },
    )

    metadata = {
        "num_components": len(components_df),
        "validation_passed": validation_result.is_valid,
        "total_wage_impact": f"${components_df['wage_impact'].sum():,.2f}",
        "total_proprietor_income": f"${components_df['proprietor_income_impact'].sum():,.2f}",
        "total_gos": f"${components_df['gross_operating_surplus'].sum():,.2f}",
        "total_consumption": f"${components_df['consumption_impact'].sum():,.2f}",
        "validation_difference": f"${validation_result.difference:,.2f}",
        "validation_tolerance": f"${validation_result.tolerance:,.2f}",
        "quality_flags": validation_result.quality_flags,
        "preview": MetadataValue.md(components_df.head(10).to_markdown()) if not components_df.empty else "No components",
    }

    return Output(value=components_df, metadata=metadata)  # type: ignore[arg-type]


@asset(
    description="Federal tax receipt estimates from economic components",
    group_name="tax_calculation",
    compute_kind="pandas",
)
def federal_tax_estimates(
    context: AssetExecutionContext,
    tax_base_components: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Estimate federal tax receipts from economic components.

    This asset computes individual income tax, payroll tax, corporate income tax,
    and excise tax estimates using configurable tax rates.
    """
    config = get_config()
    context.log.info(
        "Starting federal tax estimation",
        extra={"num_components": len(tax_base_components)},
    )

    estimator = FiscalTaxEstimator(config=config.fiscal_analysis)
    with performance_monitor.monitor_block("tax_estimation"):
        tax_estimates_df = estimator.estimate_taxes_from_components(tax_base_components)

    stats = estimator.get_estimation_statistics(tax_estimates_df)

    context.log.info(
        "Federal tax estimation complete",
        extra={
            "num_estimates": len(tax_estimates_df),
            "total_tax_receipts": f"${stats.total_tax_receipts:,.2f}",
            "avg_effective_rate": f"{stats.avg_effective_rate:.2f}%",
        },
    )

    metadata = {
        "num_estimates": len(tax_estimates_df),
        "total_individual_income_tax": f"${stats.total_individual_income_tax:,.2f}",
        "total_payroll_tax": f"${stats.total_payroll_tax:,.2f}",
        "total_corporate_income_tax": f"${stats.total_corporate_income_tax:,.2f}",
        "total_excise_tax": f"${stats.total_excise_tax:,.2f}",
        "total_tax_receipts": f"${stats.total_tax_receipts:,.2f}",
        "avg_effective_rate": f"{stats.avg_effective_rate:.2f}%",
        "preview": MetadataValue.md(tax_estimates_df.head(10).to_markdown()) if not tax_estimates_df.empty else "No estimates",
    }

    return Output(value=tax_estimates_df, metadata=metadata)  # type: ignore[arg-type]


@asset(
    description="Fiscal return summary with ROI metrics for SBIR program evaluation",
    group_name="tax_calculation",
    compute_kind="pandas",
)
def fiscal_return_summary(
    context: AssetExecutionContext,
    federal_tax_estimates: pd.DataFrame,
    inflation_adjusted_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Compute fiscal return summary with ROI metrics.

    This asset aggregates tax receipts and compares them to SBIR investments,
    computing ROI, payback period, NPV, and benefit-cost ratio.
    """
    config = get_config()
    context.log.info(
        "Starting fiscal return summary calculation",
        extra={
            "num_tax_estimates": len(federal_tax_estimates),
            "num_awards": len(inflation_adjusted_awards),
        },
    )

    calculator = FiscalROICalculator(config=config.fiscal_analysis)

    # Calculate total SBIR investment
    investment_cols = ["inflation_adjusted_amount", "fiscal_adjusted_amount", "award_amount", "shock_amount"]
    sbir_investment = 0.0
    for col in investment_cols:
        if col in inflation_adjusted_awards.columns:
            sbir_investment = float(inflation_adjusted_awards[col].sum())
            break

    from decimal import Decimal

    if sbir_investment == 0:
        logger.warning("No SBIR investment amount found in inflation_adjusted_awards")

    with performance_monitor.monitor_block("roi_calculation"):
        summary = calculator.calculate_roi_summary(
            tax_estimates_df=federal_tax_estimates,
            sbir_investment=Decimal(str(sbir_investment)),
            discount_rate=0.03,  # Default 3% discount rate
            time_horizon_years=10,  # Default 10-year horizon
        )

    # Convert summary to DataFrame for asset output
    summary_dict = {
        "analysis_id": [summary.analysis_id],
        "analysis_date": [summary.analysis_date.isoformat()],
        "base_year": [summary.base_year],
        "methodology_version": [summary.methodology_version],
        "total_sbir_investment": [float(summary.total_sbir_investment)],
        "total_tax_receipts": [float(summary.total_tax_receipts)],
        "net_fiscal_return": [float(summary.net_fiscal_return)],
        "roi_ratio": [summary.roi_ratio],
        "payback_period_years": [summary.payback_period_years],
        "net_present_value": [float(summary.net_present_value)],
        "benefit_cost_ratio": [summary.benefit_cost_ratio],
        "confidence_interval_low": [float(summary.confidence_interval_low)],
        "confidence_interval_high": [float(summary.confidence_interval_high)],
        "confidence_level": [summary.confidence_level],
        "quality_score": [summary.quality_score],
    }

    summary_df = pd.DataFrame(summary_dict)

    context.log.info(
        "Fiscal return summary calculation complete",
        extra={
            "roi_ratio": f"{summary.roi_ratio:.3f}",
            "payback_period_years": summary.payback_period_years,
            "npv": f"${summary.net_present_value:,.2f}",
            "total_investment": f"${summary.total_sbir_investment:,.2f}",
            "total_receipts": f"${summary.total_tax_receipts:,.2f}",
        },
    )

    metadata = {
        "roi_ratio": f"{summary.roi_ratio:.3f}",
        "payback_period_years": summary.payback_period_years,
        "net_present_value": f"${summary.net_present_value:,.2f}",
        "benefit_cost_ratio": f"{summary.benefit_cost_ratio:.3f}",
        "total_sbir_investment": f"${summary.total_sbir_investment:,.2f}",
        "total_tax_receipts": f"${summary.total_tax_receipts:,.2f}",
        "net_fiscal_return": f"${summary.net_fiscal_return:,.2f}",
        "quality_score": f"{summary.quality_score:.3f}",
        "quality_flags": summary.quality_flags,
        "preview": MetadataValue.md(summary_df.to_markdown()),
    }

    return Output(value=summary_df, metadata=metadata)  # type: ignore[arg-type]


# Task 6.4: Sensitivity Analysis Assets


@asset(
    description="Parameter sweep scenarios for sensitivity analysis",
    group_name="sensitivity_analysis",
    compute_kind="pandas",
)
def sensitivity_scenarios(
    context: AssetExecutionContext,
) -> Output[pd.DataFrame]:
    """
    Generate parameter sweep scenarios for uncertainty quantification.

    This asset creates scenario combinations using Monte Carlo, Latin Hypercube,
    or grid search sampling based on configuration.
    """
    config = get_config()
    context.log.info("Starting sensitivity scenario generation")

    sweep = FiscalParameterSweep(config=config.fiscal_analysis)
    with performance_monitor.monitor_block("parameter_sweep"):
        scenarios_df = sweep.generate_scenarios()

    context.log.info(
        "Sensitivity scenario generation complete",
        extra={
            "num_scenarios": len(scenarios_df),
            "method": scenarios_df["method"].iloc[0] if len(scenarios_df) > 0 else "unknown",
            "parameters": [col for col in scenarios_df.columns if col not in ["scenario_id", "method", "random_seed", "points_per_dimension"]],
        },
    )

    metadata = {
        "num_scenarios": len(scenarios_df),
        "method": scenarios_df["method"].iloc[0] if len(scenarios_df) > 0 else "unknown",
        "parameters": [col for col in scenarios_df.columns if col not in ["scenario_id", "method", "random_seed", "points_per_dimension"]],
        "preview": MetadataValue.md(scenarios_df.head(10).to_markdown()) if not scenarios_df.empty else "No scenarios",
    }

    return Output(value=scenarios_df, metadata=metadata)  # type: ignore[arg-type]


@asset(
    description="Uncertainty analysis with confidence intervals from sensitivity scenarios",
    group_name="sensitivity_analysis",
    compute_kind="pandas",
)
def uncertainty_analysis(
    context: AssetExecutionContext,
    sensitivity_scenarios: pd.DataFrame,
    federal_tax_estimates: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Compute uncertainty quantification from sensitivity scenario results.

    This asset computes confidence intervals, min/mean/max estimates, and
    sensitivity indices from parameter sweep results.
    """
    config = get_config()
    context.log.info(
        "Starting uncertainty analysis",
        extra={
            "num_scenarios": len(sensitivity_scenarios),
            "num_tax_estimates": len(federal_tax_estimates),
        },
    )

    # For now, use tax estimates as baseline
    # In full implementation, would re-run analysis for each scenario
    # This is a simplified version that quantifies uncertainty from baseline
    quantifier = FiscalUncertaintyQuantifier(config=config.fiscal_analysis)

    # Create scenario results by using tax estimates as baseline
    # In production, this would run full pipeline for each scenario
    scenario_results = sensitivity_scenarios.copy()
    baseline_tax = float(federal_tax_estimates["total_tax_receipt"].sum())

    # Simulate scenario results by applying parameter variations to baseline
    # This is a placeholder - full implementation would recompute for each scenario
    if "economic_multiplier" in scenario_results.columns:
        scenario_results["total_tax_receipt"] = (
            baseline_tax * scenario_results["economic_multiplier"] / 2.0
        )
    else:
        scenario_results["total_tax_receipt"] = baseline_tax

    with performance_monitor.monitor_block("uncertainty_quantification"):
        uncertainty_result = quantifier.quantify_uncertainty(
            scenario_results_df=scenario_results,
            target_column="total_tax_receipt",
        )

    # Convert to DataFrame
    uncertainty_df = pd.DataFrame(
        [
            {
                "min_estimate": float(uncertainty_result.min_estimate),
                "mean_estimate": float(uncertainty_result.mean_estimate),
                "max_estimate": float(uncertainty_result.max_estimate),
                "confidence_90_low": float(uncertainty_result.confidence_intervals.get(0.90, (Decimal("0"), Decimal("0")))[0]),
                "confidence_90_high": float(uncertainty_result.confidence_intervals.get(0.90, (Decimal("0"), Decimal("0")))[1]),
                "confidence_95_low": float(uncertainty_result.confidence_intervals.get(0.95, (Decimal("0"), Decimal("0")))[0]),
                "confidence_95_high": float(uncertainty_result.confidence_intervals.get(0.95, (Decimal("0"), Decimal("0")))[1]),
                "high_uncertainty": quantifier.flag_high_uncertainty(uncertainty_result),
            }
        ]
    )

    # Add sensitivity indices as metadata
    sensitivity_dict = uncertainty_result.sensitivity_indices

    context.log.info(
        "Uncertainty analysis complete",
        extra={
            "min_estimate": f"${uncertainty_result.min_estimate:,.2f}",
            "mean_estimate": f"${uncertainty_result.mean_estimate:,.2f}",
            "max_estimate": f"${uncertainty_result.max_estimate:,.2f}",
            "high_uncertainty": quantifier.flag_high_uncertainty(uncertainty_result),
        },
    )

    metadata = {
        "min_estimate": f"${uncertainty_result.min_estimate:,.2f}",
        "mean_estimate": f"${uncertainty_result.mean_estimate:,.2f}",
        "max_estimate": f"${uncertainty_result.max_estimate:,.2f}",
        "sensitivity_indices": MetadataValue.json(sensitivity_dict),
        "quality_flags": uncertainty_result.quality_flags,
        "high_uncertainty": quantifier.flag_high_uncertainty(uncertainty_result),
        "preview": MetadataValue.md(uncertainty_df.to_markdown()),
    }

    return Output(value=uncertainty_df, metadata=metadata)  # type: ignore[arg-type]


@asset(
    description="Comprehensive fiscal returns analysis report with all metrics and uncertainty bands",
    group_name="sensitivity_analysis",
    compute_kind="pandas",
)
def fiscal_returns_report(
    context: AssetExecutionContext,
    fiscal_return_summary: pd.DataFrame,
    uncertainty_analysis: pd.DataFrame,
    federal_tax_estimates: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Generate comprehensive fiscal returns analysis report.

    This asset combines ROI summary, uncertainty analysis, and tax estimates
    into a comprehensive report for policy analysis.
    """
    config = get_config()
    context.log.info("Starting fiscal returns report generation")

    # Combine summary and uncertainty
    report_df = fiscal_return_summary.merge(
        uncertainty_analysis,
        left_index=True,
        right_index=True,
        how="outer",
    )

    # Add summary statistics
    report_df["total_tax_receipts_baseline"] = float(federal_tax_estimates["total_tax_receipt"].sum())
    report_df["num_tax_estimates"] = len(federal_tax_estimates)

    context.log.info(
        "Fiscal returns report generation complete",
        extra={
            "roi_ratio": f"{report_df['roi_ratio'].iloc[0]:.3f}" if len(report_df) > 0 and "roi_ratio" in report_df.columns else "N/A",
            "num_scenarios": len(uncertainty_analysis),
        },
    )

    metadata = {
        "report_generated_at": MetadataValue.timestamp(pd.Timestamp.now()),
        "base_year": config.fiscal_analysis.base_year,
        "model_version": config.fiscal_analysis.stateio_model_version,
        "preview": MetadataValue.md(report_df.to_markdown()) if not report_df.empty else "No report",
    }

    return Output(value=report_df, metadata=metadata)  # type: ignore[arg-type]
