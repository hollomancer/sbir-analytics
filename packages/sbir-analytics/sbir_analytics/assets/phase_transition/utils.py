"""Shared helpers for phase-transition assets.

Mirrors the Dagster import shim / helper pattern used in
``sbir_analytics.assets.transition.utils`` so these assets remain importable
without Dagster installed (e.g. during unit tests).
"""

from __future__ import annotations

import os
from datetime import date, datetime
from typing import Any

import pandas as pd
from loguru import logger


try:
    from dagster import MetadataValue, Output, asset
except Exception:  # pragma: no cover - test-only shim

    def asset(*args: Any, **kwargs: Any):  # type: ignore[override]
        def _wrap(fn):
            return fn

        return _wrap

    class Output:  # type: ignore[override]
        def __init__(self, value: Any, metadata: dict | None = None) -> None:
            self.value = value
            self.metadata = metadata or {}

    class MetadataValue:  # type: ignore[override]
        @staticmethod
        def json(v: Any) -> Any:
            return v


# Centralized path / IO utilities from sbir_etl (re-exported where convenient).
from sbir_etl.utils.data.file_io import write_json
from sbir_etl.utils.path_utils import ensure_parent_dir


__all__ = [
    "Output",
    "MetadataValue",
    "asset",
    "write_json",
    "ensure_parent_dir",
    "logger",
    "now_utc_iso",
    "env_str",
    "parse_data_cut_date",
    "coerce_date_series",
    "normalize_uei",
    "normalize_duns",
    "load_parquet_if_exists",
]


def now_utc_iso() -> str:
    """UTC timestamp in ISO-8601 seconds precision."""

    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def env_str(key: str, default: str | None = None) -> str | None:
    """Lightweight env-var lookup that treats empty strings as unset."""

    v = os.getenv(key)
    if v is None or v == "":
        return default
    return v


def parse_data_cut_date() -> date:
    """Read the data-cut date used for right-censoring survival rows.

    Driven by ``SBIR_ETL__PHASE_TRANSITION__DATA_CUT_DATE`` (ISO YYYY-MM-DD).
    Falls back to today in UTC. We intentionally do not clip negative
    latencies — see the README in this package for why.
    """

    raw = env_str("SBIR_ETL__PHASE_TRANSITION__DATA_CUT_DATE")
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError:
            logger.warning(
                "Invalid SBIR_ETL__PHASE_TRANSITION__DATA_CUT_DATE={!r}; using today", raw
            )
    return datetime.utcnow().date()


def coerce_date_series(series: pd.Series) -> pd.Series:
    """Best-effort conversion to datetime64[ns]; non-parseable -> NaT."""

    return pd.to_datetime(series, errors="coerce")


def normalize_uei(v: Any) -> str | None:
    """Return a 12-char alnum uppercased UEI, or None."""

    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = "".join(ch for ch in str(v) if ch.isalnum()).upper()
    return s if len(s) == 12 else None


def normalize_duns(v: Any) -> str | None:
    """Return a 9-digit DUNS string, or None."""

    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    digits = "".join(ch for ch in str(v) if ch.isdigit())
    return digits if len(digits) == 9 else None


def load_parquet_if_exists(path: str | os.PathLike[str]) -> pd.DataFrame | None:
    """Load a parquet file if it exists; otherwise return None."""

    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("Failed to read parquet at {}: {}", p, e)
        return None
