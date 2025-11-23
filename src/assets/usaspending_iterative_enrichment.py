"""Dagster assets for USAspending iterative enrichment.

Phase 1: USAspending API only. Other APIs (SAM.gov, NIH RePORTER, PatentsView, etc.)
will be evaluated in Phase 2+.
"""

import asyncio
from typing import Any

import pandas as pd
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    Config,
    OpExecutionContext,
    Output,
    asset,
    asset_check,
    op,
)
from loguru import logger
from pydantic import Field

from ..config.loader import get_config
from ..enrichers.usaspending import USAspendingAPIClient
from ..exceptions import ValidationError
from ..utils.async_tools import run_sync
from ..utils.enrichment_freshness import FreshnessStore, update_freshness_ledger
from ..utils.enrichment_metrics import EnrichmentMetricsCollector


class EnrichmentRefreshConfig(Config):
    """Configuration for enrichment refresh operations."""

    source: str = Field(default="usaspending", description="Enrichment source name")
    award_ids: list[str] | None = Field(
        default=None, description="Optional list of award IDs to refresh"
    )
    force: bool = Field(default=False, description="Force refresh even if not stale")
    batch_size: int | None = Field(default=None, description="Override batch size from config")


@asset(
    description="Freshness ledger tracking enrichment state for all awards",
    group_name="enrichment",
    compute_kind="pandas",
)
def usaspending_freshness_ledger(context: AssetExecutionContext) -> Output[pd.DataFrame]:
    """Load freshness ledger for USAspending enrichment.

    Returns:
        DataFrame with freshness records
    """
    store = FreshnessStore()
    df = store.load_all()

    # Filter to USAspending only
    if not df.empty and "source" in df.columns:
        df = df[df["source"] == "usaspending"]

    context.log.info(f"Loaded {len(df)} USAspending freshness records")

    return Output(
        value=df,
        metadata={
            "total_records": len(df),
            "stale_count": len(df[df["status"] == "stale"]) if not df.empty else 0,
            "success_count": len(df[df["status"] == "success"]) if not df.empty else 0,
        },
    )


