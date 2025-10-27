"""Dagster assets for SBIR-USAspending enrichment pipeline."""

from pathlib import Path
from typing import Any

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
from loguru import logger

from ..config.loader import get_config
from ..enrichers.chunked_enrichment import ChunkedEnricher
from ..enrichers.usaspending_enricher import enrich_sbir_with_usaspending
from ..utils.performance_monitor import performance_monitor
from ..utils.performance_alerts import AlertCollector, AlertSeverity
from ..utils.quality_baseline import QualityBaselineManager, QualityBaseline


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

    Supports both standard and chunked processing based on dataset size
    and configured memory thresholds.

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

    # Determine if chunked processing is needed
    use_chunked = _should_use_chunked_processing(
        validated_sbir_awards,
        usaspending_recipient_lookup,
        config,
    )

    if use_chunked:
        context.log.info("Using chunked enrichment processing")
        enriched_df, enrichment_metrics = _enrich_chunked(
            validated_sbir_awards,
            usaspending_recipient_lookup,
            config,
            context,
        )
    else:
        context.log.info("Using standard enrichment processing")
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
        enrichment_metrics = {}

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
    if not enrichment_metrics:
        perf_summary = performance_monitor.get_metrics_summary()
        enrichment_perf = perf_summary.get("enrichment_core", {})
        duration = enrichment_perf.get("total_duration", 0.0)
        avg_memory_delta = enrichment_perf.get("avg_memory_delta_mb", 0.0)
        max_peak_memory = enrichment_perf.get("max_peak_memory_mb", 0.0)
        records_per_second = (total_awards / duration) if duration > 0 else 0
    else:
        # Use metrics from chunked processing
        duration = enrichment_metrics.get("total_duration_seconds", 0.0)
        avg_memory_delta = enrichment_metrics.get("avg_memory_delta_mb", 0.0)
        max_peak_memory = enrichment_metrics.get("peak_memory_mb", 0.0)
        records_per_second = enrichment_metrics.get("records_per_second", 0.0)

    # Collect and check for performance/quality alerts
    alerts = AlertCollector(
        asset_name="enriched_sbir_awards",
        run_id=context.run.run_id,
        config=config,
    )

    # Check performance thresholds
    alerts.check_duration_per_record(duration, total_awards, metric_name="enrichment_duration")
    alerts.check_memory_delta(avg_memory_delta, metric_name="enrichment_memory")

    # Check quality thresholds
    alerts.check_match_rate(match_rate, metric_name="enrichment_match_rate")

    # Log all alerts
    alerts.log_alerts()

    # Save alerts to file for record-keeping
    alerts_output_dir = Path("reports/alerts")
    alerts_output_dir.mkdir(parents=True, exist_ok=True)
    alerts_file = alerts_output_dir / f"enrichment_alerts_{context.run.run_id}.json"
    alerts.save_to_file(alerts_file)

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
        # Processing metadata
        "processing_mode": "chunked" if use_chunked else "standard",
        "chunk_size": config.enrichment.performance.chunk_size if use_chunked else None,
        # Alert metadata
            "alert_count": alerts.alerts.__len__(),
            "alert_failures": len(alerts.get_alerts(AlertSeverity.FAILURE)),
            "alert_warnings": len(alerts.get_alerts(AlertSeverity.WARNING)),
            "alerts": MetadataValue.json(alerts.to_dict()),
        }

        # Create and save quality baseline for regression detection
        baseline_mgr = QualityBaselineManager()
        current_baseline = baseline_mgr.create_baseline_from_metrics(
            match_rate=match_rate,
            matched_records=int(matched_awards),
            total_records=total_awards,
            exact_matches=int(exact_matches),
            fuzzy_matches=int(fuzzy_matches),
            run_id=context.run.run_id,
            processing_mode="chunked" if use_chunked else "standard",
            metadata={
                "duration_seconds": duration,
                "peak_memory_mb": max_peak_memory,
                "records_per_second": records_per_second,
            },
        )
        baseline_mgr.save_baseline(current_baseline)

        return Output(value=enriched_df, metadata=metadata)</parameter>
    </invoke>


def _should_use_chunked_processing(
    sbir_df: pd.DataFrame,
    recipient_df: pd.DataFrame,
    config: Any,
) -> bool:
    """Determine if chunked processing should be used.

    Args:
        sbir_df: SBIR DataFrame
        recipient_df: Recipient DataFrame
        config: Configuration object

    Returns:
        True if chunked processing should be used
    """
    # Use chunked processing if:
    # 1. SBIR dataset is large (> 10K records)
    # 2. Total dataset size exceeds threshold
    total_sbir = len(sbir_df)
    total_recipients = len(recipient_df)

    # Estimate memory needed (rough heuristic)
    estimated_memory_mb = (total_sbir * 1.0 + total_recipients * 1.0) / 1024
    threshold_mb = config.enrichment.performance.memory_threshold_mb

    return total_sbir > 10000 or estimated_memory_mb > (threshold_mb * 0.8)


