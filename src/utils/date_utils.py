"""Date parsing and manipulation utilities."""

from datetime import date, datetime

import pandas as pd


def parse_date(
    value: str | date | datetime | pd.Timestamp | None,
    return_datetime: bool = False,
) -> date | datetime | None:
    """
    Parse a date from various input formats.

    Args:
        value: Date value to parse (string, date, datetime, or pandas Timestamp)
        return_datetime: If True, return datetime instead of date

    Returns:
        Parsed date or datetime object, or None if value is None/NaT

    Raises:
        ValueError: If the date string cannot be parsed
    """
    if value is None:
        return None

    # Handle pandas NaT - must check before isinstance checks
    if isinstance(value, (pd.Timestamp, type(pd.NaT))):
        if pd.isna(value):
            return None
        # Valid pandas Timestamp
        dt = value.to_pydatetime()
        return dt if return_datetime else dt.date()

    # Already a datetime - preserve time if return_datetime=True
    if isinstance(value, datetime):
        return value if return_datetime else value.date()

    # Already a date
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time()) if return_datetime else value

    # Parse string
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None

        try:
            # Try ISO format first
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if return_datetime else dt.date()
        except ValueError:
            pass

        try:
            # Try common date formats
            for fmt in ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"]:
                try:
                    dt = datetime.strptime(value, fmt)
                    return dt if return_datetime else dt.date()
                except ValueError:
                    continue
        except Exception:
            pass

        raise ValueError(f"Could not parse date from value: {value!r}")

    raise ValueError(f"Unsupported date type: {type(value)}")
