"""Dagster assets for USAspending iterative enrichment.

Phase 1: USAspending API only. Other APIs (SAM.gov, NIH RePORTER, PatentsView, etc.)
will be evaluated in Phase 2+.
"""

from typing import Any

import pandas as pd
from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    Config,
    Output,
    asset,
    asset_check,
)
from loguru import logger
from pydantic import Field

from sbir_etl.config.loader import get_config
from sbir_etl.enrichers.source_adapter import SourceAdapter, SourceRefreshRunner
from sbir_etl.enrichers.usaspending import USAspendingSourceAdapter
from sbir_etl.exceptions import ValidationError
from sbir_etl.utils.enrichment.checkpoints import CheckpointStore
from sbir_etl.utils.enrichment.freshness import FreshnessStore
from sbir_etl.utils.enrichment.metrics import EnrichmentMetricsCollector


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


def _load_enriched_awards(context: AssetExecutionContext) -> pd.DataFrame | None:
    """Load enriched SBIR awards written by sbir_usaspending_enrichment."""
    from sbir_etl.utils.cloud_storage import get_data_root

    src = get_data_root() / "processed" / "enriched" / "sbir_awards.parquet"
    if not src.is_file():
        context.log.info(f"No enriched awards at {src}")
        return None
    try:
        df = pd.read_parquet(src)
        context.log.info(f"Loaded {len(df)} enriched awards from {src}")
        return df
    except Exception as e:
        context.log.warning(f"Failed to load enriched awards from {src}: {e}")
        return None


@asset(
    description="Awards that need USAspending refresh (exceed SLA)",
    group_name="enrichment",
    compute_kind="pandas",
)
def stale_usaspending_awards(
    context: AssetExecutionContext,
    usaspending_freshness_ledger: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """Identify awards that need USAspending refresh.

    Loads enriched awards from S3 if available. If no enriched data exists,
    returns empty DataFrame (no awards to refresh yet).

    Args:
        usaspending_freshness_ledger: Freshness records

    Returns:
        DataFrame of stale awards with enrichment identifiers
    """
    # Load enriched awards from S3
    enriched_sbir_awards = _load_enriched_awards(context)
    if enriched_sbir_awards is None or enriched_sbir_awards.empty:
        context.log.info("No enriched awards available - nothing to refresh")
        return Output(
            value=pd.DataFrame(),
            metadata={"stale_count": 0, "reason": "no_enriched_data"},
        )

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
    from sbir_etl.utils.asset_column_helper import AssetColumnHelper

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


def _first_present_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in frame.columns:
            return col
    return None


def stale_awards_to_requests(stale_awards: pd.DataFrame) -> list[dict[str, Any]]:
    """Map a stale-award frame to runner request dicts."""

    if stale_awards.empty:
        return []
    award_id_col = _first_present_column(stale_awards, ["award_id", "Award_ID", "id", "ID"])
    if not award_id_col:
        raise ValidationError(
            "Could not find award ID column",
            component="assets.usaspending_iterative_enrichment",
            operation="enrich_stale_usaspending_records",
            details={
                "expected_columns": ["award_id", "Award_ID", "id", "ID"],
                "available_columns": list(stale_awards.columns),
            },
        )
    uei_col = _first_present_column(stale_awards, ["UEI", "uei", "company_uei", "recipient_uei"])
    duns_col = _first_present_column(
        stale_awards, ["Duns", "duns", "company_duns", "recipient_duns"]
    )
    cage_col = _first_present_column(
        stale_awards, ["CAGE", "cage", "company_cage", "recipient_cage"]
    )
    contract_col = _first_present_column(
        stale_awards, ["Contract", "contract", "contract_number", "piid"]
    )
    requests: list[dict[str, Any]] = []
    for _, row in stale_awards.iterrows():
        requests.append(
            {
                "award_id": str(row[award_id_col]),
                "uei": row[uei_col] if uei_col else None,
                "duns": row[duns_col] if duns_col else None,
                "cage": row[cage_col] if cage_col else None,
                "piid": row[contract_col] if contract_col else None,
            }
        )
    return requests


def build_usaspending_adapter(*, freshness: FreshnessStore) -> SourceAdapter:
    """Factory so tests can inject a hermetic adapter without constructing the client."""

    return USAspendingSourceAdapter(freshness=freshness)


@asset(
    description="Refresh USAspending enrichment for stale awards via SourceRefreshRunner",
    group_name="enrichment",
    compute_kind="python",
)
def usaspending_refresh_batch(
    context: AssetExecutionContext,
    stale_usaspending_awards: pd.DataFrame,
    config: EnrichmentRefreshConfig,
) -> Output[dict[str, Any]]:
    """Refresh USAspending enrichment for a batch of awards."""

    source = config.source or "usaspending"
    store = FreshnessStore()
    if stale_usaspending_awards.empty:
        context.log.info("No stale awards — skipping refresh")
        return Output(
            value={
                "total": 0,
                "success": 0,
                "failed": 0,
                "unchanged": 0,
                "skipped": 0,
                "errors": [],
            },
            metadata={"stale_count": 0, "reason": "no_stale_awards"},
        )

    requests = stale_awards_to_requests(stale_usaspending_awards)
    refresh_config = get_config().enrichment_refresh.usaspending
    batch_size = config.batch_size or refresh_config.batch_size
    requests = requests[:batch_size]

    adapter = build_usaspending_adapter(freshness=store)
    metrics_collector = EnrichmentMetricsCollector()
    runner = SourceRefreshRunner(
        freshness=store,
        checkpoints=CheckpointStore(),
        metrics=metrics_collector,
        partition_id="usaspending-default",
    )
    stats = runner.refresh_records(adapter, requests).as_dict()

    context.log.info(
        f"Refresh complete: {stats['success']} success, "
        f"{stats['unchanged']} unchanged, {stats['failed']} failed"
    )
    try:
        metrics_path = metrics_collector.emit_metrics(source)
        context.log.info(f"Emitted freshness metrics to {metrics_path}")
    except Exception as e:
        logger.warning(f"Failed to emit metrics: {e}")

    return Output(value=stats, metadata={k: v for k, v in stats.items() if k != "errors"})


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
