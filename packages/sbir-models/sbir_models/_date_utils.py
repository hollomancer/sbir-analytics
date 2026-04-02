"""Vendored date parsing utility for standalone sbir-models package.

This is a self-contained copy of the parse_date function from
sbir_etl.utils.date_utils, allowing sbir-models to work
without the full sbir_etl dependency tree.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

# Optional pandas import for Timestamp support
try:
    import pandas as pd
except ImportError:
    pd = None  # type: ignore[assignment, unused-ignore]

# Common date formats in order of preference
COMMON_DATE_FORMATS = [
    "%Y-%m-%d",  # ISO-like: 2023-01-15
    "%m/%d/%Y",  # US format: 01/15/2023
    "%Y/%m/%d",  # ISO-like with slashes: 2023/01/15
    "%m-%d-%Y",  # US format with dashes: 01-15-2023
]

# Date formats with time component
DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
]

EIGHT_DIGIT_FORMAT = "%Y%m%d"
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
NULL_VALUES = {"", "\\N", "nan", "nat", "none", "null", "NULL", "NAN", "NAT"}


def parse_date(
    value: Any,
    return_datetime: bool = False,
    strict: bool = False,
    allow_8digit: bool = False,
) -> date | datetime | None:
    """Parse a date value from various input types and formats.

    Supports date/datetime objects, ISO strings, common date formats,
    datetime strings with time components, 8-digit format (YYYYMMDD),
    pandas Timestamps, and special null values.

    Args:
        value: Value to parse (str, date, datetime, pandas Timestamp, or None)
        return_datetime: If True, return datetime instead of date
        strict: If True, raise ValueError on parse failure; if False, return None
        allow_8digit: If True, try 8-digit format (YYYYMMDD)

    Returns:
        Parsed date or datetime object, or None if parsing fails and strict=False

    Raises:
        ValueError: If strict=True and parsing fails
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        if return_datetime:
            return value
        return value.date()

    if isinstance(value, date):
        if return_datetime:
            return datetime.combine(value, datetime.min.time())
        return value

    # Handle pandas Timestamp and NaT
    if pd is not None:
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass

        if isinstance(value, pd.Timestamp):
            if pd.isna(value):
                return None
            dt = value.to_pydatetime()
            if return_datetime:
                return dt
            return dt.date()

    # Handle string values
    if isinstance(value, str):
        s = value.strip()

        if not s or s.lower() in NULL_VALUES:
            return None

        # Try ISO format first (most common and unambiguous)
        if ISO_DATE_RE.match(s):
            try:
                parsed = date.fromisoformat(s)
                if return_datetime:
                    return datetime.combine(parsed, datetime.min.time())
                return parsed
            except ValueError:
                pass

        # Try 8-digit format if allowed (YYYYMMDD)
        if allow_8digit and len(s) >= 8 and s[:8].isdigit():
            try:
                parsed = datetime.strptime(s[:8], EIGHT_DIGIT_FORMAT).date()
                if return_datetime:
                    return datetime.combine(parsed, datetime.min.time())
                return parsed
            except ValueError:
                pass

        # Try datetime formats (with time component)
        for fmt in DATETIME_FORMATS:
            try:
                parsed_dt = datetime.strptime(s, fmt)
                if return_datetime:
                    return parsed_dt
                return parsed_dt.date()
            except ValueError:
                continue

        # Try common date formats
        for fmt in COMMON_DATE_FORMATS:
            try:
                parsed = datetime.strptime(s, fmt).date()
                if return_datetime:
                    return datetime.combine(parsed, datetime.min.time())
                return parsed
            except ValueError:
                continue

        # Try pandas to_datetime as fallback
        if pd is not None:
            try:
                pd_date = pd.to_datetime(s, errors="raise")
                if hasattr(pd_date, "to_pydatetime"):
                    dt = pd_date.to_pydatetime()
                    if return_datetime:
                        return dt
                    return dt.date()
            except (ValueError, TypeError):
                pass

    if strict:
        raise ValueError(f"Could not parse date from value: {value!r}")
    return None