def _enrich_chunked(
    sbir_df: pd.DataFrame,
    recipient_df: pd.DataFrame,
    config: Any,
    context: AssetExecutionContext,
) -> tuple[pd.DataFrame, dict]:
    """Perform enrichment using chunked processing.

    Args:
        sbir_df: SBIR DataFrame
        recipient_df: Recipient DataFrame
        config: Configuration object
        context: Dagster execution context

    Returns:
        Tuple of (enriched DataFrame, metrics dict)
    """
    try:
        enricher = ChunkedEnricher(
            sbir_df=sbir_df,
            recipient_df=recipient_df,
            checkpoint_dir=Path("reports/checkpoints"),
            enable_progress_tracking=config.enrichment.performance.enable_progress_tracking,
        )

        enriched_df, metrics = enricher.process_to_dataframe()

        context.log.info(
            f"Chunked enrichment complete: {metrics['total_records']} records, "
            f"{metrics['overall_match_rate']:.1%} match rate, "
            f"{metrics['total_duration_seconds']:.2f}s",
            extra=metrics,
        )

        return enriched_df, metrics

    except Exception as e:
        logger.error(f"Chunked enrichment failed: {e}")
        raise


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


@asset_check(
    asset="enriched_sbir_awards",
    description="No quality regression detected compared to historical baseline",
)
def enrichment_quality_regression_check(enriched_sbir_awards: pd.DataFrame) -> AssetCheckResult:
    """
    Check for quality regressions compared to historical baseline.

    This check compares the current enrichment match rate against the stored baseline
    and fails if the match rate has regressed beyond the configured threshold.

    Args:
        enriched_sbir_awards: Enriched SBIR awards DataFrame

    Returns:
        AssetCheckResult with pass/fail status and comparison metrics
    """
    config = get_config()
    regression_threshold = config.data_quality.enrichment.get("regression_threshold_percent", 5.0)

    # Calculate current metrics
    total_awards = len(enriched_sbir_awards)
    matched_awards = enriched_sbir_awards["_usaspending_match_method"].notna().sum()
    exact_matches = enriched_sbir_awards["_usaspending_match_method"].str.contains("exact", na=False).sum()
    fuzzy_matches = enriched_sbir_awards["_usaspending_match_method"].str.contains("fuzzy", na=False).sum()
    match_rate = matched_awards / total_awards if total_awards > 0 else 0

    # Load baseline and compare
    baseline_mgr = QualityBaselineManager()
    current_baseline = baseline_mgr.create_baseline_from_metrics(
        match_rate=match_rate,
        matched_records=int(matched_awards),
        total_records=total_awards,
        exact_matches=int(exact_matches),
        fuzzy_matches=int(fuzzy_matches),
    )

    comparison = baseline_mgr.compare_to_baseline(
        current=current_baseline,
        regression_threshold_percent=regression_threshold,
    )

    # Determine pass/fail
    passed = not comparison.exceeded_threshold

    # Set severity
    if passed:
        severity = AssetCheckSeverity.WARN
        if comparison.baseline.match_rate == current_baseline.match_rate:
            description = "✓ First baseline established"
        elif current_baseline.match_rate > comparison.baseline.match_rate:
            description = f"✓ Quality improved: {current_baseline.match_rate:.1%} (was {comparison.baseline.match_rate:.1%})"
        else:
            description = f"✓ Quality regression within threshold: {current_baseline.match_rate:.1%} (was {comparison.baseline.match_rate:.1%}, threshold: {regression_threshold:.1f}pp)"
    else:
        severity = AssetCheckSeverity.ERROR
        description = f"✗ Quality regression detected: {current_baseline.match_rate:.1%} is below baseline {comparison.baseline.match_rate:.1%} by {abs(comparison.match_rate_delta_percent):.2f}pp (threshold: {regression_threshold:.1f}pp)"

    metadata = {
        "baseline_match_rate": f"{comparison.baseline.match_rate:.1%}",
        "current_match_rate": f"{current_baseline.match_rate:.1%}",
        "delta_percentage_points": f"{comparison.match_rate_delta_percent:+.2f}pp",
        "regression_severity": comparison.regression_severity,
        "threshold_percent": f"{regression_threshold:.1f}pp",
        "exceeded_threshold": comparison.exceeded_threshold,
        "baseline_run_id": comparison.baseline.run_id or "initial",
        "baseline_timestamp": comparison.baseline.timestamp.isoformat() if comparison.baseline.timestamp else "unknown",
    }

    return AssetCheckResult(
        passed=passed,
        severity=severity,
        description=description,
        metadata=metadata,
    )
</parameter>
</invoke>
