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
from sbir_etl.utils.enrichment.checkpoints import CheckpointStore
from sbir_etl.utils.enrichment.freshness import FreshnessStore


EPISTEMIC_TIER = "pipelines"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh one enrichment source")
    parser.add_argument("--source", required=True, help="Registered enrichment source id")
    parser.add_argument(
        "--window",
        default=None,
        help="Optional start:end window (ISO dates). Applied when award_date is present.",
    )
    parser.add_argument(
        "--award-id",
        action="append",
        dest="award_ids",
        default=None,
        help="Limit refresh to one or more award ids (repeatable)",
    )
    return parser


def _requests_for_source(source: str, award_ids: Sequence[str] | None) -> list[dict[str, Any]]:
    config = get_config()
    source_config = getattr(config.enrichment_refresh, source, None)
    if source_config is None:
        raise SystemExit(f"unknown enrichment source: {source}")
    if not source_config.enabled and source != "usaspending":
        raise SystemExit(f"enrichment source {source} is disabled")
    store = FreshnessStore()
    sla = source_config.sla_staleness_days
    stale = store.get_awards_needing_refresh(source, sla, list(award_ids) if award_ids else None)
    return [{"award_id": award_id} for award_id in stale]


def run_refresh(
    *,
    source: str,
    window: str | None = None,
    award_ids: Sequence[str] | None = None,
    runner: SourceRefreshRunner | None = None,
    adapter: Any = None,
) -> dict[str, Any]:
    del window  # reserved; date columns are not on the freshness ledger
    if source != "usaspending":
        raise SystemExit(
            f"source {source!r} has no adapter yet; implement SourceAdapter to join the runner"
        )
    requests = _requests_for_source(source, award_ids)
    freshness = FreshnessStore()
    active_adapter = adapter or USAspendingSourceAdapter(freshness=freshness)
    active_runner = runner or SourceRefreshRunner(
        freshness=freshness,
        checkpoints=CheckpointStore(),
        partition_id=f"{source}-cli",
    )
    return active_runner.refresh_records(active_adapter, requests).as_dict()


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    stats = run_refresh(source=args.source, window=args.window, award_ids=args.award_ids)
    print(stats)
    return 0 if stats.get("failed", 0) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
