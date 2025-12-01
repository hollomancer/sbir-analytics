"""Dagster assets for SBIR-USAspending enrichment pipeline."""

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
from ..enrichers.chunked_enrichment import ChunkedEnricher
from ..enrichers.usaspending import enrich_sbir_with_usaspending
from ..utils.monitoring import performance_monitor
from ..utils.reporting.analyzers.sbir_analyzer import SbirEnrichmentAnalyzer


@asset(
    description="SBIR awards enriched with USAspending recipient data",
    group_name="enrichment",
    compute_kind="pandas",
)
def enriched_sbir_awards(
    context: AssetExecutionContext,
    validated_sbir_awards: pd.DataFrame,
    raw_usaspending_recipients: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Enrich validated SBIR awards with USAspending recipient data.

    Supports both standard and chunked processing based on dataset size
    and configured memory thresholds.

    Args:
        validated_sbir_awards: Validated SBIR awards DataFrame
        raw_usaspending_recipients: USAspending recipient lookup data

    Returns:
        Enriched SBIR awards with USAspending data and match metadata
    """
    config = get_config()

    context.log.info(
        "Starting SBIR-USAspending enrichment",
        extra={
            "sbir_records": len(validated_sbir_awards),
            "usaspending_recipients": len(raw_usaspending_recipients),
        },
    )

    # Determine if chunked processing is needed
    use_chunked = _should_use_chunked_processing(
        validated_sbir_awards,
        raw_usaspending_recipients,
        config,
    )

    if use_chunked:
        context.log.info("Using chunked enrichment processing")
        enriched_df, enrichment_metrics = _enrich_chunked(
            validated_sbir_awards,
            raw_usaspending_recipients,
            config,
            context,
        )
    else:
        context.log.info("Using standard enrichment processing")
        # Perform enrichment with performance monitoring
        with performance_monitor.monitor_block("enrichment_core"):
            enriched_df = enrich_sbir_with_usaspending(
                sbir_df=validated_sbir_awards,
                recipient_df=raw_usaspending_recipients,
                sbir_company_col="Company",
                sbir_uei_col="UEI",
                sbir_duns_col="Duns",
                # USAspending recipient_lookup table column names
                recipient_name_col="legal_business_name",
                recipient_uei_col="uei",
                recipient_duns_col="duns",
                high_threshold=90,
                low_threshold=75,
                return_candidates=True,
            )
        enrichment_metrics = {}
        enricher = None

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

    # Get performance metrics before creating module_data
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

    # Perform statistical analysis with SBIR analyzer
    analyzer = SbirEnrichmentAnalyzer()
    run_context = {
        "run_id": context.run.run_id if context.run else f"run_{context.run_id}",
        "pipeline_name": "sbir_enrichment",
        "stage": "enrich",
    }

    # Prepare module data for analysis
    module_data = {
        "enriched_df": enriched_df,
        "original_df": validated_sbir_awards,
        "enrichment_metrics": {
            "records_processed": total_awards,
            "records_failed": 0,  # Enrichment doesn't typically "fail" records
            "duration_seconds": duration,
            "records_per_second": records_per_second,
            "match_rate": match_rate,
            "matched_records": int(matched_awards),
            "exact_matches": int(exact_matches),
            "fuzzy_matches": int(fuzzy_matches),
            "processing_mode": "chunked" if use_chunked else "standard",
        },
        "run_context": run_context,
    }

    # Generate analysis report
    analysis_report = analyzer.analyze(module_data)

    context.log.info(
        "SBIR enrichment analysis complete",
        extra={
            "insights_generated": len(analysis_report.insights)
            if hasattr(analysis_report, "insights")
            else 0,
            "data_hygiene_score": analysis_report.data_hygiene.quality_score_mean
            if analysis_report.data_hygiene
            else None,
        },
    )

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
        # Statistical analysis results
        "analysis_insights_count": len(analysis_report.insights)
        if hasattr(analysis_report, "insights")
        else 0,
        "analysis_data_hygiene_score": round(analysis_report.data_hygiene.quality_score_mean, 3)
        if analysis_report.data_hygiene
        else None,
        "analysis_success_rate": round(analysis_report.success_rate, 3),
        "analysis_throughput": round(analysis_report.throughput_records_per_second, 2),
    }

    # Add progress metadata if chunked processing was used
    if use_chunked and enricher:
        progress_metadata = enricher.get_progress_metadata()
        metadata.update(progress_metadata)

    return Output(value=enriched_df, metadata=metadata)


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

        # Process chunks with progress logging to Dagster UI
        enriched_chunks = []
        all_metrics = []
        for _chunk_num, (enriched_chunk, chunk_metrics) in enumerate(
            enricher.process_all_chunks(), 1
        ):
            enriched_chunks.append(enriched_chunk)
            all_metrics.append(chunk_metrics)
            # Log progress to Dagster UI after each chunk
            progress = enricher.progress
            context.log.info(
                f"Enrichment progress: {progress.percent_complete:.1f}% "
                f"({progress.records_processed}/{progress.total_records} records, "
                f"{progress.chunks_processed}/{progress.total_chunks} chunks, "
                f"~{progress.estimated_remaining_seconds / 60:.0f} min remaining)",
                extra={
                    "percent_complete": round(progress.percent_complete, 2),
                    "records_processed": progress.records_processed,
                    "total_records": progress.total_records,
                    "chunks_processed": progress.chunks_processed,
                    "total_chunks": progress.total_chunks,
                    "estimated_remaining_minutes": round(
                        progress.estimated_remaining_seconds / 60, 1
                    ),
                },
            )

        # Combine chunks and aggregate metrics
        enriched_df = pd.concat(enriched_chunks, ignore_index=True)

        # Aggregate final metrics
        total_duration = sum(m.get("duration_seconds", 0) for m in all_metrics)
        total_matched = sum(m.get("records_matched", 0) for m in all_metrics)
        total_records = len(enriched_df)
        overall_match_rate = total_matched / total_records if total_records > 0 else 0

        metrics = {
            "total_records": total_records,
            "total_chunks": len(all_metrics),
            "overall_match_rate": overall_match_rate,
            "total_duration_seconds": total_duration,
            "chunks": all_metrics,
        }

        context.log.info(
            f"Chunked enrichment complete: {metrics['total_records']} records, "
            f"{metrics['overall_match_rate']:.1%} match rate, "
            f"{metrics['total_duration_seconds']:.2f}s",
            extra=metrics,
        )

        return enriched_df, metrics  # type: ignore[return-value]

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
        "match_methods": MetadataValue.json(report["match_methods"]),  # type: ignore[arg-type]
        "fuzzy_score_distribution": MetadataValue.json(report["fuzzy_score_distribution"]),  # type: ignore[arg-type]
    }

    return Output(value=report, metadata=metadata)  # type: ignore[arg-type]


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
    enrichment_config = config.data_quality.enrichment
    min_match_rate = (
        enrichment_config.get("usaspending_match_rate", 0.70)
        if isinstance(enrichment_config, dict)
        else 0.70
    )  # type: ignore[arg-type]

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
        passed=passed,
        severity=severity,
        description=description,
        metadata=metadata,  # type: ignore[arg-type]
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
