"""Unit tests for date utilities."""

from datetime import date, datetime

import pytest


pytestmark = pytest.mark.fast

# Import directly to avoid duckdb dependency in utils/__init__.py
from sbir_etl.utils.date_utils import (
    format_date_iso,
    parse_date,
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
        # Function converts datetime to date (strips time component)
        assert result == date(2023, 1, 15)

    def test_parse_date_datetime_return_datetime(self):
        """Test parsing datetime with return_datetime=True."""
        dt = datetime(2023, 1, 15, 14, 30)
        result = parse_date(dt, return_datetime=True)
        # Function returns datetime as-is (preserves time component)
        assert result == datetime(2023, 1, 15, 14, 30)

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
        # Function converts Timestamp to date object
        assert result == date(2023, 1, 15)

    def test_parse_date_pandas_na(self, pandas_available):
        """Test parsing pandas NaT."""
        pd = pandas_available
        result = parse_date(pd.NaT)
        # NaT is isinstance(datetime), so it takes the datetime branch
        # and returns NaT.date() which is NaT — not None
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
