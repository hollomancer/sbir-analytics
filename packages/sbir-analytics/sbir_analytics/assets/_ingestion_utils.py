"""Shared ingestion helpers for Dagster assets."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
from dagster import AssetExecutionContext


def _resolve_tiered_path(
    context: AssetExecutionContext,
    *,
    discover: Callable[[], str | None],
    local_path_getter: Callable[[], Path | None],
    label: str,
) -> tuple[Path | None, str | None]:
    """Resolve a data file: configured local path first, then discovery.

    Returns (resolved_path, discovered_path) where the second element is
    non-None only when discovery under the data root supplied the file rather
    than the configured path. Both are None if every tier failed.
    """
    try:
        local = local_path_getter()
        if local is not None and Path(local).exists():
            context.log.info(f"Using local {label}: {local}")
            return Path(local), None
        if local is not None:
            context.log.warning(f"Local {label} not found: {local}")
    except Exception as e:
        context.log.warning(f"Local {label} path check failed: {e}")

    context.log.info(f"Attempting to discover {label} under the data root")
    try:
        discovered = discover()
        if discovered and Path(discovered).exists():
            context.log.info(f"Discovered {label}: {discovered}")
            return Path(discovered), discovered
    except Exception as e:
        context.log.warning(f"{label} discovery failed: {e}")

    return None, None


def stamp_provenance(df: pd.DataFrame, source: str, url: str) -> None:
    """Set data_source, data_source_url, and ingested_at columns on df in-place."""
    df["data_source"] = source
    df["data_source_url"] = url
    df["ingested_at"] = datetime.now(UTC)
