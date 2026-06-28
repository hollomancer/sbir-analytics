"""Shared ingestion helpers for Dagster assets."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from dagster import AssetExecutionContext

from sbir_etl.utils.cloud_storage import resolve_data_path


def _resolve_tiered_path(
    context: AssetExecutionContext,
    *,
    s3_finder: Callable[[str], str | None],
    local_path_getter: Callable[[], Path | None],
    s3_bucket: str | None,
    use_s3: bool = True,
    label: str,
) -> tuple[Path | None, str | None]:
    """Resolve a data file via S3-first, local-fallback strategy.

    Returns (resolved_path, s3_url) where s3_url is non-None only when S3 was used.
    Both are None if every tier failed.
    """
    if use_s3 and s3_bucket:
        context.log.info(f"Attempting to load {label} from S3 (PRIMARY)")
        s3_url = s3_finder(s3_bucket)
        if s3_url:
            try:
                path = resolve_data_path(s3_url)
                context.log.info(f"Using S3 {label}: {s3_url} -> {path}")
                return path, s3_url
            except Exception as e:
                context.log.warning(f"S3 {label} resolution failed: {e}")

    try:
        local = local_path_getter()
        if local is not None and Path(local).exists():
            context.log.info(f"Using local {label}: {local}")
            return Path(local), None
        if local is not None:
            context.log.warning(f"Local {label} not found: {local}")
    except Exception as e:
        context.log.warning(f"Local {label} path check failed: {e}")

    return None, None
