"""Dagster assets for fiscal analysis pipeline."""

from decimal import Decimal

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

from sbir_etl.config.loader import get_config
from sbir_etl.enrichers.fiscal_bea_mapper import NAICSToBEAMapper, enrich_awards_with_bea_sectors
from sbir_etl.enrichers.inflation_adjuster import adjust_awards_for_inflation
from sbir_etl.enrichers.naics import enrich_sbir_awards_with_fiscal_naics
from sbir_etl.transformers.bea_io_adapter import BEAIOAdapter
from sbir_etl.transformers.fiscal import (
    FiscalComponentCalculator,
    FiscalParameterSweep,
    FiscalROICalculator,
    FiscalShockAggregator,
    FiscalTaxEstimator,
    FiscalUncertaintyQuantifier,
)
from sbir_etl.utils.monitoring import performance_monitor


# ---------------------------------------------------------------------------
# Metadata helpers (shared across many assets / checks)
# ---------------------------------------------------------------------------


def _preview(df: pd.DataFrame, *, empty: str = "No data", head: int | None = 10) -> object:
    """Return a Markdown preview of `df`, or `empty` placeholder when empty."""
    if df.empty:
        return empty
    table = df.head(head) if head else df
    return MetadataValue.md(table.to_markdown())


def _threshold_check(
    *,
    label: str,
    actual: float,
    threshold: float,
    metadata: dict,
    use_percent: bool = True,
) -> AssetCheckResult:
    """Build an AssetCheckResult for a 'rate ≥ threshold' style check."""
    passed = bool(actual >= threshold)
    fmt = (lambda v: f"{v:.1%}") if use_percent else (lambda v: f"{v:.3f}")
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR
    sign = "✓" if passed else "✗"
    verb = "PASSED" if passed else "FAILED"
    description = (
        f"{sign} {label} {verb}: {fmt(actual)}"
        + (f" ({'threshold' if passed else 'below threshold of'}: {fmt(threshold)})")
    )
    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=description,
        metadata=metadata,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# NAICS enrichment
# ---------------------------------------------------------------------------


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
    """Enrich SBIR awards with NAICS codes via hierarchical fallback (original →
    USAspending matches → fresh recipient lookup → agency default → sector default).
    """
    get_config()
    context.log.info(
        "Starting NAICS enrichment for fiscal analysis",
        extra={
            "sbir_records": len(enriched_sbir_awards),
            "usaspending_recipients_available": raw_usaspending_recipients is not None,
        },
    )

    with performance_monitor.monitor_block("fiscal_naics_enrichment"):
        enriched_df, quality_metrics = enrich_sbir_awards_with_fiscal_naics(
            awards_df=enriched_sbir_awards,
            usaspending_df=raw_usaspending_recipients,
        )

    total = len(enriched_df)
    covered = enriched_df["fiscal_naics_code"].notna().sum()
    coverage_rate = covered / total if total > 0 else 0
    source_counts = enriched_df["fiscal_naics_source"].value_counts(dropna=False).to_dict()
    confidence = enriched_df["fiscal_naics_confidence"].dropna().describe()
    avg_conf = confidence.get("mean", 0.0)

    context.log.info(
        "NAICS enrichment complete",
        extra={
            "total_awards": total,
            "naics_coverage": covered,
            "coverage_rate": f"{coverage_rate:.1%}",
            "source_distribution": source_counts,
            "avg_confidence": round(avg_conf, 3),
        },
    )

    perf = performance_monitor.get_metrics_summary().get("fiscal_naics_enrichment", {})
    duration = perf.get("total_duration", 0.0)
    metadata = {
        "num_records": int(total),
        "naics_coverage": f"{coverage_rate:.1%}",
        "naics_coverage_count": int(covered),
        "source_distribution": MetadataValue.json(source_counts),
        "confidence_stats": MetadataValue.json(
            {
                "mean": round(float(avg_conf), 3),
                "min": round(float(confidence.get("min", 0.0)), 3),
                "max": round(float(confidence.get("max", 1.0)), 3),
                "std": round(float(confidence.get("std", 0.0)), 3),
            }
        ),
        "preview": _preview(enriched_df),
        "performance_duration_seconds": round(duration, 2),
        "performance_records_per_second": round(total / duration if duration > 0 else 0, 2),
        "performance_peak_memory_mb": round(perf.get("max_peak_memory_mb", 0.0), 2),
        "quality_coverage_threshold": f"{quality_metrics['naics_coverage_threshold']:.1%}",
        "quality_coverage_meets_threshold": bool(quality_metrics["coverage_meets_threshold"]),
        "quality_avg_confidence": round(float(avg_conf), 3),
    }
    return Output(value=enriched_df, metadata=metadata)


