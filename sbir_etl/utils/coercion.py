"""Generic type-coercion helpers shared across ETL modules."""

from __future__ import annotations

from typing import Any

import pandas as pd

# Explicit pandas NA singleton types — avoids pd.isna() on arrays/lists
# which returns an ambiguous boolean array and triggers DeprecationWarning.
_PANDAS_NA_TYPES = (type(pd.NA), type(pd.NaT))


def _blank(value: Any) -> bool:
    """Return True for None, NaN, pd.NA, pd.NaT, or whitespace-only strings."""
    if value is None:
        return True
    if isinstance(value, _PANDAS_NA_TYPES):
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return isinstance(value, str) and not value.strip()


def _to_float(value: Any) -> float | None:
    """Parse value to float, stripping currency symbols and commas. Returns None if blank."""
    if _blank(value):
        return None
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    """Parse value to int (via float, to handle '1.0' strings). Returns None if blank."""
    if _blank(value):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _to_str(value: Any) -> str | None:
    """Strip value to str. Returns None if blank."""
    if _blank(value):
        return None
    return str(value).strip()
