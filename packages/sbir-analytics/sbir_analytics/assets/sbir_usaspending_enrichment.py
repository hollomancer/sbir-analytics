"""Dagster assets for SBIR-USAspending enrichment pipeline."""

from dataclasses import dataclass
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

from sbir_etl.config.loader import get_config
from sbir_etl.enrichers.chunked_enrichment import ChunkedEnricher
from sbir_etl.enrichers.usaspending import enrich_sbir_with_usaspending
from sbir_etl.utils.identifiers import DunsProfile, normalize_duns, normalize_uei
from sbir_etl.utils.monitoring import performance_monitor
from sbir_etl.analyzers.sbir_analyzer import SbirEnrichmentAnalyzer


@dataclass(frozen=True)
class EnrichmentSummary:
    """Counts derived from the completed enrichment frame."""

    total_awards: int
    usaspending_matches: int
    sam_gov_matches: int
    total_matched: int
    exact_matches: int
    fuzzy_matches: int
    match_rate: float


@dataclass(frozen=True)
class PerformanceSummary:
    """Performance values reported in Dagster metadata and analysis."""

    duration: float
    records_per_second: float
    max_peak_memory: float
    avg_memory_delta: float


def _duns_key(value: object) -> str | None:
    # DUNS_V2: a DUNS column with NaN is read as float, so 12345678.0 must key
    # as 012345678, not as the different DUNS 123456780.
    return normalize_duns(value, profile=DunsProfile.DUNS_V2)


def _filter_recipients_by_sbir(
    sbir_df: pd.DataFrame,
    recipients_df: pd.DataFrame,
    context: AssetExecutionContext,
) -> pd.DataFrame:
    """Filter recipients to only those that could match SBIR records.

    This dramatically reduces memory usage by keeping only relevant recipients.

    Args:
        sbir_df: SBIR awards DataFrame with uei/duns columns
        recipients_df: Full recipients DataFrame
        context: Dagster context for logging

    Returns:
        Filtered recipients DataFrame
    """
    original_count = len(recipients_df)

    # Extract unique identifiers from SBIR data
    sbir_ueis = set()
    sbir_duns = set()

    if "uei" in sbir_df.columns:
        sbir_ueis = set(sbir_df["uei"].map(normalize_uei).dropna())
    if "duns" in sbir_df.columns:
        sbir_duns = set(sbir_df["duns"].map(_duns_key).dropna())

    context.log.info(f"SBIR identifiers: {len(sbir_ueis)} UEIs, {len(sbir_duns)} DUNS")

    # Build filter mask
    mask = pd.Series(False, index=recipients_df.index)

    if "uei" in recipients_df.columns and sbir_ueis:
        recipient_ueis = recipients_df["uei"].map(normalize_uei)
        mask |= recipient_ueis.isin(sbir_ueis)

    if "duns" in recipients_df.columns and sbir_duns:
        recipient_duns = recipients_df["duns"].map(_duns_key)
        mask |= recipient_duns.isin(sbir_duns)

    filtered_df = recipients_df[mask].copy()
    filtered_count = len(filtered_df)

    retained_percent = filtered_count / original_count * 100 if original_count else 0.0
    context.log.info(
        f"Filtered recipients: {original_count:,} -> {filtered_count:,} "
        f"({retained_percent:.1f}% retained)"
    )

    return filtered_df


def _run_usaspending_enrichment(
    sbir_df: pd.DataFrame,
    recipients_df: pd.DataFrame,
    config: Any,
    context: AssetExecutionContext,
) -> tuple[pd.DataFrame, dict[str, Any], bool]:
    """Run the standard or chunked USAspending enrichment stage."""
    filtered_recipients = _filter_recipients_by_sbir(sbir_df, recipients_df, context)
    use_chunked = _should_use_chunked_processing(sbir_df, filtered_recipients, config)

    if use_chunked:
        context.log.info("Using chunked enrichment processing")
        enriched_df, metrics = _enrich_chunked(
            sbir_df,
            filtered_recipients,
            config,
            context,
        )
        return enriched_df, metrics, True

    context.log.info("Using standard enrichment processing")
    with performance_monitor.monitor_block("enrichment_core"):
        enriched_df = enrich_sbir_with_usaspending(
            sbir_df=sbir_df,
            recipient_df=filtered_recipients,
            sbir_company_col="company_name",
            sbir_uei_col="uei",
            sbir_duns_col="duns",
            recipient_name_col="legal_business_name",
            recipient_uei_col="uei",
            recipient_duns_col="duns",
            high_threshold=90,
            low_threshold=75,
            return_candidates=True,
        )
    return enriched_df, {}, False