@asset_check(
    asset="fiscal_naics_enriched_awards",
    description="NAICS coverage rate meets minimum threshold",
)
def fiscal_naics_coverage_check(fiscal_naics_enriched_awards: pd.DataFrame) -> AssetCheckResult:
    """Fail if NAICS coverage falls below threshold (blocks downstream fiscal analysis)."""
    threshold = get_config().fiscal_analysis.quality_thresholds.get("naics_coverage_rate", 0.85)

    total = len(fiscal_naics_enriched_awards)
    if total == 0 or "fiscal_naics_code" not in fiscal_naics_enriched_awards.columns:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            metadata={
                "total_records": 0,
                "covered_records": 0,
                "actual_coverage_rate": 0.0,
                "min_coverage_rate": threshold,
                "message": "Empty DataFrame or missing fiscal_naics_code column",
            },
        )

    covered = fiscal_naics_enriched_awards["fiscal_naics_code"].notna().sum()
    rate = covered / total
    return _threshold_check(
        label="NAICS coverage check",
        actual=rate,
        threshold=threshold,
        metadata={
            "actual_coverage_rate": f"{rate:.1%}",
            "threshold": f"{threshold:.1%}",
            "total_records": int(total),
            "covered_records": int(covered),
            "uncovered_records": int(total - covered),
            "source_distribution": fiscal_naics_enriched_awards["fiscal_naics_source"]
            .value_counts(dropna=False)
            .to_dict(),
        },
    )


@asset_check(
    asset="fiscal_naics_enriched_awards",
    description="NAICS confidence scores meet minimum quality threshold",
)
def fiscal_naics_quality_check(fiscal_naics_enriched_awards: pd.DataFrame) -> AssetCheckResult:
    """Validate that average NAICS confidence is high enough for economic modeling."""
    threshold = getattr(
        get_config().fiscal_analysis.quality_thresholds,
        "naics_confidence_threshold",
        0.60,
    )
    scores = fiscal_naics_enriched_awards["fiscal_naics_confidence"].dropna()
    avg = scores.mean() if not scores.empty else 0.0
    return _threshold_check(
        label="NAICS quality check",
        actual=avg,
        threshold=threshold,
        use_percent=False,
        metadata={
            "avg_confidence": round(avg, 3),
            "threshold": round(threshold, 3),
            "confidence_distribution": scores.describe().to_dict(),
            "source_distribution": fiscal_naics_enriched_awards["fiscal_naics_source"]
            .value_counts(dropna=False)
            .to_dict(),
        },
    )


# ---------------------------------------------------------------------------
# BEA sector mapping
# ---------------------------------------------------------------------------


