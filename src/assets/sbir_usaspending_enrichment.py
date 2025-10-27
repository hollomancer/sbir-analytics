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

    return Output(value=enriched_df, metadata=metadata)
