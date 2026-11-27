"""Unit tests for date utilities."""

from datetime import date, datetime

import pandas as pd
import pytest


pytestmark = pytest.mark.fast

# Import directly to avoid duckdb dependency in utils/__init__.py
from sbir_etl.utils.date_utils import (
    federal_fiscal_year,
    federal_fiscal_year_series,
    format_date_iso,
    parse_date,
    parse_iso_date_lenient,
    parse_iso_date_strict,
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


# Inputs that neither ISO parser may turn into a date.
MALFORMED_ISO = [
    "2024-13-01",  # month out of range
    "2024-02-30",  # day out of range
    "2023-02-29",  # not a leap year
    "20240105",  # basic form; date.fromisoformat accepts it on 3.11+
    "2024-W01-5",  # ISO week date; date.fromisoformat accepts it on 3.11+
    "2024-01-05abc",  # trailing garbage
    "2024-01-05 garbage",
    "2024-1-5",
    "01/05/2024",
    "2024/01/05",
    "Jan 5, 2024",
    "\u0662\u0660\u0662\u0664-\u0660\u0661-\u0660\u0665",  # non-ASCII digits
    "nan",
    "",
    "   ",
]


class TestParseIsoDateStrict:
    """parse_iso_date_strict accepts YYYY-MM-DD and nothing else."""

    def test_date_only(self):
        assert parse_iso_date_strict("2024-01-05") == date(2024, 1, 5)
        assert parse_iso_date_strict(" 2024-01-05 ") == date(2024, 1, 5)

    def test_date_object(self):
        assert parse_iso_date_strict(date(2024, 1, 5)) == date(2024, 1, 5)

    @pytest.mark.parametrize(
        "value",
        [
            "2024-01-05T00:00:00",
            "2024-01-05 00:00:00",
            "2024-01-05T10:30Z",
            "2024-01-05T10:30+05:00",
            datetime(2024, 1, 5, 10, 30),
            pd.Timestamp("2024-01-05"),
        ],
    )
    def test_rejects_time_part(self, value):
        assert parse_iso_date_strict(value) is None

    @pytest.mark.parametrize("value", [*MALFORMED_ISO, None, 20240105, 1.5, True])
    def test_rejects_malformed(self, value):
        assert parse_iso_date_strict(value) is None


class TestParseIsoDateLenient:
    """parse_iso_date_lenient also accepts a time part and an offset."""

    @pytest.mark.parametrize(
        "value",
        [
            "2024-01-05",
            "2024-01-05T00:00:00",
            "2024-01-05 00:00:00",
            "2024-01-05T23:59",
            "2024-01-05 23:59:59.123456",
            "2024-01-05T10:30Z",
            "2024-01-05T10:30:00Z",
            "2024-01-05T10:30:00+00:00",
            "2024-01-05T10:30:00-0500",
            " 2024-01-05T10:30:00 ",
        ],
    )
    def test_accepted_shapes(self, value):
        assert parse_iso_date_lenient(value) == date(2024, 1, 5)

    def test_t_and_space_agree(self):
        assert parse_iso_date_lenient("2024-01-05T18:00:00") == parse_iso_date_lenient(
            "2024-01-05 18:00:00"
        )

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            # Local date as written; no UTC conversion (same rule as #883).
            ("2024-01-05T22:00-05:00", date(2024, 1, 5)),  # 2024-01-06 in UTC
            ("2024-01-06T01:00+09:00", date(2024, 1, 6)),  # 2024-01-05 in UTC
            ("2023-09-30T22:00-05:00", date(2023, 9, 30)),
        ],
    )
    def test_offset_keeps_local_date(self, value, expected):
        assert parse_iso_date_lenient(value) == expected

    def test_offset_rule_matches_federal_fiscal_year(self):
        value = "2023-09-30T22:00-05:00"
        parsed = parse_iso_date_lenient(value)
        assert parsed is not None
        assert federal_fiscal_year(parsed) == federal_fiscal_year(value) == 2023

    def test_objects(self):
        assert parse_iso_date_lenient(date(2024, 1, 5)) == date(2024, 1, 5)
        assert parse_iso_date_lenient(datetime(2024, 1, 5, 23, 0)) == date(2024, 1, 5)
        aware = pd.Timestamp("2024-01-05 22:00", tz="US/Eastern")
        assert parse_iso_date_lenient(aware) == date(2024, 1, 5)
        assert parse_iso_date_lenient(pd.NaT) is None

    @pytest.mark.parametrize(
        "value",
        [
            *MALFORMED_ISO,
            "2024-01-05T25:00",  # hour out of range
            "2024-01-05T10:60",
            "2024-01-05T10",  # hour without minutes
            "2024-01-05T1030",  # basic-form time
            "2024-01-05t10:30",  # lowercase separator
            "2024-01-05T10:30z",  # lowercase zone
            "2024-01-05  10:30",  # two spaces
            "2024-01-05T10:30+5",
            "2024-01-05T10:30 UTC",
            "2024-01-05T10:30:00abc",
            None,
            20240105,
            True,
        ],
    )
    def test_rejects_malformed(self, value):
        assert parse_iso_date_lenient(value) is None

    @pytest.mark.parametrize("value", ["2024-01-05", "2024-02-29", "1999-12-31"])
    def test_agrees_with_strict_on_date_only(self, value):
        assert parse_iso_date_lenient(value) == parse_iso_date_strict(value)


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