@asset(
    description="SBIR awards mapped to BEA Input-Output sectors",
    group_name="economic_modeling",
    compute_kind="pandas",
)
def bea_mapped_sbir_awards(
    context: AssetExecutionContext,
    fiscal_naics_enriched_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """Map NAICS codes to BEA Input-Output sectors via hierarchical fallback."""
    get_config()
    context.log.info(
        "Starting BEA sector mapping", extra={"sbir_records": len(fiscal_naics_enriched_awards)}
    )

    with performance_monitor.monitor_block("bea_sector_mapping"):
        enriched_df, stats = enrich_awards_with_bea_sectors(
            awards_df=fiscal_naics_enriched_awards,
            mapper=NAICSToBEAMapper(),
        )

    context.log.info(
        "BEA sector mapping complete",
        extra={
            "mapping_coverage_rate": f"{stats.coverage_rate:.1%}",
            "avg_confidence": round(stats.avg_confidence, 3),
        },
    )

    metadata = {
        "num_input_records": len(fiscal_naics_enriched_awards),
        "num_output_records": len(enriched_df),
        "mapping_coverage_rate": f"{stats.coverage_rate:.1%}",
        "avg_confidence": round(stats.avg_confidence, 3),
    }
    return Output(value=enriched_df, metadata=metadata)  # type: ignore[arg-type]


@asset_check(
    asset="bea_mapped_sbir_awards",
    description="Validate BEA sector mapping coverage and confidence",
)
def bea_mapping_quality_check(bea_mapped_sbir_awards: pd.DataFrame) -> AssetCheckResult:
    """Asset check: BEA sector mapping coverage ≥ threshold AND confidence ≥ 0.70."""
    threshold = get_config().fiscal_analysis.quality_thresholds.get(
        "bea_sector_mapping_rate", 0.90
    )
    total = len(bea_mapped_sbir_awards)
    if total == 0 or "bea_sector_code" not in bea_mapped_sbir_awards.columns:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            metadata={
                "total_mappings": 0,
                "valid_mappings": 0,
                "coverage_rate": 0.0,
                "avg_confidence": 0.0,
                "min_coverage_rate": threshold,
            },
            description="Empty DataFrame or missing bea_sector_code column",
        )

    valid = bea_mapped_sbir_awards["bea_sector_code"].notna().sum()
    coverage = valid / total
    confidences = bea_mapped_sbir_awards["bea_mapping_confidence"].dropna()
    avg_conf = confidences.mean() if not confidences.empty else 0.0

    passed = bool(coverage >= threshold and avg_conf >= 0.70)
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR
    description = (
        f"✓ BEA mapping PASSED: {coverage:.1%} coverage, {avg_conf:.3f} confidence"
        if passed
        else f"✗ BEA mapping FAILED: {coverage:.1%} coverage (threshold {threshold:.1%})"
    )
    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=description,
        metadata={
            "coverage_rate": f"{coverage:.1%}",
            "avg_confidence": round(avg_conf, 3),
            "total_mappings": total,
        },  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Economic shocks
# ---------------------------------------------------------------------------


@asset(
    description="Economic shocks aggregated by state, BEA sector, and fiscal year for BEA I-O model input",
    group_name="economic_modeling",
    compute_kind="pandas",
)
def economic_shocks(
    context: AssetExecutionContext,
    bea_mapped_sbir_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """Aggregate SBIR awards into state × sector × fiscal-year shocks."""
    config = get_config()
    context.log.info(
        "Starting economic shock aggregation",
        extra={"bea_mapped_records": len(bea_mapped_sbir_awards)},
    )

    chunk_size = config.fiscal_analysis.performance.get("chunk_size", 10000)
    chunk_arg = chunk_size if len(bea_mapped_sbir_awards) > chunk_size else None
    aggregator = FiscalShockAggregator(config=config)

    with performance_monitor.monitor_block("economic_shock_aggregation"):
        shocks_df = aggregator.aggregate_shocks_to_dataframe(
            awards_df=bea_mapped_sbir_awards,
            chunk_size=chunk_arg,
        )

    shocks_list = aggregator.aggregate_shocks(
        awards_df=bea_mapped_sbir_awards, chunk_size=chunk_arg
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
        "preview": _preview(shocks_df, empty="No shocks"),
    }
    return Output(value=shocks_df, metadata=metadata)  # type: ignore[arg-type]


@asset_check(
    asset="economic_shocks",
    description="Validate economic shock aggregation coverage and quality",
)
def economic_shocks_quality_check(economic_shocks: pd.DataFrame) -> AssetCheckResult:
    """Check shock count and NAICS / geographic coverage on the aggregated shocks."""
    if economic_shocks.empty:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description="✗ Economic shocks aggregation FAILED: No shocks generated",
            metadata={"num_shocks": 0},
        )

    num = len(economic_shocks)
    naics = economic_shocks["naics_coverage_rate"].dropna().mean() or 0.0
    geo = economic_shocks["geographic_resolution_rate"].dropna().mean() or 0.0
    confidence = economic_shocks["confidence"].dropna().mean() or 0.0

    thresholds = get_config().fiscal_analysis.quality_thresholds
    min_naics = thresholds.get("naics_coverage_rate", 0.85)
    min_geo = thresholds.get("geographic_resolution_rate", 0.90)

    # Allow 20% tolerance on coverage at the shock-aggregate stage.
    passed = bool(
        num >= 10
        and naics >= min_naics * 0.8
        and geo >= min_geo * 0.8
        and confidence >= 0.60
    )
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR
    description = (
        f"✓ Economic shocks aggregation PASSED: {num} shocks, "
        f"{naics:.1%} NAICS coverage, {geo:.1%} geo coverage"
        if passed
        else "✗ Economic shocks aggregation FAILED: Quality metrics below thresholds"
    )
    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=description,
        metadata={
            "num_shocks": num,
            "avg_naics_coverage": f"{naics:.1%}",
            "avg_geo_coverage": f"{geo:.1%}",
            "avg_confidence": round(confidence, 3),
            "total_shock_amount": f"${economic_shocks['shock_amount'].sum():,.2f}",
        },  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Economic impacts (BEA I-O)
