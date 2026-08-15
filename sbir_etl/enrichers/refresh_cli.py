"""Operator CLI for iterative enrichment refresh.

Epistemic tier: pipelines. Thin wrapper over ``SourceRefreshRunner``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Any

from sbir_etl.config.loader import get_config
from sbir_etl.enrichers.source_adapter import SourceRefreshRunner
from sbir_etl.enrichers.usaspending.adapter import USAspendingSourceAdapter
from sbir_etl.enrichers.usaspending.requests import (
    AWARD_ID_COLUMNS,
    enriched_awards_path,
    filter_by_window,
    first_present_column,
    has_identifier,
    load_enriched_awards,
    stale_awards_to_requests,
)
from sbir_etl.utils.enrichment.checkpoints import CheckpointStore
from sbir_etl.utils.enrichment.freshness import FreshnessStore


EPISTEMIC_TIER = "pipelines"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh one enrichment source")
    parser.add_argument("--source", required=True, help="Registered enrichment source id")
    parser.add_argument(
        "--window",
        default=None,
        help="Optional START:END window (ISO dates) applied to the award date column.",
    )
    parser.add_argument(
        "--award-id",
        action="append",
        dest="award_ids",
        default=None,
        help="Limit refresh to one or more award ids (repeatable)",
    )
    return parser


def _requests_for_source(
    source: str,
    award_ids: Sequence[str] | None,
    window: str | None = None,
) -> list[dict[str, Any]]:
    config = get_config()
    source_config = getattr(config.enrichment_refresh, source, None)
    if source_config is None:
        raise SystemExit(f"unknown enrichment source: {source}")
    if not source_config.enabled:
        raise SystemExit(f"enrichment source {source} is disabled")
    store = FreshnessStore()
    sla = source_config.sla_staleness_days
    stale = store.get_awards_needing_refresh(source, sla, list(award_ids) if award_ids else None)
    if not stale:
        return []

    # The ledger stores award ids only. Identifiers (UEI / DUNS / CAGE / PIID) live
    # on the enriched award frame, and enrich_award cannot match an award without
    # at least one of them, so join rather than sending bare ids.
    try:
        enriched = load_enriched_awards()
    except Exception as exc:
        raise SystemExit(f"failed to load enriched awards: {exc}") from exc
    if enriched is None or enriched.empty:
        raise SystemExit(
            f"{enriched_awards_path()} is unavailable; refresh needs enriched awards "
            "for recipient identifiers. Materialize sbir_usaspending_enrichment first."
        )
    award_id_col = first_present_column(enriched, AWARD_ID_COLUMNS)
    if not award_id_col:
        raise SystemExit(
            f"no award id column on {enriched_awards_path()}; expected one of {AWARD_ID_COLUMNS}"
        )
    stale_ids = {str(award_id) for award_id in stale}
    stale_frame = enriched.loc[enriched[award_id_col].astype(str).isin(stale_ids)].copy()
    matched_ids = set(stale_frame[award_id_col].astype(str))
    missing_from_enriched = len(stale_ids - matched_ids)
    if missing_from_enriched:
        print(
            f"skipping {missing_from_enriched} stale award(s) absent from enriched awards",
            file=sys.stderr,
        )
    if window:
        stale_frame = filter_by_window(stale_frame, window)

    requests = stale_awards_to_requests(stale_frame)
    usable = [request for request in requests if has_identifier(request)]
    dropped = len(requests) - len(usable)
    if dropped:
        print(f"skipping {dropped} stale award(s) with no usable identifier", file=sys.stderr)
    return usable


def run_refresh(
    *,
    source: str,
    window: str | None = None,
    award_ids: Sequence[str] | None = None,
    runner: SourceRefreshRunner | None = None,
    adapter: Any = None,
) -> dict[str, Any]:
    if source != "usaspending":
        raise SystemExit(
            f"source {source!r} has no adapter yet; implement SourceAdapter to join the runner"
        )
    requests = _requests_for_source(source, award_ids, window)
    freshness = FreshnessStore()
    active_adapter = adapter or USAspendingSourceAdapter(freshness=freshness)
    active_runner = runner or SourceRefreshRunner(
        freshness=freshness,
        checkpoints=CheckpointStore(),
        partition_id=f"{source}-cli",
        checkpoint_interval=get_config().enrichment_refresh.usaspending.checkpoint_interval,
    )
    return active_runner.refresh_records(active_adapter, requests).as_dict()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    stats = run_refresh(source=args.source, window=args.window, award_ids=args.award_ids)
    print(stats)
    return 0 if stats.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
