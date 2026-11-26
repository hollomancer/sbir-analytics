"""Shared helpers for phase-transition assets.

Re-exports the Dagster names the phase-transition asset modules share, matching
the helper pattern in ``sbir_analytics.assets.transition.utils``.
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import Any

import pandas as pd
from dagster import MetadataValue, Output, asset
from loguru import logger


# Centralized path / IO utilities from sbir_etl (re-exported where convenient).
from sbir_etl.utils.data.file_io import write_json
from sbir_etl.utils.identifiers import normalize_duns, normalize_uei
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
    "nullable_str_series",
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


_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def parse_data_cut_date() -> date:
    """Read the data-cut date used for right-censoring survival rows.

    Driven by ``SBIR_ETL__PHASE_TRANSITION__DATA_CUT_DATE`` (ISO YYYY-MM-DD).
    An unset, empty, or blank variable falls back to today in UTC. A set value that is
    not a valid ISO date raises ``ValueError``: silently using today would make
    the censoring cut, and every survival row, depend on the day of the run.
    We intentionally do not clip negative latencies — see the README in this
    package for why.
    """

    raw = env_str("SBIR_ETL__PHASE_TRANSITION__DATA_CUT_DATE")
    if raw is None or not raw.strip():
        return datetime.utcnow().date()
    text = raw.strip()
    try:
        # date.fromisoformat also accepts 20201231 and week dates such as
        # 2020-W01-1, so require the documented YYYY-MM-DD shape first.
        if not _ISO_DATE.fullmatch(text):
            raise ValueError
        return date.fromisoformat(text)
    except ValueError:
        raise ValueError(
            f"SBIR_ETL__PHASE_TRANSITION__DATA_CUT_DATE={raw!r} is not an ISO date (YYYY-MM-DD)"
        ) from None


def coerce_date_series(series: pd.Series) -> pd.Series:
    """Best-effort conversion to datetime64[ns]; non-parseable -> NaT."""

    return pd.to_datetime(series, errors="coerce")


def nullable_str_series(values: Any, index: Any = None) -> pd.Series:
    """Build an object-dtype Series whose missing entries stay ``None``.

    pandas infers the ``str`` dtype for a sequence of strings and rewrites the
    missing entries to ``NaN``, which is a float: it is truthy, it is not
    ``None``, and a pydantic contract typed ``str | None`` rejects it. Columns
    where "absent" is a meaningful value -- an unknown program, an absent
    parent reference -- therefore need an explicit object dtype so that absent
    reads as absent all the way to the row contract.
    """

    series = pd.Series(values, index=index, dtype=object)
    return series.where(series.notna(), None)


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