# ---------------------------------------------------------------------------

_IMPACT_COLS = (
    "wage_impact",
    "proprietor_income_impact",
    "gross_operating_surplus",
    "consumption_impact",
    "tax_impact",
    "production_impact",
)


@asset(
    description="Economic impacts computed from shocks using BEA I-O model",
    group_name="economic_modeling",
    compute_kind="r",
)
def economic_impacts(
    context: AssetExecutionContext,
    economic_shocks: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """Run BEA I-O multipliers on the aggregated shocks; placeholder when BEA unavailable."""
    config = get_config()
    context.log.info("Starting economic impact computation", extra={"num_shocks": len(economic_shocks)})

    try:
        adapter = BEAIOAdapter(config=config.fiscal_analysis)
        if not adapter.is_available():
            context.log.warning(
                "BEA I-O adapter not available. Set BEA_API_KEY env var.\n"
                "Register at https://apps.bea.gov/API/signup/"
            )
            return _create_placeholder_impacts(economic_shocks, context)
    except Exception as e:
        context.log.warning(f"BEA I-O adapter not available: {e}")
        return _create_placeholder_impacts(economic_shocks, context)

    shocks_input = economic_shocks[["state", "bea_sector", "fiscal_year", "shock_amount"]].copy()
    with performance_monitor.monitor_block("economic_impact_computation"):
        try:
            impacts_df = adapter.compute_impacts(shocks_input)
        except Exception as e:
            context.log.error(f"Failed to compute economic impacts: {e}")
            return _create_placeholder_impacts(economic_shocks, context)

    result = economic_shocks.merge(
        impacts_df,
        on=["state", "bea_sector", "fiscal_year"],
        how="left",
        suffixes=("_shock", "_impact"),
    )
    for col in _IMPACT_COLS:
        if col not in result.columns:
            result[col] = 0.0
        result[col] = result[col].fillna(0.0)

    context.log.info(
        "Economic impact computation complete",
        extra={
            "num_impacts": len(result),
            "total_wage_impact": f"${result['wage_impact'].sum():,.2f}",
            "total_production_impact": f"${result['production_impact'].sum():,.2f}",
            "model_version": adapter.get_model_version(),
        },
    )

    metadata = {
        "num_impacts": len(result),
        "model_version": adapter.get_model_version(),
        "total_wage_impact": f"${result['wage_impact'].sum():,.2f}",
        "total_proprietor_income_impact": f"${result['proprietor_income_impact'].sum():,.2f}",
        "total_gross_operating_surplus": f"${result['gross_operating_surplus'].sum():,.2f}",
        "total_production_impact": f"${result['production_impact'].sum():,.2f}",
        "preview": _preview(result, empty="No impacts"),
    }
    return Output(value=result, metadata=metadata)  # type: ignore[arg-type]


def _create_placeholder_impacts(
    shocks_df: pd.DataFrame, context: AssetExecutionContext
) -> Output[pd.DataFrame]:
    """Placeholder impacts (zero values) when the BEA I-O adapter is unavailable."""
    context.log.warning("Creating placeholder impacts (BEA I-O adapter unavailable)")
    df = shocks_df.copy()
    for col in _IMPACT_COLS:
        df[col] = 0.0
    df["model_version"] = "placeholder"
    df["confidence"] = 0.0
    df["quality_flags"] = "bea_adapter_unavailable"
    return Output(
        value=df,
        metadata={
            "num_impacts": len(df),
            "model_version": "placeholder",
            "warning": "BEA I-O adapter unavailable - placeholder impacts generated",
        },
    )  # type: ignore[arg-type]


@asset_check(
    asset="economic_impacts",
    description="Validate economic impacts computation quality",
)
def economic_impacts_quality_check(economic_impacts: pd.DataFrame) -> AssetCheckResult:
    """Check no negatives / NaNs in impact columns; fail if placeholder model in use."""
    if economic_impacts.empty:
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description="✗ Economic impacts FAILED: No impacts generated",
            metadata={"num_impacts": 0},
        )
    if economic_impacts["model_version"].iloc[0] == "placeholder":
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description="✗ Economic impacts FAILED: Using placeholder model (R adapter unavailable)",
            metadata={"model_version": "placeholder"},
        )

    issues: list[str] = []
    for col in _IMPACT_COLS:
        if col not in economic_impacts.columns:
            issues.append(f"Missing column: {col}")
            continue
        if (neg := int((economic_impacts[col] < 0).sum())) > 0:
            issues.append(f"{col}: {neg} negative values")
        if (nan := int(economic_impacts[col].isna().sum())) > 0:
            issues.append(f"{col}: {nan} NaN values")

    passed = not issues
    severity = AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR
    description = (
        f"✓ Economic impacts PASSED: {len(economic_impacts)} impacts computed"
        if passed
        else f"✗ Economic impacts FAILED: {', '.join(issues)}"
    )
    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=description,
        metadata={
            "num_impacts": len(economic_impacts),
            "model_version": economic_impacts["model_version"].iloc[0],
            "issues": issues,
        },
    )