@asset(
    description="Awards that need USAspending refresh (exceed SLA)",
    group_name="enrichment",
    compute_kind="pandas",
)
def stale_usaspending_awards(
    context: AssetExecutionContext,
    usaspending_freshness_ledger: pd.DataFrame,
    enriched_sbir_awards: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """Identify awards that need USAspending refresh.

    Args:
        usaspending_freshness_ledger: Freshness records
        enriched_sbir_awards: Enriched SBIR awards

    Returns:
        DataFrame of stale awards with enrichment identifiers
    """
    config = get_config()
    sla_days = config.enrichment_refresh.usaspending.sla_staleness_days

    store = FreshnessStore()
    stale_award_ids = store.get_awards_needing_refresh("usaspending", sla_days)

    if not stale_award_ids:
        context.log.info("No stale awards found")
        return Output(
            value=pd.DataFrame(),
            metadata={"stale_count": 0},
        )

    # Filter enriched awards to stale ones
    from ...utils.asset_column_helper import AssetColumnHelper  # type: ignore[import-not-found]

    award_id_col = AssetColumnHelper.find_award_id_column(enriched_sbir_awards)
    if not award_id_col:
        context.log.warning("Could not find award ID column")
        return Output(value=pd.DataFrame(), metadata={"stale_count": 0})

    stale_df = enriched_sbir_awards[enriched_sbir_awards[award_id_col].isin(stale_award_ids)].copy()

    context.log.info(f"Found {len(stale_df)} stale awards needing refresh")

    return Output(
        value=stale_df,
        metadata={
            "stale_count": len(stale_df),
            "sla_days": sla_days,
        },
    )


@op(
    description="Refresh USAspending enrichment for a batch of awards",
)
def usaspending_refresh_batch(
    context: OpExecutionContext,
    stale_awards_batch: pd.DataFrame,
) -> dict[str, Any]:
    """Refresh USAspending enrichment for a batch of awards.

    Args:
        stale_awards_batch: DataFrame of awards to refresh

    Returns:
        Refresh statistics
    """
    op_config = context.op_config
    source = op_config.get("source", "usaspending")
    batch_size = op_config.get("batch_size")

    config = get_config()
    refresh_config = config.enrichment_refresh.usaspending
    if batch_size is None:
        batch_size = refresh_config.batch_size

    # Initialize API client, freshness store, and metrics collector
    api_client = USAspendingAPIClient()
    store = FreshnessStore()
    metrics_collector = EnrichmentMetricsCollector()

    # Identify award ID and identifier columns
    award_id_col = None
    for col in ["award_id", "Award_ID", "id", "ID"]:
        if col in stale_awards_batch.columns:
            award_id_col = col
            break

    if not award_id_col:
        raise ValidationError(
            "Could not find award ID column",
            component="assets.usaspending_iterative_enrichment",
            operation="enrich_stale_usaspending_records",
            details={
                "expected_columns": ["award_id", "Award_ID", "id", "ID"],
                "available_columns": list(stale_awards_batch.columns),
            },
        )

    uei_col = None
    for col in ["UEI", "uei", "company_uei", "recipient_uei"]:
        if col in stale_awards_batch.columns:
            uei_col = col
            break

    duns_col = None
    for col in ["Duns", "duns", "company_duns", "recipient_duns"]:
        if col in stale_awards_batch.columns:
            duns_col = col
            break

    cage_col = None
    for col in ["CAGE", "cage", "company_cage", "recipient_cage"]:
        if col in stale_awards_batch.columns:
            cage_col = col
            break

    contract_col = None
    for col in ["Contract", "contract", "contract_number", "piid"]:
        if col in stale_awards_batch.columns:
            contract_col = col
            break

    # Process awards in batch
    stats: dict[str, int | list[str]] = {
        "total": len(stale_awards_batch),
        "success": 0,
        "failed": 0,
        "unchanged": 0,
        "errors": [],
    }

    async def process_award(row: pd.Series) -> None:
        """Process a single award."""
        award_id = str(row[award_id_col])
        uei = str(row[uei_col]) if uei_col and pd.notna(row.get(uei_col)) else None
        duns = str(row[duns_col]) if duns_col and pd.notna(row.get(duns_col)) else None
        cage = str(row[cage_col]) if cage_col and pd.notna(row.get(cage_col)) else None
        contract = (
            str(row[contract_col]) if contract_col and pd.notna(row.get(contract_col)) else None
        )

        # Load existing freshness record
        freshness_record = store.get_record(award_id, source)

        try:
            # Enrich award
            result = await api_client.enrich_award(
                award_id=award_id,
                uei=uei,
                duns=duns,
                cage=cage,
                piid=contract,
                freshness_record=freshness_record,
            )

            # Record API call for metrics
            metrics_collector.record_api_call(source, error=not result["success"])

            # Update freshness ledger
            update_freshness_ledger(
                store=store,
                award_id=award_id,
                source=source,
                success=result["success"],
                payload_hash=result.get("payload_hash"),
                metadata=result.get("metadata", {}),
                error_message=result.get("error"),
            )

            if result["success"]:
                if result.get("delta_detected", True):
                    success_val = stats["success"]
                    stats["success"] = (success_val if isinstance(success_val, int) else 0) + 1
                else:
                    unchanged_val = stats["unchanged"]
                    stats["unchanged"] = (unchanged_val if isinstance(unchanged_val, int) else 0) + 1
            else:
                failed_val = stats["failed"]
                stats["failed"] = (failed_val if isinstance(failed_val, int) else 0) + 1
                errors = stats.get("errors")
                if not isinstance(errors, list):
                    errors = []
                    stats["errors"] = errors
                errors.append(f"{award_id}: {result.get('error', 'Unknown error')}")

        except Exception as e:
            logger.error(f"Failed to refresh award {award_id}: {e}")
            failed_val = stats["failed"]
            stats["failed"] = (failed_val if isinstance(failed_val, int) else 0) + 1
            errors = stats.get("errors")
            if not isinstance(errors, list):
                errors = []
                stats["errors"] = errors
            errors.append(f"{award_id}: {str(e)}")

            # Record API error
            metrics_collector.record_api_call(source, error=True)

            # Update freshness record with failure
            update_freshness_ledger(
                store=store,
                award_id=award_id,
                source=source,
                success=False,
                error_message=str(e),
            )

    # Process awards asynchronously (respecting rate limits via client)
    async def process_batch() -> None:
        tasks = [process_award(row) for _, row in stale_awards_batch.iterrows()]
        await asyncio.gather(*tasks)

    run_sync(process_batch())

    context.log.info(
        f"Refresh complete: {stats['success']} success, "
        f"{stats['unchanged']} unchanged, {stats['failed']} failed"
    )

    # Emit freshness metrics
    try:
        metrics_path = metrics_collector.emit_metrics(source)
        context.log.info(f"Emitted freshness metrics to {metrics_path}")
    except Exception as e:
        logger.warning(f"Failed to emit metrics: {e}")

    return stats


@asset_check(
    asset="stale_usaspending_awards",
    description="Check that stale awards are within acceptable threshold",
)
def stale_awards_threshold_check(
    stale_usaspending_awards: pd.DataFrame,
) -> AssetCheckResult:
    """Check that stale awards count is within acceptable threshold."""
    get_config()
    # You could add a threshold to config if needed
    stale_count = len(stale_usaspending_awards)

    # For now, just warn if more than 50% are stale
    # This threshold could be configurable

    # We'd need total awards count for percentage, but for now just check count
    if stale_count > 1000:  # Arbitrary threshold
        return AssetCheckResult(
            passed=False,
            severity=AssetCheckSeverity.ERROR,
            description=f"Too many stale awards: {stale_count}",
            metadata={
                "stale_count": stale_count,
                "threshold": 1000,
            },
        )

    return AssetCheckResult(
        passed=True,
        description=f"Stale awards within threshold: {stale_count}",
        metadata={
            "stale_count": stale_count,
        },
    )
