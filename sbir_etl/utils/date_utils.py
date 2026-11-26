"""Unified date parsing and formatting utilities.

This module provides centralized date parsing and formatting functions that
consolidate duplicate date handling logic across the codebase.

Epistemic tier: primitives. Deterministic parse/format helpers imported by
primitives-tier models; output-changing behavior is a versioned change,
never an edit in place.
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


EPISTEMIC_TIER = "primitives"

# Common date formats in order of preference
COMMON_DATE_FORMATS = [
    "%Y-%m-%d",  # ISO-like: 2023-01-15
    "%m/%d/%Y",  # US format: 01/15/2023
    "%Y/%m/%d",  # ISO-like with slashes: 2023/01/15
    "%m-%d-%Y",  # US format with dashes: 01-15-2023
    "%d/%m/%Y",  # Day-first: 24/07/2025
    "%B %d, %Y",  # Full month name: July 24, 2025
    "%b %d, %Y",  # Abbreviated month: Jul 24, 2025
]

# Date formats with time component
DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",  # ISO-like with time: 2023-01-15 14:30:00
    "%Y/%m/%d %H:%M:%S",  # ISO-like with slashes and time: 2023/01/15 14:30:00
]

# Special formats
EIGHT_DIGIT_FORMAT = "%Y%m%d"  # 20230115

# ISO date regex pattern
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Values that should be treated as None (all lowercase; compared via s.lower())
NULL_VALUES = {"", "\\n", "nan", "nat", "none", "null"}


def parse_date(
    value: Any,
    return_datetime: bool = False,
    strict: bool = False,
    allow_8digit: bool = False,
) -> date | datetime | None:
    """Parse a date value from various input types and formats.

    Supports:
    - date and datetime objects (returned as-is or converted)
    - ISO format strings (YYYY-MM-DD)
    - Common date formats (MM/DD/YYYY, YYYY/MM/DD, etc.)
    - Datetime strings with time components
    - 8-digit format (YYYYMMDD) if allow_8digit=True
    - Pandas Timestamp objects
    - Special null values (empty string, "\\N", "nan", etc.)

    Args:
        value: Value to parse (str, date, datetime, pandas Timestamp, or None)
        return_datetime: If True, return datetime instead of date
        strict: If True, raise ValueError on parse failure; if False, return None
        allow_8digit: If True, try 8-digit format (YYYYMMDD) before other formats

    Returns:
        Parsed date or datetime object, or None if parsing fails and strict=False

    Raises:
        ValueError: If strict=True and parsing fails

    Examples:
        >>> parse_date("2023-01-15")
        datetime.date(2023, 1, 15)
        >>> parse_date("01/15/2023")
        datetime.date(2023, 1, 15)
        >>> parse_date("2023-01-15 14:30:00", return_datetime=True)
        datetime.datetime(2023, 1, 15, 14, 30)
        >>> parse_date(None)
        None
        >>> parse_date("\\N")
        None
    """
    # Handle None and empty values
    if value is None:
        return None

    # Handle date/datetime objects (check datetime first since it's a subclass of date)
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
        # Check for pandas NaT/NaN first (before Timestamp check, since NaT is a Timestamp)
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass

        if isinstance(value, pd.Timestamp):
            # Double-check it's not NaT (isna check above should catch it, but be safe)
            if pd.isna(value):
                return None
            dt = value.to_pydatetime()
            if return_datetime:
                return dt
            return dt.date()

    # Handle string values
    if isinstance(value, str):
        s = value.strip()

        # Check for null values
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
                parsed = datetime.strptime(s, fmt)
                if return_datetime:
                    return parsed
                return parsed.date()
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

        # Try pandas to_datetime as fallback (handles many edge cases)
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

    # Parsing failed
    if strict:
        raise ValueError(f"Could not parse date from value: {value!r}")
    return None


def format_date_iso(value: date | datetime | None) -> str | None:
    """Format a date or datetime object as ISO format string (YYYY-MM-DD).

    Args:
        value: Date, datetime, or None to format

    Returns:
        ISO format string (YYYY-MM-DD) or None if input is None

    Examples:
        >>> format_date_iso(date(2023, 1, 15))
        '2023-01-15'
        >>> format_date_iso(datetime(2023, 1, 15, 14, 30))
        '2023-01-15'
        >>> format_date_iso(None)
        None
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    # Try to parse and format if it's a string or other type
    parsed = parse_date(value)
    if parsed is None:
        return None

    if isinstance(parsed, datetime):
        return parsed.date().isoformat()

    return parsed.isoformat()


def _local_calendar_date(value: Any) -> date | None:
    """Return the calendar date of ``value`` as written, without any timezone conversion."""
    if value is None:
        return None
    if pd is not None:
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass
    # datetime and pandas.Timestamp are date subclasses; their year and month
    # fields are already the local wall-clock values.
    if isinstance(value, date):
        return value
    text = value.strip() if isinstance(value, str) else str(value).strip()
    if not text or text.lower() in NULL_VALUES:
        return None
    if pd is not None:
        parsed = pd.to_datetime(text, errors="coerce")
        return None if pd.isna(parsed) else parsed
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def federal_fiscal_year(value: Any) -> int | None:
    """Return the US federal fiscal year of a date-like value.

    Rule: the federal fiscal year is the calendar year, plus one when the month
    is October or later. FY2024 runs from 2023-10-01 through 2024-09-30.

    A timestamp with a UTC offset uses its local date as written. The value is
    not converted to UTC first. ``2023-09-30T22:00-05:00`` is September 30, so
    it is FY2023, even though the same instant is October 1 in UTC.

    Accepts ``date``, ``datetime``, ``pandas.Timestamp``, ISO strings, and other
    strings that ``pandas.to_datetime`` can parse. Returns ``None`` for
    ``None``, ``NaT``, ``NaN``, null-like strings, and values that do not parse.

    Examples:
        >>> federal_fiscal_year("2023-09-30")
        2023
        >>> federal_fiscal_year("2023-10-01")
        2024
        >>> federal_fiscal_year("2023-09-30T22:00-05:00")
        2023
    """
    local_date = _local_calendar_date(value)
    if local_date is None:
        return None
    return int(local_date.year + (local_date.month >= 10))


def federal_fiscal_year_series(values: pd.Series) -> pd.Series:
    """Vectorized :func:`federal_fiscal_year` over a pandas Series.

    Applies the same rule: local date as written, no UTC conversion. Returns a
    nullable ``Int64`` Series; missing or unparseable values become ``<NA>``.
    A column whose values carry different UTC offsets falls back to the scalar
    function, because pandas cannot hold mixed offsets in one datetime column.
    """
    if pd is None:  # pragma: no cover - pandas is a core dependency
        raise ImportError("federal_fiscal_year_series requires pandas")
    try:
        parsed = pd.to_datetime(values, errors="coerce")
    except (TypeError, ValueError):
        return values.map(federal_fiscal_year).astype("Int64")
    year = parsed.dt.year.astype("Int64")
    return (year + (parsed.dt.month >= 10).astype("Int64")).astype("Int64")