# ---------------------------------------------------------------------------
# Fiscal data prep (geographic resolution + inflation adjustment)
# ---------------------------------------------------------------------------


@asset(
    description="SBIR awards prepared for fiscal analysis with NAICS enrichment and geographic resolution",
    group_name="fiscal_data_prep",
    compute_kind="pandas",
)
def fiscal_prepared_sbir_awards(
    context: AssetExecutionContext,
    fiscal_naics_enriched_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """Add state-level geographic resolution to NAICS-enriched awards."""
    from sbir_etl.enrichers.geographic_resolver import resolve_award_geography

    config = get_config()
    context.log.info(
        "Starting fiscal award preparation",
        extra={"num_awards": len(fiscal_naics_enriched_awards)},
    )

    with performance_monitor.monitor_block("geographic_resolution"):
        resolved_df, _ = resolve_award_geography(
            fiscal_naics_enriched_awards,
            config=config.fiscal_analysis,  # type: ignore[arg-type]
        )
    if "fiscal_state_code" in resolved_df.columns:
        resolved_df["resolved_state"] = resolved_df["fiscal_state_code"]

    total = len(resolved_df)
    geo_cov = resolved_df["resolved_state"].notna().sum() / total if total else 0.0
    naics_cov = (
        f"{(resolved_df['fiscal_naics_code'].notna().sum() / total):.1%}" if total else "0%"
    )

    context.log.info(
        "Fiscal award preparation complete",
        extra={
            "num_awards": total,
            "naics_coverage": naics_cov,
            "geographic_coverage": f"{geo_cov:.1%}",
        },
    )

    metadata = {
        "num_awards": total,
        "naics_coverage": naics_cov,
        "geographic_coverage": f"{geo_cov:.1%}",
        "preview": _preview(resolved_df, empty="No awards"),
    }
    return Output(value=resolved_df, metadata=metadata)  # type: ignore[arg-type]


@asset_check(
    asset="fiscal_prepared_sbir_awards",
    description="Validate geographic resolution success rate meets threshold",
)
def fiscal_geographic_resolution_check(
    fiscal_prepared_sbir_awards: pd.DataFrame,
) -> AssetCheckResult:
    """Asset check: state-level geographic resolution rate ≥ threshold."""
    threshold = get_config().fiscal_analysis.quality_thresholds.get(
        "geographic_resolution_rate", 0.90
    )
    total = len(fiscal_prepared_sbir_awards)
    resolved = fiscal_prepared_sbir_awards.get("resolved_state", pd.Series()).notna().sum()
    rate = resolved / total if total > 0 else 0.0
    return _threshold_check(
        label="Geographic resolution",
        actual=rate,
        threshold=threshold,
        metadata={
            "resolution_rate": f"{rate:.1%}",
            "threshold": f"{threshold:.1%}",
            "total_awards": int(total),
            "resolved_awards": int(resolved),
            "unresolved_awards": int(total - resolved),
        },
    )


@asset(
    description="SBIR awards with inflation-adjusted amounts normalized to base year",
    group_name="fiscal_data_prep",
    compute_kind="pandas",
)
def inflation_adjusted_awards(
    context: AssetExecutionContext,
    fiscal_prepared_sbir_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """Normalize award amounts to the configured base year via BEA GDP deflator."""
    config = get_config()
    context.log.info(
        "Starting inflation adjustment",
        extra={"num_awards": len(fiscal_prepared_sbir_awards)},
    )

    with performance_monitor.monitor_block("inflation_adjustment"):
        adjusted_df, quality_metrics = adjust_awards_for_inflation(
            fiscal_prepared_sbir_awards,
            target_year=config.fiscal_analysis.base_year,
            config=config.fiscal_analysis,  # type: ignore[arg-type]
        )
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
        "total_adjusted_amount": (
            f"${adjusted_df['inflation_adjusted_amount'].sum():,.2f}"
            if "inflation_adjusted_amount" in adjusted_df.columns
            else "N/A"
        ),
        "preview": _preview(adjusted_df, empty="No awards"),
    }
    return Output(value=adjusted_df, metadata=metadata)  # type: ignore[arg-type]


@asset_check(
    asset="inflation_adjusted_awards",
    description="Validate inflation adjustment quality meets threshold",
)
def inflation_adjustment_quality_check(inflation_adjusted_awards: pd.DataFrame) -> AssetCheckResult:
    """Asset check: inflation-adjustment success rate ≥ threshold."""
    threshold = get_config().fiscal_analysis.quality_thresholds.get(
        "inflation_adjustment_success", 0.95
    )
    total = len(inflation_adjusted_awards)
    adjusted = 0
    for col in ("inflation_adjusted_amount", "fiscal_adjusted_amount"):
        if col in inflation_adjusted_awards.columns:
            adjusted = inflation_adjusted_awards[col].notna().sum()
            break
    rate = adjusted / total if total > 0 else 0.0
    return _threshold_check(
        label="Inflation adjustment",
        actual=rate,
        threshold=threshold,
        metadata={
            "success_rate": f"{rate:.1%}",
            "threshold": f"{threshold:.1%}",
            "total_awards": int(total),
            "adjusted_awards": int(adjusted),
            "unadjusted_awards": int(total - adjusted),
        },
    )


# ---------------------------------------------------------------------------
# Tax calculation
# ---------------------------------------------------------------------------


@asset(
    description="Economic components extracted from BEA I-O impacts for tax base calculation",
    group_name="tax_calculation",
    compute_kind="pandas",
)
def tax_base_components(
    context: AssetExecutionContext,
    economic_impacts: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """Extract validated tax-base components (wages, proprietor income, GOS, consumption)."""
    config = get_config()
    context.log.info(
        "Starting tax base component extraction", extra={"num_impacts": len(economic_impacts)}
    )

    calculator = FiscalComponentCalculator(config=config.fiscal_analysis)
    with performance_monitor.monitor_block("component_extraction"):
        components_df = calculator.extract_components(economic_impacts)
    validation = calculator.validate_aggregate_components(components_df)

    context.log.info(
        "Tax base component extraction complete",
        extra={
            "num_components": len(components_df),
            "validation_passed": validation.is_valid,
            "total_wage_impact": f"${components_df['wage_impact'].sum():,.2f}",
            "total_component_total": f"${components_df['component_total'].sum():,.2f}",
        },
    )

    metadata = {
        "num_components": len(components_df),
        "validation_passed": validation.is_valid,
        "total_wage_impact": f"${components_df['wage_impact'].sum():,.2f}",
        "total_proprietor_income": f"${components_df['proprietor_income_impact'].sum():,.2f}",
        "total_gos": f"${components_df['gross_operating_surplus'].sum():,.2f}",
        "total_consumption": f"${components_df['consumption_impact'].sum():,.2f}",
        "validation_difference": f"${validation.difference:,.2f}",
        "validation_tolerance": f"${validation.tolerance:,.2f}",
        "quality_flags": validation.quality_flags,
        "preview": _preview(components_df, empty="No components"),
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
    """Estimate federal income, payroll, corporate income, and excise tax receipts."""
    config = get_config()
    context.log.info("Starting federal tax estimation", extra={"num_components": len(tax_base_components)})

    estimator = FiscalTaxEstimator(config=config.fiscal_analysis)
    with performance_monitor.monitor_block("tax_estimation"):
        tax_df = estimator.estimate_taxes_from_components(tax_base_components)
    stats = estimator.get_estimation_statistics(tax_df)

    context.log.info(
        "Federal tax estimation complete",
        extra={
            "num_estimates": len(tax_df),
            "total_tax_receipts": f"${stats.total_tax_receipts:,.2f}",
            "avg_effective_rate": f"{stats.avg_effective_rate:.2f}%",
        },
    )

    metadata = {
        "num_estimates": len(tax_df),
        "total_individual_income_tax": f"${stats.total_individual_income_tax:,.2f}",
        "total_payroll_tax": f"${stats.total_payroll_tax:,.2f}",
        "total_corporate_income_tax": f"${stats.total_corporate_income_tax:,.2f}",
        "total_excise_tax": f"${stats.total_excise_tax:,.2f}",
        "total_tax_receipts": f"${stats.total_tax_receipts:,.2f}",
        "avg_effective_rate": f"{stats.avg_effective_rate:.2f}%",
        "preview": _preview(tax_df, empty="No estimates"),
    }
    return Output(value=tax_df, metadata=metadata)  # type: ignore[arg-type]


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
    """Compute ROI / payback / NPV / benefit-cost from tax receipts vs SBIR investment."""
    config = get_config()
    context.log.info(
        "Starting fiscal return summary calculation",
        extra={
            "num_tax_estimates": len(federal_tax_estimates),
            "num_awards": len(inflation_adjusted_awards),
        },
    )

    investment = 0.0
    for col in (
        "inflation_adjusted_amount",
        "fiscal_adjusted_amount",
        "award_amount",
        "shock_amount",
    ):
        if col in inflation_adjusted_awards.columns:
            investment = float(inflation_adjusted_awards[col].sum())
            break
    if investment == 0:
        logger.warning("No SBIR investment amount found in inflation_adjusted_awards")

    calculator = FiscalROICalculator(config=config.fiscal_analysis)
    with performance_monitor.monitor_block("roi_calculation"):
        summary = calculator.calculate_roi_summary(
            tax_estimates_df=federal_tax_estimates,
            sbir_investment=Decimal(str(investment)),
            discount_rate=0.03,
            time_horizon_years=10,
        )

    summary_df = pd.DataFrame(
        {
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
    )

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
        "preview": _preview(summary_df, head=None),
    }
    return Output(value=summary_df, metadata=metadata)


# ---------------------------------------------------------------------------
# Sensitivity analysis
# ---------------------------------------------------------------------------


@asset(
    description="Parameter sweep scenarios for sensitivity analysis",
    group_name="sensitivity_analysis",
    compute_kind="pandas",
)
def sensitivity_scenarios(context: AssetExecutionContext) -> Output[pd.DataFrame]:
    """Generate Monte Carlo / Latin Hypercube / grid-search scenario combinations."""
    config = get_config()
    context.log.info("Starting sensitivity scenario generation")

    sweep = FiscalParameterSweep(config=config.fiscal_analysis)
    with performance_monitor.monitor_block("parameter_sweep"):
        scenarios_df = sweep.generate_scenarios()

    method = scenarios_df["method"].iloc[0] if len(scenarios_df) > 0 else "unknown"
    parameters = [
        c
        for c in scenarios_df.columns
        if c not in ("scenario_id", "method", "random_seed", "points_per_dimension")
    ]
    context.log.info(
        "Sensitivity scenario generation complete",
        extra={"num_scenarios": len(scenarios_df), "method": method, "parameters": parameters},
    )

    metadata = {
        "num_scenarios": len(scenarios_df),
        "method": method,
        "parameters": parameters,
        "preview": _preview(scenarios_df, empty="No scenarios"),
    }
    return Output(value=scenarios_df, metadata=metadata)


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
    """Quantify uncertainty (CIs, sensitivity indices) from scenario sweep results."""
    config = get_config()
    context.log.info(
        "Starting uncertainty analysis",
        extra={
            "num_scenarios": len(sensitivity_scenarios),
            "num_tax_estimates": len(federal_tax_estimates),
        },
    )

    # Placeholder: apply parameter variations to a baseline rather than re-running the
    # full pipeline per scenario. Full implementation would recompute downstream assets.
    scenario_results = sensitivity_scenarios.copy()
    baseline_tax = float(federal_tax_estimates["total_tax_receipt"].sum())
    if "economic_multiplier" in scenario_results.columns:
        scenario_results["total_tax_receipt"] = (
            baseline_tax * scenario_results["economic_multiplier"] / 2.0
        )
    else:
        scenario_results["total_tax_receipt"] = baseline_tax

    quantifier = FiscalUncertaintyQuantifier(config=config.fiscal_analysis)
    with performance_monitor.monitor_block("uncertainty_quantification"):
        result = quantifier.quantify_uncertainty(
            scenario_results_df=scenario_results, target_column="total_tax_receipt"
        )

    def _ci(level: float, idx: int) -> float:
        return float(result.confidence_intervals.get(level, (Decimal("0"), Decimal("0")))[idx])

    uncertainty_df = pd.DataFrame(
        [
            {
                "min_estimate": float(result.min_estimate),
                "mean_estimate": float(result.mean_estimate),
                "max_estimate": float(result.max_estimate),
                "confidence_90_low": _ci(0.90, 0),
                "confidence_90_high": _ci(0.90, 1),
                "confidence_95_low": _ci(0.95, 0),
                "confidence_95_high": _ci(0.95, 1),
                "high_uncertainty": quantifier.flag_high_uncertainty(result),
            }
        ]
    )

    context.log.info(
        "Uncertainty analysis complete",
        extra={
            "min_estimate": f"${result.min_estimate:,.2f}",
            "mean_estimate": f"${result.mean_estimate:,.2f}",
            "max_estimate": f"${result.max_estimate:,.2f}",
            "high_uncertainty": quantifier.flag_high_uncertainty(result),
        },
    )

    metadata = {
        "min_estimate": f"${result.min_estimate:,.2f}",
        "mean_estimate": f"${result.mean_estimate:,.2f}",
        "max_estimate": f"${result.max_estimate:,.2f}",
        "sensitivity_indices": MetadataValue.json(result.sensitivity_indices),
        "quality_flags": result.quality_flags,
        "high_uncertainty": quantifier.flag_high_uncertainty(result),
        "preview": _preview(uncertainty_df, head=None),
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
    """Combine ROI summary, uncertainty bands, and tax totals into one policy report."""
    config = get_config()
    context.log.info("Starting fiscal returns report generation")

    report = fiscal_return_summary.merge(
        uncertainty_analysis, left_index=True, right_index=True, how="outer"
    )
    report["total_tax_receipts_baseline"] = float(federal_tax_estimates["total_tax_receipt"].sum())
    report["num_tax_estimates"] = len(federal_tax_estimates)

    roi = (
        f"{report['roi_ratio'].iloc[0]:.3f}"
        if len(report) > 0 and "roi_ratio" in report.columns
        else "N/A"
    )
    context.log.info(
        "Fiscal returns report generation complete",
        extra={"roi_ratio": roi, "num_scenarios": len(uncertainty_analysis)},
    )

    metadata = {
        "report_generated_at": MetadataValue.timestamp(pd.Timestamp.now(tz="UTC")),
        "base_year": config.fiscal_analysis.base_year,
        "model_version": config.fiscal_analysis.stateio_model_version,
        "preview": _preview(report, head=None, empty="No report"),
    }
    return Output(value=report, metadata=metadata)  # type: ignore[arg-type]