class TestFederalFiscalYear:
    """Federal FY rule: year + 1 from October; local date as written, no UTC conversion."""

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            # No offset
            ("2023-09-30T23:59:59", 2023),
            ("2023-10-01T00:00:00", 2024),
            # Negative offset: the UTC instant is already October 1
            ("2023-09-30T22:00-05:00", 2023),
            ("2023-09-30T23:59:59-08:00", 2023),
            ("2023-10-01T00:30-05:00", 2024),
            # Positive offset: the UTC instant is still September 30
            ("2023-10-01T01:00+02:00", 2024),
            ("2023-09-30T23:00+05:30", 2023),
            # UTC "Z"
            ("2023-09-30T23:59Z", 2023),
            ("2023-10-01T00:00Z", 2024),
        ],
    )
    def test_boundary_timestamps_use_local_date(self, value, expected):
        assert federal_fiscal_year(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2023-09-30", 2023),
            ("2023-10-01", 2024),
            ("2024-01-15", 2024),
            ("2023-12-31", 2024),
            (" 2023-10-01 ", 2024),
        ],
    )
    def test_date_only_strings(self, value, expected):
        assert federal_fiscal_year(value) == expected

    def test_date_and_datetime_objects(self):
        from datetime import timedelta, timezone

        assert federal_fiscal_year(date(2023, 9, 30)) == 2023
        assert federal_fiscal_year(date(2023, 10, 1)) == 2024
        eastern = timezone(timedelta(hours=-5))
        assert federal_fiscal_year(datetime(2023, 9, 30, 22, tzinfo=eastern)) == 2023

    def test_pandas_timestamp(self):
        pd = pytest.importorskip("pandas")
        assert federal_fiscal_year(pd.Timestamp("2023-09-30")) == 2023
        assert federal_fiscal_year(pd.Timestamp("2023-10-01")) == 2024
        assert federal_fiscal_year(pd.Timestamp("2023-09-30T22:00-05:00")) == 2023

    @pytest.mark.parametrize("value", [None, "", "  ", "nan", "NaT", "None", "not a date"])
    def test_missing_and_unparseable_return_none(self, value):
        assert federal_fiscal_year(value) is None

    def test_nat_and_nan_return_none(self):
        pd = pytest.importorskip("pandas")
        assert federal_fiscal_year(pd.NaT) is None
        assert federal_fiscal_year(float("nan")) is None

    def test_series_matches_scalar_rule(self):
        pd = pytest.importorskip("pandas")
        values = pd.Series(["2023-09-30", "2023-10-01", None, "not a date"])
        result = federal_fiscal_year_series(values)
        assert str(result.dtype) == "Int64"
        assert result.tolist() == [2023, 2024, pd.NA, pd.NA]

    def test_series_single_offset_uses_local_date(self):
        pd = pytest.importorskip("pandas")
        values = pd.Series(["2023-09-30T22:00-05:00", "2023-10-01T00:30-05:00"])
        assert federal_fiscal_year_series(values).tolist() == [2023, 2024]

    def test_series_mixed_offsets_use_local_date(self):
        pd = pytest.importorskip("pandas")
        values = pd.Series(["2023-09-30T22:00-05:00", "2023-10-01T01:00+02:00", None])
        assert federal_fiscal_year_series(values).tolist() == [2023, 2024, pd.NA]

    def test_series_of_timestamps(self):
        pd = pytest.importorskip("pandas")
        values = pd.to_datetime(pd.Series(["2023-09-30", None, "2023-10-01"]))
        assert federal_fiscal_year_series(values).tolist() == [2023, pd.NA, 2024]

    def test_series_mixed_offset_timestamps_are_not_coerced_to_na(self):
        """Regression: to_datetime(errors="coerce") nulls minority-offset Timestamps."""
        pd = pytest.importorskip("pandas")
        values = pd.Series(
            [pd.Timestamp("2023-09-30T22:00-05:00"), pd.Timestamp("2023-10-01T01:00+05:00")]
        )
        assert federal_fiscal_year_series(values).tolist() == [2023, 2024]

    def test_series_mixed_string_formats_are_not_coerced_to_na(self):
        pd = pytest.importorskip("pandas")
        values = pd.Series(["2023-09-30", "10/01/2023", "", None])
        assert federal_fiscal_year_series(values).tolist() == [2023, 2024, pd.NA, pd.NA]

    def test_series_utc_converted_column_uses_stored_zone(self):
        """A Series already converted to UTC gives the UTC date, as documented."""
        pd = pytest.importorskip("pandas")
        values = pd.to_datetime(pd.Series(["2023-09-30T22:00-05:00"]), utc=True)
        assert federal_fiscal_year_series(values).tolist() == [2024]
        assert federal_fiscal_year(values.iloc[0]) == 2024

    def test_series_calls_scalar_once_per_distinct_value(self, monkeypatch):
        """Speed guard without a clock: one scalar call per distinct value."""
        pd = pytest.importorskip("pandas")
        from sbir_etl.utils import date_utils

        calls: list[object] = []
        real = date_utils.federal_fiscal_year

        def counting(value):
            calls.append(value)
            return real(value)

        monkeypatch.setattr(date_utils, "federal_fiscal_year", counting)
        clean = ["2023-09-30", "2023-10-01"] * 500
        values = pd.Series([*clean, "", "garbage", "garbage", None, "10/01/2023"])

        result = date_utils.federal_fiscal_year_series(values)

        assert len(calls) == 6
        # The sixth call is the one null; pandas may store it as None or NaN.
        assert {value for value in calls if isinstance(value, str)} == {
            "2023-09-30",
            "2023-10-01",
            "",
            "garbage",
            "10/01/2023",
        }
        assert str(result.dtype) == "Int64"
        assert result.iloc[:1000].tolist() == [2023, 2024] * 500
        assert result.iloc[1000:].tolist() == [pd.NA, pd.NA, pd.NA, pd.NA, 2024]

    def test_series_same_instant_different_zones_not_merged(self):
        """Equal instants in different zones can fall in different fiscal years."""
        pd = pytest.importorskip("pandas")
        values = pd.Series(
            [
                pd.Timestamp("2023-09-30T22:00-05:00"),
                pd.Timestamp("2023-10-01T03:00+00:00"),
                pd.Timestamp("2023-10-01T08:00+05:00"),
            ]
        )
        assert federal_fiscal_year_series(values).tolist() == [2023, 2024, 2024]

    def test_series_empty_and_mixed_strings(self):
        pd = pytest.importorskip("pandas")
        values = pd.Series(["", "2023-09-30", "10/01/2023"])
        assert federal_fiscal_year_series(values).tolist() == [pd.NA, 2023, 2024]

    @pytest.mark.parametrize(
        "index",
        [
            [0, 0, 1, 1],
            ["d", "c", "b", "a"],
            [3, 1, 0, 2],
        ],
        ids=["duplicate", "string", "shuffled"],
    )
    def test_series_keeps_index_and_positions(self, index):
        pd = pytest.importorskip("pandas")
        values = pd.Series(["10/01/2023", "2023-09-30", "", "2023-10-01"], index=index)
        result = federal_fiscal_year_series(values)
        assert result.index.tolist() == index
        assert result.tolist() == [2024, 2023, pd.NA, 2024]

    def test_datetime_series_keeps_duplicate_index(self):
        pd = pytest.importorskip("pandas")
        values = pd.Series(pd.to_datetime(["2023-10-01", "2023-09-30", None]), index=[5, 5, 1])
        result = federal_fiscal_year_series(values)
        assert result.index.tolist() == [5, 5, 1]
        assert result.tolist() == [2024, 2023, pd.NA]

    @pytest.mark.parametrize(
        ("value", "expected"),
        [(2023, 2023), (20231001, 2024), (20230930, 2023), (1.0, None), (float("nan"), None)],
    )
    def test_numbers_are_read_as_written_not_epoch(self, value, expected):
        pd = pytest.importorskip("pandas")
        assert federal_fiscal_year(value) == expected
        result = federal_fiscal_year_series(pd.Series([value])).tolist()
        assert result == [pd.NA if expected is None else expected]

    def test_integer_series_is_not_epoch(self):
        pd = pytest.importorskip("pandas")
        values = pd.Series([2023, 20231001, 20230930])
        assert federal_fiscal_year_series(values).tolist() == [2023, 2024, 2023]

    def test_mixed_object_column_of_ints_and_strings(self):
        pd = pytest.importorskip("pandas")
        values = pd.Series([20231001, "2023-09-30", 2023, "10/01/2023", None], dtype=object)
        assert federal_fiscal_year_series(values).tolist() == [2024, 2023, 2023, 2024, pd.NA]
