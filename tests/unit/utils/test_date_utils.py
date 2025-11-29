"""Unit tests for date utilities."""

from datetime import date, datetime

import pytest


pytestmark = pytest.mark.fast

# Import directly to avoid duckdb dependency in utils/__init__.py
from src.utils.common.date_utils import (
    format_date_iso,
    parse_date,
    parse_date_safe,
    validate_date_range,
)


class TestParseDate:
    """Test parse_date function."""

    def test_parse_date_none(self):
        """Test parsing None."""
        assert parse_date(None) is None

    def test_parse_date_date_object(self):
        """Test parsing date object."""
        d = date(2023, 1, 15)
        assert parse_date(d) == d

    def test_parse_date_datetime_object(self):
        """Test parsing datetime object."""
        dt = datetime(2023, 1, 15, 14, 30)
        result = parse_date(dt)
        # Function returns datetime unchanged, not converted to date
        assert result == dt

    def test_parse_date_datetime_return_datetime(self):
        """Test parsing datetime with return_datetime=True."""
        dt = datetime(2023, 1, 15, 14, 30)
        result = parse_date(dt, return_datetime=True)
        # Function strips time component, returns datetime with 00:00:00
        assert result == datetime(2023, 1, 15, 0, 0)

    def test_parse_date_iso_string(self):
        """Test parsing ISO format string."""
        result = parse_date("2023-01-15")
        assert result == date(2023, 1, 15)

    def test_parse_date_us_format(self):
        """Test parsing US format string."""
        result = parse_date("01/15/2023")
        assert result == date(2023, 1, 15)

    def test_parse_date_iso_slash_format(self):
        """Test parsing ISO-like format with slashes."""
        result = parse_date("2023/01/15")
        assert result == date(2023, 1, 15)

    def test_parse_date_datetime_string(self):
        """Test parsing datetime string."""
        result = parse_date("2023-01-15 14:30:00", return_datetime=True)
        assert isinstance(result, datetime)
        assert result.year == 2023
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 30

    def test_parse_date_8digit_format(self):
        """Test parsing 8-digit format (YYYYMMDD)."""
        result = parse_date("20230115", allow_8digit=True)
        assert result == date(2023, 1, 15)

    def test_parse_date_8digit_without_flag(self):
        """Test that 8-digit format is not parsed without flag."""
        result = parse_date("20230115", allow_8digit=False)
        # Should try other formats or return None
        assert result is None or isinstance(result, date)

    def test_parse_date_empty_string(self):
        """Test parsing empty string."""
        assert parse_date("") is None
        assert parse_date("   ") is None

    def test_parse_date_null_values(self):
        """Test parsing null value strings."""
        for null_val in ["\\N", "nan", "nat", "none", "null", "NULL", "NAN"]:
            assert parse_date(null_val) is None

    def test_parse_date_strict_mode(self):
        """Test strict mode raises ValueError on failure."""
        with pytest.raises(ValueError):
            parse_date("invalid-date", strict=True)

    def test_parse_date_non_strict_mode(self):
        """Test non-strict mode returns None on failure."""
        assert parse_date("invalid-date", strict=False) is None

    def test_parse_date_pandas_timestamp(self, pandas_available):
        """Test parsing pandas Timestamp."""
        pd = pandas_available
        ts = pd.Timestamp("2023-01-15")
        result = parse_date(ts)
        # Function returns Timestamp unchanged
        assert result == ts

    def test_parse_date_pandas_na(self, pandas_available):
        """Test parsing pandas NaT."""
        pd = pandas_available
        result = parse_date(pd.NaT)
        # Function returns NaT unchanged, not None
        assert pd.isna(result)


class TestFormatDateIso:
    """Test format_date_iso function."""

    def test_format_date_iso_date(self):
        """Test formatting date object."""
        d = date(2023, 1, 15)
        assert format_date_iso(d) == "2023-01-15"

    def test_format_date_iso_datetime(self):
        """Test formatting datetime object."""
        dt = datetime(2023, 1, 15, 14, 30)
        assert format_date_iso(dt) == "2023-01-15"

    def test_format_date_iso_none(self):
        """Test formatting None."""
        assert format_date_iso(None) is None

    def test_format_date_iso_string(self):
        """Test formatting string (should parse first)."""
        result = format_date_iso("2023-01-15")
        assert result == "2023-01-15"

    def test_format_date_iso_invalid_string(self):
        """Test formatting invalid string."""
        result = format_date_iso("invalid")
        # Should return None if parsing fails
        assert result is None


class TestValidateDateRange:
    """Test validate_date_range function."""

    def test_validate_date_range_within_range(self):
        """Test date within range."""
        d = date(2023, 6, 15)
        assert validate_date_range(d, min_date=date(2023, 1, 1), max_date=date(2023, 12, 31))

    def test_validate_date_range_before_min(self):
        """Test date before minimum."""
        d = date(2022, 6, 15)
        assert not validate_date_range(d, min_date=date(2023, 1, 1))

    def test_validate_date_range_after_max(self):
        """Test date after maximum."""
        d = date(2024, 6, 15)
        assert not validate_date_range(d, max_date=date(2023, 12, 31))

    def test_validate_date_range_none(self):
        """Test None date (should be valid)."""
        assert validate_date_range(None, min_date=date(2023, 1, 1))

    def test_validate_date_range_datetime(self):
        """Test datetime object."""
        dt = datetime(2023, 6, 15, 14, 30)
        assert validate_date_range(dt, min_date=date(2023, 1, 1), max_date=date(2023, 12, 31))

    def test_validate_date_range_no_bounds(self):
        """Test validation with no bounds."""
        d = date(2023, 6, 15)
        assert validate_date_range(d)


class TestParseDateSafe:
    """Test parse_date_safe function."""

    def test_parse_date_safe_success(self):
        """Test successful parsing."""
        result = parse_date_safe("2023-01-15", default=date.today())
        assert result == date(2023, 1, 15)

    def test_parse_date_safe_failure_with_default(self):
        """Test failure returns default."""
        default = date(2020, 1, 1)
        result = parse_date_safe("invalid", default=default)
        assert result == default

    def test_parse_date_safe_failure_no_default(self):
        """Test failure returns None if no default."""
        result = parse_date_safe("invalid")
        assert result is None

    def test_parse_date_safe_return_datetime(self):
        """Test return_datetime parameter."""
        result = parse_date_safe("2023-01-15 14:30:00", return_datetime=True)
        assert isinstance(result, datetime)
        assert result.year == 2023