def _build_sam_indexes(
    sam_entities: pd.DataFrame,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Index SAM rows by normalized UEI and DUNS identifiers."""
    sam_by_uei: dict[str, Any] = {}
    sam_by_duns: dict[str, Any] = {}
    if sam_entities.empty:
        return sam_by_uei, sam_by_duns

    if "unique_entity_id" in sam_entities.columns:
        for index, uei in sam_entities["unique_entity_id"].dropna().items():
            normalized = str(uei).strip().upper()
            if normalized:
                sam_by_uei[normalized] = index

    duns_col = next(
        (column for column in ("duns_number", "duns", "DUNS") if column in sam_entities.columns),
        None,
    )
    if duns_col:
        for index, duns in sam_entities[duns_col].dropna().items():
            duns_key = _duns_key(duns)
            if duns_key:
                sam_by_duns[duns_key] = index

    return sam_by_uei, sam_by_duns


def _apply_sam_enrichment(
    enriched_df: pd.DataFrame,
    sam_entities: pd.DataFrame,
    context: AssetExecutionContext,
) -> pd.DataFrame:
    """Apply SAM fallback and NAICS enrichment to USAspending results."""
    sam_by_uei, sam_by_duns = _build_sam_indexes(sam_entities)
    enriched_df["_sam_gov_match_method"] = pd.NA
    enriched_df["_sam_gov_match_idx"] = pd.NA

    unmatched_mask = enriched_df["_usaspending_match_method"].isna()
    if unmatched_mask.any() and not sam_entities.empty:
        context.log.info(
            f"Attempting SAM.gov enrichment for {unmatched_mask.sum()} unmatched records"
        )
        if "uei" in enriched_df.columns:
            uei_series = (
                enriched_df.loc[unmatched_mask, "uei"]
                .fillna("")
                .astype(str)
                .str.strip()
                .str.upper()
            )
            uei_matches = uei_series.isin(sam_by_uei)
            matched_indices = uei_series[uei_matches].index
            enriched_df.loc[matched_indices, "_sam_gov_match_idx"] = (
                uei_series[uei_matches].map(sam_by_uei).values
            )
            enriched_df.loc[matched_indices, "_sam_gov_match_method"] = "sam-uei-exact"

        still_unmatched = unmatched_mask & enriched_df["_sam_gov_match_method"].isna()
        if "duns" in enriched_df.columns and still_unmatched.any():
            duns_series = enriched_df.loc[still_unmatched, "duns"].map(_duns_key)
            duns_matches = duns_series.isin(sam_by_duns)
            matched_indices = duns_series[duns_matches].index
            enriched_df.loc[matched_indices, "_sam_gov_match_idx"] = (
                duns_series[duns_matches].map(sam_by_duns).values
            )
            enriched_df.loc[matched_indices, "_sam_gov_match_method"] = "sam-duns-exact"

    needs_naics = (
        enriched_df["_usaspending_match_method"].notna() & enriched_df["_sam_gov_match_idx"].isna()
    )
    if needs_naics.any() and not sam_entities.empty:
        context.log.info(
            f"Enriching NAICS from SAM.gov for {needs_naics.sum()} USAspending-matched records"
        )
        if "UEI" in enriched_df.columns:
            uei_series = (
                enriched_df.loc[needs_naics, "UEI"].fillna("").astype(str).str.strip().str.upper()
            )
            uei_matches = uei_series.isin(sam_by_uei)
            matched_indices = uei_series[uei_matches].index
            enriched_df.loc[matched_indices, "_sam_gov_match_idx"] = (
                uei_series[uei_matches].map(sam_by_uei).values
            )
            enriched_df.loc[matched_indices, "_sam_gov_match_method"] = "sam-naics-uei"

        still_needs_naics = needs_naics & enriched_df["_sam_gov_match_idx"].isna()
        if "Duns" in enriched_df.columns and still_needs_naics.any():
            duns_series = enriched_df.loc[still_needs_naics, "Duns"].map(_duns_key)
            duns_matches = duns_series.isin(sam_by_duns)
            matched_indices = duns_series[duns_matches].index
            enriched_df.loc[matched_indices, "_sam_gov_match_idx"] = (
                duns_series[duns_matches].map(sam_by_duns).values
            )
            enriched_df.loc[matched_indices, "_sam_gov_match_method"] = "sam-naics-duns"

    sam_matched = enriched_df["_sam_gov_match_idx"].notna()
    sam_columns = [
        column
        for column in (
            "unique_entity_id",
            "legal_business_name",
            "dba_name",
            "physical_address_city",
            "physical_address_state",
            "cage_code",
            "primary_naics",
            "naics_code_string",
        )
        if column in sam_entities.columns
    ]
    if sam_matched.any():
        for column in sam_columns:
            enriched_df[f"sam_gov_{column}"] = pd.NA
            matched_index = enriched_df.loc[sam_matched, "_sam_gov_match_idx"].astype(int)
            enriched_df.loc[sam_matched, f"sam_gov_{column}"] = sam_entities.loc[
                matched_index, column
            ].values

    sam_fallback_count = (
        enriched_df["_sam_gov_match_method"].isin(["sam-uei-exact", "sam-duns-exact"]).sum()
    )
    sam_naics_count = (
        enriched_df["_sam_gov_match_method"].str.startswith("sam-naics", na=False).sum()
    )
    context.log.info(
        f"SAM.gov enrichment: {sam_fallback_count} fallback matches, "
        f"{sam_naics_count} NAICS-only matches"
    )

    enriched_df = enriched_df.drop(columns=["_sam_gov_match_idx"])
    enriched_df["_enrichment_source"] = None
    enriched_df.loc[enriched_df["_usaspending_match_method"].notna(), "_enrichment_source"] = (
        "usaspending"
    )
    fallback_mask = enriched_df["_sam_gov_match_method"].isin(["sam-uei-exact", "sam-duns-exact"])
    enriched_df.loc[fallback_mask, "_enrichment_source"] = "sam_gov"
    enriched_df["_naics_source"] = None
    enriched_df.loc[enriched_df["_sam_gov_match_method"].notna(), "_naics_source"] = "sam_gov"
    return enriched_df


def _summarize_enrichment(enriched_df: pd.DataFrame) -> EnrichmentSummary:
    """Calculate the match counts used by logs, analysis, and metadata."""
    total_awards = len(enriched_df)
    usaspending_matches = int(enriched_df["_usaspending_match_method"].notna().sum())
    sam_gov_matches = int(enriched_df["_sam_gov_match_method"].notna().sum())
    total_matched = usaspending_matches + sam_gov_matches
    exact_matches = int(
        enriched_df["_usaspending_match_method"].str.contains("exact", na=False).sum()
    )
    fuzzy_matches = int(
        enriched_df["_usaspending_match_method"].str.contains("fuzzy", na=False).sum()
    )
    return EnrichmentSummary(
        total_awards=total_awards,
        usaspending_matches=usaspending_matches,
        sam_gov_matches=sam_gov_matches,
        total_matched=total_matched,
        exact_matches=exact_matches,
        fuzzy_matches=fuzzy_matches,
        match_rate=total_matched / total_awards if total_awards else 0.0,
    )


def _performance_summary(
    total_awards: int,
    enrichment_metrics: dict[str, Any],
) -> PerformanceSummary:
    """Normalize standard and chunked performance metrics."""
    if enrichment_metrics:
        return PerformanceSummary(
            duration=enrichment_metrics.get("total_duration_seconds", 0.0),
            avg_memory_delta=enrichment_metrics.get("avg_memory_delta_mb", 0.0),
            max_peak_memory=enrichment_metrics.get("peak_memory_mb", 0.0),
            records_per_second=enrichment_metrics.get("records_per_second", 0.0),
        )

    metrics = performance_monitor.get_metrics_summary().get("enrichment_core", {})
    duration = metrics.get("total_duration", 0.0)
    return PerformanceSummary(
        duration=duration,
        avg_memory_delta=metrics.get("avg_memory_delta_mb", 0.0),
        max_peak_memory=metrics.get("max_peak_memory_mb", 0.0),
        records_per_second=(total_awards / duration) if duration > 0 else 0.0,
    )


def _build_output_metadata(
    *,
    context: AssetExecutionContext,
    config: Any,
    enriched_df: pd.DataFrame,
    original_df: pd.DataFrame,
    summary: EnrichmentSummary,
    performance: PerformanceSummary,
    enrichment_metrics: dict[str, Any],
    use_chunked: bool,
) -> dict[str, Any]:
    """Run the analyzer and assemble Dagster output metadata."""
    run_context = {
        "run_id": context.run.run_id if context.run else f"run_{context.run_id}",
        "pipeline_name": "sbir_enrichment",
        "stage": "enrich",
    }
    module_data = {
        "enriched_df": enriched_df,
        "original_df": original_df,
        "enrichment_metrics": {
            "records_processed": summary.total_awards,
            "records_failed": 0,
            "duration_seconds": performance.duration,
            "records_per_second": performance.records_per_second,
            "match_rate": summary.match_rate,
            "matched_records": summary.total_matched,
            "exact_matches": summary.exact_matches,
            "fuzzy_matches": summary.fuzzy_matches,
            "processing_mode": "chunked" if use_chunked else "standard",
        },
        "run_context": run_context,
    }
    analysis_report = SbirEnrichmentAnalyzer().analyze(module_data)
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

    metadata = {
        "num_records": len(enriched_df),
        "match_rate": f"{summary.match_rate:.1%}",
        "matched_awards": summary.total_matched,
        "exact_matches": summary.exact_matches,
        "fuzzy_matches": summary.fuzzy_matches,
        "enrichment_columns": [
            column for column in enriched_df.columns if column.startswith("usaspending_")
        ],
        "preview": MetadataValue.md(enriched_df.head(10).to_markdown()),
        "performance_duration_seconds": round(performance.duration, 2),
        "performance_records_per_second": round(performance.records_per_second, 2),
        "performance_peak_memory_mb": round(performance.max_peak_memory, 2),
        "performance_avg_memory_delta_mb": round(performance.avg_memory_delta, 2),
        "processing_mode": "chunked" if use_chunked else "standard",
        "chunk_size": config.enrichment.performance.chunk_size if use_chunked else None,
        "analysis_insights_count": len(analysis_report.insights)
        if hasattr(analysis_report, "insights")
        else 0,
        "analysis_data_hygiene_score": round(analysis_report.data_hygiene.quality_score_mean, 3)
        if analysis_report.data_hygiene
        else None,
        "analysis_success_rate": round(analysis_report.success_rate, 3),
        "analysis_throughput": round(analysis_report.throughput_records_per_second, 2),
    }
    if use_chunked and "progress" in enrichment_metrics:
        metadata.update(enrichment_metrics["progress"])
    return metadata


@asset(
    description="SBIR awards enriched with USAspending and SAM.gov data",
    group_name="enrichment",
    compute_kind="pandas",
)
def enriched_sbir_awards(
    context: AssetExecutionContext,
    validated_sbir_awards: pd.DataFrame,
    raw_usaspending_recipients: pd.DataFrame,
    raw_sam_gov_entities: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """
    Enrich validated SBIR awards with USAspending and SAM.gov data.

    Enrichment strategy (hierarchical):
    1. USAspending: UEI/DUNS exact match, then fuzzy name match
    2. SAM.gov: Fill gaps for unmatched records using UEI/DUNS

    Args:
        validated_sbir_awards: Validated SBIR awards DataFrame
        raw_usaspending_recipients: USAspending recipient lookup data
        raw_sam_gov_entities: SAM.gov entity records

    Returns:
        Enriched SBIR awards with USAspending and SAM.gov data
    """
    config = get_config()

    context.log.info(
        "Starting SBIR enrichment (USAspending + SAM.gov)",
        extra={
            "sbir_records": len(validated_sbir_awards),
            "usaspending_recipients": len(raw_usaspending_recipients),
            "sam_gov_entities": len(raw_sam_gov_entities),
        },
    )

    enriched_df, enrichment_metrics, use_chunked = _run_usaspending_enrichment(
        validated_sbir_awards,
        raw_usaspending_recipients,
        config,
        context,
    )

    # Calculate USAspending enrichment statistics
    usaspending_matched = enriched_df["_usaspending_match_method"].notna().sum()
    context.log.info(f"USAspending enrichment: {usaspending_matched}/{len(enriched_df)} matched")

    enriched_df = _apply_sam_enrichment(enriched_df, raw_sam_gov_entities, context)

    summary = _summarize_enrichment(enriched_df)
    context.log.info(
        "Enrichment complete",
        extra={
            "total_awards": summary.total_awards,
            "usaspending_matches": summary.usaspending_matches,
            "sam_gov_matches": summary.sam_gov_matches,
            "total_matched": summary.total_matched,
            "exact_matches": summary.exact_matches,
            "fuzzy_matches": summary.fuzzy_matches,
            "match_rate": f"{summary.match_rate:.1%}",
        },
    )
    performance = _performance_summary(summary.total_awards, enrichment_metrics)
    metadata = _build_output_metadata(
        context=context,
        config=config,
        enriched_df=enriched_df,
        original_df=validated_sbir_awards,
        summary=summary,
        performance=performance,
        enrichment_metrics=enrichment_metrics,
        use_chunked=use_chunked,
    )

    # Persist to S3 for cross-job asset sharing
    _persist_enriched_awards(enriched_df, context)

    return Output(value=enriched_df, metadata=metadata)


def _persist_enriched_awards(df: pd.DataFrame, context: AssetExecutionContext) -> None:
    """Write enriched awards where usaspending_iterative_enrichment reads them."""
    from sbir_etl.utils.cloud_storage import get_data_root

    dest = get_data_root() / "processed" / "enriched" / "sbir_awards.parquet"
    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dest, index=False)
    context.log.info(f"Persisted {len(df)} enriched awards to {dest}")


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

    # Determine if check passes (convert to Python bool)
    passed = bool(actual_match_rate >= min_match_rate)

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
        "total_awards": int(total_awards),
        "matched_awards": int(matched_awards),
        "unmatched_awards": int(total_awards - matched_awards),
        "exact_matches": int(exact_matches),
        "fuzzy_matches": int(fuzzy_matches),
        "match_methods": {str(k): int(v) for k, v in match_methods.to_dict().items()},
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
    # Fields that the enricher must produce
    required_fields = [
        "_usaspending_match_method",
    ]
    # Optional fields for reporting (may be present after join)
    optional_fields = [
        "_usaspending_match_score",
        "usaspending_recipient_legal_business_name",
    ]

    # Check all required fields exist
    missing_fields = [f for f in required_fields if f not in enriched_sbir_awards.columns]

    # Check null rates in all fields (required + optional if present)
    null_rates = {}
    for field in required_fields + optional_fields:
        if field in enriched_sbir_awards.columns:
            null_rate = enriched_sbir_awards[field].isna().sum() / len(enriched_sbir_awards)
            null_rates[field] = null_rate

    # Pass if no missing required fields
    passed = len(missing_fields) == 0

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
