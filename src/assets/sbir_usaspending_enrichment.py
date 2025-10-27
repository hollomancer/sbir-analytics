"""Dagster assets for SBIR-USAspending enrichment pipeline."""

import pandas as pd
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    AssetIn,
    MetadataValue,
    Output,
    asset,
    asset_check,
)

from ..config.loader import get_config
from ..enrichers.usaspending_enricher import enrich_sbir_with_usaspending
from ..utils.performance_monitor import performance_monitor


@asset(
    description="SBIR awards enriched with USAspending recipient data",
    group_name="enrichment",
    compute_kind="pandas",
)
def enriched_sbir_awards(
    context: AssetExecutionContext,
    validated_sbir_awards: pd.DataFrame,
    usaspending_recipient_lookup: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Enrich validated SBIR awards with USAspending recipient data.

    Args:
        validated_sbir_awards: Validated SBIR awards DataFrame
        usaspending_recipient_lookup: USAspending recipient lookup data

    Returns:
        Enriched SBIR awards with USAspending data and match metadata
    """
    config = get_config()

    context.log.info(
        "Starting SBIR-USAspending enrichment",
        extra={
            "sbir_records": len(validated_sbir_awards),
            "usaspending_recipients": len(usaspending_recipient_lookup),
        },
    )

    # Perform enrichment with performance monitoring
    with performance_monitor.monitor_block("enrichment_core"):
        enriched_df = enrich_sbir_with_usaspending(
            sbir_df=validated_sbir_awards,
            recipient_df=usaspending_recipient_lookup,
            sbir_company_col="Company",
            sbir_uei_col="UEI",
            sbir_duns_col="Duns",
            recipient_name_col="recipient_name",
            recipient_uei_col="recipient_uei",
            recipient_duns_col="recipient_duns",
            high_threshold=90,
            low_threshold=75,
            return_candidates=True,
        )

    # Calculate enrichment statistics
    total_awards = len(enriched_df)
    matched_awards = enriched_df["_usaspending_match_method"].notna().sum()
    exact_matches = enriched_df["_usaspending_match_method"].str.contains("exact", na=False).sum()
    fuzzy_matches = enriched_df["_usaspending_match_method"].str.contains("fuzzy", na=False).sum()

    match_rate = matched_awards / total_awards if total_awards > 0 else 0

    context.log.info(
        "Enrichment complete",
        extra={
            "total_awards": total_awards,
            "matched_awards": matched_awards,
            "exact_matches": exact_matches,
            "fuzzy_matches": fuzzy_matches,
            "match_rate": f"{match_rate:.1%}",
        },
    )

    # Get performance metrics
    perf_summary = performance_monitor.get_metrics_summary()
    enrichment_perf = perf_summary.get("enrichment_core", {})

    # Extract performance data
    duration = enrichment_perf.get("total_duration", 0.0)
    avg_memory_delta = enrichment_perf.get("avg_memory_delta_mb", 0.0)
    max_peak_memory = enrichment_perf.get("max_peak_memory_mb", 0.0)
    records_per_second = (total_awards / duration) if duration > 0 else 0

    # Create metadata
    metadata = {
        "num_records": len(enriched_df),
        "match_rate": f"{match_rate:.1%}",
        "matched_awards": int(matched_awards),
        "exact_matches": int(exact_matches),
        "fuzzy_matches": int(fuzzy_matches),
        "enrichment_columns": [
            col for col in enriched_df.columns if col.startswith("usaspending_")
        ],
        "preview": MetadataValue.md(enriched_df.head(10).to_markdown()),
        # Performance metrics
        "performance_duration_seconds": round(duration, 2),
        "performance_records_per_second": round(records_per_second, 2),
        "performance_peak_memory_mb": round(max_peak_memory, 2),
        "performance_avg_memory_delta_mb": round(avg_memory_delta, 2),
    }

    return Output(value=enriched_df, metadata=metadata)


@asset(
    description="SBIR-USAspending enrichment quality report",
    group_name="enrichment",
    compute_kind="pandas",
)
def sbir_usaspending_enrichment_report(
    context: AssetExecutionContext, enriched_sbir_awards: pd.DataFrame
) -> Output[dict]:
    """
    Generate quality report for SBIR-USAspending enrichment.

    Args:
        enriched_sbir_awards: Enriched SBIR awards DataFrame

    Returns:
        Enrichment quality report
    """
    # Analyze match quality
    match_methods = enriched_sbir_awards["_usaspending_match_method"].value_counts(dropna=False)

    # Score distribution for fuzzy matches
    fuzzy_scores = enriched_sbir_awards[
        enriched_sbir_awards["_usaspending_match_method"].str.contains("fuzzy", na=False)
    ]["_usaspending_match_score"]

    score_bins = pd.cut(fuzzy_scores, bins=[0, 75, 85, 90, 95, 100], right=False)
    score_distribution = score_bins.value_counts().sort_index()

    # Unmatched awards analysis
    unmatched = enriched_sbir_awards[enriched_sbir_awards["_usaspending_match_method"].isna()]
    unmatched_with_identifiers = unmatched[(unmatched["UEI"].notna()) | (unmatched["Duns"].notna())]

    report = {
        "total_awards": len(enriched_sbir_awards),
        "matched_awards": match_methods.sum() - match_methods.get("NaN", 0),
        "match_rate": (match_methods.sum() - match_methods.get("NaN", 0))
        / len(enriched_sbir_awards),
        "match_methods": match_methods.to_dict(),
        "fuzzy_score_distribution": score_distribution.to_dict(),
        "unmatched_with_identifiers": len(unmatched_with_identifiers),
        "unmatched_total": len(unmatched),
    }

    context.log.info(
        "Enrichment report generated",
        extra={
            "match_rate": f"{report['match_rate']:.1%}",
            "matched_awards": report["matched_awards"],
            "unmatched_with_identifiers": report["unmatched_with_identifiers"],
        },
    )

    # Create metadata
    metadata = {
        "match_rate": f"{report['match_rate']:.1%}",
        "matched_awards": report["matched_awards"],
        "unmatched_awards": report["unmatched_total"],
        "match_methods": MetadataValue.json(report["match_methods"]),
        "fuzzy_score_distribution": MetadataValue.json(report["fuzzy_score_distribution"]),
    }

    return Output(value=report, metadata=metadata)


@asset_check(
    asset="enriched_sbir_awards",
    description="Enrichment match rate meets minimum threshold of 70%",
)
def enrichment_match_rate_check(enriched_sbir_awards: pd.DataFrame) -> AssetCheckResult:
    """
    Asset check to ensure enrichment match rate meets minimum threshold.

    This check will FAIL the asset if match rate falls below 70%,
    preventing downstream assets from running with poor-quality enrichment.

    Args:
        enriched_sbir_awards: Enriched SBIR awards DataFrame

    Returns:
        AssetCheckResult with pass/fail status and metrics
    """
    # Get configuration
    config = get_config()
    min_match_rate = config.data_quality.enrichment.usaspending_match_rate  # From config: 0.70

    # Calculate match rate
    total_awards = len(enriched_sbir_awards)
    matched_awards = enriched_sbir_awards["_usaspending_match_method"].notna().sum()
    actual_match_rate = matched_awards / total_awards if total_awards > 0 else 0.0

    # Break down matches by method
    match_methods = enriched_sbir_awards["_usaspending_match_method"].value_counts(dropna=False)
    exact_matches = (
        enriched_sbir_awards["_usaspending_match_method"].str.contains("exact", na=False).sum()
    )
    fuzzy_matches = (
        enriched_sbir_awards["_usaspending_match_method"].str.contains("fuzzy", na=False).sum()
    )

    # Determine if check passes
    passed = actual_match_rate >= min_match_rate

    # Set severity and description
    if passed:
        severity = AssetCheckSeverity.WARN
        description = f"✓ Enrichment match rate check PASSED: {actual_match_rate:.1%} (threshold: {min_match_rate:.1%})"
    else:
        severity = AssetCheckSeverity.ERROR
        description = f"✗ Enrichment match rate check FAILED: {actual_match_rate:.1%} is below threshold of {min_match_rate:.1%}"

    # Create metadata
    metadata = {
        "actual_match_rate": f"{actual_match_rate:.1%}",
        "threshold": f"{min_match_rate:.1%}",
        "total_awards": total_awards,
        "matched_awards": matched_awards,
        "unmatched_awards": total_awards - matched_awards,
        "exact_matches": int(exact_matches),
        "fuzzy_matches": int(fuzzy_matches),
        "match_methods": match_methods.to_dict(),
    }

    return AssetCheckResult(
        passed=passed, severity=severity, description=description, metadata=metadata
    )


@asset_check(
    asset="enriched_sbir_awards",
    description="All required enrichment fields are populated",
)
def enrichment_completeness_check(enriched_sbir_awards: pd.DataFrame) -> AssetCheckResult:
    """
    Validate that enriched output contains required fields and minimal null values.

    Ensures data quality for downstream consumption.

    Args:
        enriched_sbir_awards: Enriched SBIR awards DataFrame

    Returns:
        AssetCheckResult with pass/fail status
    """
    required_fields = [
        "_usaspending_match_method",
        "_usaspending_match_score",
        "usaspending_recipient_name",
    ]

    # Check all required fields exist
    missing_fields = [f for f in required_fields if f not in enriched_sbir_awards.columns]

    # Check null rates in key fields
    null_rates = {}
    for field in required_fields:
        if field in enriched_sbir_awards.columns:
            null_rate = enriched_sbir_awards[field].isna().sum() / len(enriched_sbir_awards)
            null_rates[field] = null_rate

    # Pass if no missing fields and null rates are reasonable (allowing for unmatched records)
    passed = len(missing_fields) == 0 and all(rate < 0.95 for rate in null_rates.values())

    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.ERROR if not passed else AssetCheckSeverity.WARN,
        description=f"{'✓ Completeness check passed' if passed else '✗ Completeness check failed'}",
        metadata={
            "missing_fields": missing_fields if missing_fields else "None",
            "null_rates": {k: f"{v:.1%}" for k, v in null_rates.items()},
            "total_records": len(enriched_sbir_awards),
        },
    )
