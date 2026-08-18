"""Dagster assets for NIH RePORTER iterative enrichment.

Epistemic tier: pipelines. Shared lifecycle stays on SourceRefreshRunner.
No sensor and no schedule — keep enrichment_refresh.nih_reporter.enabled false
until a hand run succeeds.
"""

from typing import Any

import pandas as pd
from dagster import AssetExecutionContext, Config, Output, asset
from loguru import logger
from pydantic import Field

from sbir_etl.config.loader import get_config
from sbir_etl.enrichers.nih_reporter.adapter import NIHReporterSourceAdapter
from sbir_etl.enrichers.nih_reporter.requests import (
    build_nih_reporter_requests,
    frame_to_nih_requests,
    load_sbir_award_frame,
    nih_ids_needing_refresh,
)
from sbir_etl.enrichers.source_adapter import SourceAdapter, SourceRefreshRunner
from sbir_etl.utils.enrichment.checkpoints import CheckpointStore
from sbir_etl.utils.enrichment.freshness import FreshnessStore
from sbir_etl.utils.enrichment.metrics import EnrichmentMetricsCollector


class NIHReporterRefreshConfig(Config):
    """Run config for a NIH RePORTER refresh pass."""

    award_ids: list[str] | None = Field(
        default=None, description="Optional list of award IDs to refresh"
    )
    batch_size: int | None = Field(default=None, description="Override batch size from config")
    window: str | None = Field(
        default=None,
        description="RePORTER criteria window (YYYY-MM-DD:YYYY-MM-DD or fy:YYYY-YYYY)",
    )


@asset(
    description="Freshness ledger tracking NIH RePORTER enrichment state",
    group_name="enrichment",
    compute_kind="pandas",
)
def nih_reporter_freshness_ledger(context: AssetExecutionContext) -> Output[pd.DataFrame]:
    """Load freshness ledger rows for the nih_reporter source."""

    store = FreshnessStore()
    df = store.load_all()
    if not df.empty and "source" in df.columns:
        df = df[df["source"] == "nih_reporter"]
    context.log.info(f"Loaded {len(df)} NIH RePORTER freshness records")
    return Output(
        value=df,
        metadata={
            "total_records": len(df),
            "success_count": len(df[df["status"] == "success"]) if not df.empty else 0,
        },
    )


@asset(
    description="SBIR.gov NIH/HHS awards that need a RePORTER refresh",
    group_name="enrichment",
    compute_kind="pandas",
)
def stale_nih_reporter_awards(
    context: AssetExecutionContext,
    nih_reporter_freshness_ledger: pd.DataFrame,
) -> Output[pd.DataFrame]:
    """Build exact-key requests for unseen or stale NIH/HHS awards.

    An empty freshness ledger is a first run: every eligible SBIR.gov NIH/HHS
    award is selected. Missing SBIR.gov CSV fails closed.
    """

    del nih_reporter_freshness_ledger
    try:
        awards = load_sbir_award_frame()
    except FileNotFoundError as exc:
        raise RuntimeError(str(exc)) from exc

    requests, skipped = build_nih_reporter_requests(awards)
    if skipped:
        context.log.warning(
            f"Skipping {skipped} NIH/HHS award(s) with no usable project key or year"
        )
    config = get_config()
    sla_days = config.enrichment_refresh.nih_reporter.sla_staleness_days
    selected_ids = nih_ids_needing_refresh(
        FreshnessStore(),
        [request["award_id"] for request in requests],
        sla_days,
    )
    selected = [request for request in requests if request["award_id"] in selected_ids]
    stale_df = pd.DataFrame(selected)
    context.log.info(f"Found {len(stale_df)} NIH RePORTER awards needing refresh")
    return Output(
        value=stale_df,
        metadata={"stale_count": len(stale_df), "sla_days": sla_days, "skipped": skipped},
    )


def build_nih_reporter_adapter(*, freshness: FreshnessStore) -> SourceAdapter:
    """Factory so tests can inject a hermetic adapter without constructing the client."""

    return NIHReporterSourceAdapter(freshness=freshness)


@asset(
    description="Refresh NIH RePORTER enrichment for stale awards via SourceRefreshRunner",
    group_name="enrichment",
    compute_kind="python",
)
def nih_reporter_refresh_batch(
    context: AssetExecutionContext,
    stale_nih_reporter_awards: pd.DataFrame,
    config: NIHReporterRefreshConfig,
) -> Output[dict[str, Any]]:
    """Refresh NIH RePORTER enrichment for a batch of awards."""

    empty_stats = {
        "total": 0,
        "success": 0,
        "failed": 0,
        "unchanged": 0,
        "skipped": 0,
        "errors": [],
    }
    refresh_config = get_config().enrichment_refresh.nih_reporter
    if not refresh_config.enabled:
        context.log.warning("nih_reporter is disabled; skipping refresh")
        return Output(value=empty_stats, metadata={"stale_count": 0, "reason": "disabled"})
    if stale_nih_reporter_awards.empty:
        context.log.info("No stale NIH RePORTER awards — skipping refresh")
        return Output(value=empty_stats, metadata={"stale_count": 0, "reason": "no_stale_awards"})

    requests = frame_to_nih_requests(stale_nih_reporter_awards)
    if config.award_ids:
        wanted = {str(award_id) for award_id in config.award_ids}
        requests = [request for request in requests if request["award_id"] in wanted]
    if config.window:
        for request in requests:
            request["window"] = config.window
    batch_size = config.batch_size or refresh_config.batch_size
    requests = requests[:batch_size]

    store = FreshnessStore()
    adapter = build_nih_reporter_adapter(freshness=store)
    metrics_collector = EnrichmentMetricsCollector()
    runner = SourceRefreshRunner(
        freshness=store,
        checkpoints=CheckpointStore(),
        metrics=metrics_collector,
        partition_id="nih-reporter-default",
        checkpoint_interval=refresh_config.checkpoint_interval,
    )
    stats = runner.refresh_records(adapter, requests).as_dict()
    context.log.info(
        f"NIH RePORTER refresh complete: {stats['success']} success, "
        f"{stats['unchanged']} unchanged, {stats['failed']} failed"
    )
    try:
        metrics_path = metrics_collector.emit_metrics("nih_reporter")
        context.log.info(f"Emitted freshness metrics to {metrics_path}")
    except Exception as e:
        logger.warning(f"Failed to emit metrics: {e}")
    return Output(value=stats, metadata={k: v for k, v in stats.items() if k != "errors"})
