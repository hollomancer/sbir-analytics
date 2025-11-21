"""Unified date parsing and formatting utilities.

This module provides centralized date parsing and formatting functions that
consolidate duplicate date handling logic across the codebase.
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
    "%Y-%m-%d %H:%M:%S",  # ISO-like with time: 2023-01-15 14:30:00
    "%Y/%m/%d %H:%M:%S",  # ISO-like with slashes and time: 2023/01/15 14:30:00
]

# Special formats
EIGHT_DIGIT_FORMAT = "%Y%m%d"  # 20230115

# ISO date regex pattern
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Values that should be treated as None
NULL_VALUES = {"", "\\N", "nan", "nat", "none", "null", "NULL", "NAN", "NAT"}


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

    # Handle date/datetime objects
    if isinstance(value, date):
        if return_datetime:
            return datetime.combine(value, datetime.min.time())
        return value

    if isinstance(value, datetime):
        if return_datetime:
            return value
        return value.date()

    # Handle pandas Timestamp
    if pd is not None:
        if isinstance(value, pd.Timestamp):
            dt = value.to_pydatetime()
            if return_datetime:
                return dt
            return dt.date()

        # Check for pandas NaT/NaN
        try:
            if pd.isna(value):
                return None
        except (TypeError, ValueError):
            pass

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


def validate_date_range(
    date_value: date | datetime | None,
    min_date: date | None = None,
    max_date: date | None = None,
) -> bool:
    """Validate that a date is within a specified range.

    Args:
        date_value: Date to validate
        min_date: Minimum allowed date (inclusive)
        max_date: Maximum allowed date (inclusive)

    Returns:
        True if date is within range (or None if date_value is None), False otherwise

    Examples:
        >>> validate_date_range(date(2023, 6, 15), min_date=date(2023, 1, 1), max_date=date(2023, 12, 31))
        True
        >>> validate_date_range(date(2022, 6, 15), min_date=date(2023, 1, 1))
        False
    """
    if date_value is None:
        return True  # None is considered valid (missing data)

    # Convert datetime to date
    if isinstance(date_value, datetime):
        date_value = date_value.date()

    if min_date is not None and date_value < min_date:
        return False

    if max_date is not None and date_value > max_date:
        return False

    return True


def parse_date_safe(
    value: Any,
    default: date | None = None,
    return_datetime: bool = False,
) -> date | datetime | None:
    """Safely parse a date, returning a default value on failure.

    This is a convenience wrapper around parse_date() that never raises exceptions.

    Args:
        value: Value to parse
        default: Default value to return on parse failure (default: None)
        return_datetime: If True, return datetime instead of date

    Returns:
        Parsed date/datetime or default value

    Examples:
        >>> parse_date_safe("2023-01-15", default=date.today())
        datetime.date(2023, 1, 15)
        >>> parse_date_safe("invalid", default=date.today())
        datetime.date(2024, 1, 1)  # or current date
    """
    try:
        result = parse_date(value, return_datetime=return_datetime, strict=False)
        return result if result is not None else default
    except Exception:
        return default
