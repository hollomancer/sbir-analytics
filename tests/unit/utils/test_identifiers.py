"""Tests for canonical domain identifier normalization."""

import numpy as np
import pandas as pd
import pytest

from sbir_etl.utils.identifiers import (
    DunsProfile,
    normalize_duns,
    normalize_naics,
    normalize_uei,
    normalize_uspto_identifier,
)


pytestmark = pytest.mark.fast


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("us123", "US123"),
        ("  US 123  ", "US123"),
        ("US-123.456/789", "US-123456789"),
        ("app_123", "APP_123"),
        (12345, "12345"),
        (".", ""),
    ],
)
def test_normalize_uspto_identifier_preserves_ingestion_contract(value, expected) -> None:
    assert normalize_uspto_identifier(value) == expected


# DUNS_V1 is the default and must not change output. Each row pins today's result.
DUNS_V1_TABLE = [
    (None, None),
    ("", None),
    ("   ", None),
    (float("nan"), None),
    ("123456789", "123456789"),
    (" 123-456-789 ", "123456789"),
    ("012345678", "012345678"),
    (123456789, "123456789"),
    (12345678, None),
    ("12345678", None),
    ("12345678.0", "123456780"),
    (12345678.0, "123456780"),
    (123456789.0, None),
    ("1234567890", None),
    ("000000000", "000000000"),
    ("999999999", "999999999"),
    ("N/A", None),
    ("NONE", None),
    ("123456789A", "123456789"),
]


@pytest.mark.parametrize(("value", "expected"), DUNS_V1_TABLE)
def test_duns_v1_output_is_unchanged(value, expected) -> None:
    assert normalize_duns(value) == expected
    assert normalize_duns(value, profile=DunsProfile.DUNS_V1) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("123456789", "123456789"),
        (" 123-456-789 ", "123456789"),
        ("012345678", "012345678"),
        (123456789, "123456789"),
        (np.int64(12345678), "012345678"),
        (12345678, "012345678"),
        (12345678.0, "012345678"),
        (np.float64(12345678.0), "012345678"),
        (123456789.0, "123456789"),
        ("12345678.0", "012345678"),
        (" 123456789.00 ", "123456789"),
    ],
)
def test_duns_v2_happy_path(value, expected) -> None:
    assert normalize_duns(value, profile=DunsProfile.DUNS_V2) == expected


def test_duns_v2_float_artifact_does_not_become_a_different_duns() -> None:
    key = normalize_duns("12345678.0", profile=DunsProfile.DUNS_V2)
    assert key != "123456780"
    assert key == "012345678"


@pytest.mark.parametrize(
    "value",
    [
        "N/A",
        "NONE",
        "000000000",
        "999999999",
        0,
        0.0,
        "0.0",
        "111111111",
        None,
        "",
        float("nan"),
        pd.NA,
        True,
    ],
)
def test_duns_v2_placeholders_and_missing_values_produce_no_key(value) -> None:
    assert normalize_duns(value, profile=DunsProfile.DUNS_V2) is None


@pytest.mark.parametrize(
    "value",
    [
        "123456789A",
        "1A2B3C4D5E6F7G8H9",
        "12345678.9",
        12345678.9,
        "1234567.89",
        "１２３４５６７８９",  # full-width digits pass str.isdigit but are not a DUNS
        "１２３４５６７８.0",
        "123.456.789",
        "DUNS 123456789",
        -123456789,
        -12345678.0,
        float("inf"),
    ],
)
def test_duns_v2_does_not_pull_digits_out_of_a_malformed_value(value) -> None:
    assert normalize_duns(value, profile=DunsProfile.DUNS_V2) is None


@pytest.mark.parametrize("profile", list(DunsProfile))
@pytest.mark.parametrize("value", ["12345678", "1234567", " 12345678 "])
def test_short_duns_text_stays_invalid(profile, value) -> None:
    # Text sources keep leading zeros, so a short string is a truncated DUNS.
    assert normalize_duns(value, profile=profile) is None


@pytest.mark.parametrize("profile", list(DunsProfile))
@pytest.mark.parametrize("value", ["1234567890", "1234567890.0", "123456789-0001"])
def test_long_duns_does_not_match_its_9_digit_prefix(profile, value) -> None:
    assert normalize_duns(value, profile=profile) is None


def test_duns_profile_accepts_its_string_value() -> None:
    assert normalize_duns("12345678.0", profile="duns-v2") == "012345678"  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        normalize_duns("123456789", profile="duns-v3")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("abc123def456", "ABC123DEF456"),
        (" ABC-123-DEF-456 ", "ABC123DEF456"),
        (None, None),
        ("", None),
        (float("nan"), None),
    ],
)
def test_normalize_uei_happy_path(value, expected) -> None:
    assert normalize_uei(value) == expected


@pytest.mark.parametrize("value", ["ABC123DEF45", "ABC123DEF4567", "N/A"])
def test_uei_of_wrong_length_does_not_match_its_12_character_prefix(value) -> None:
    assert normalize_uei(value) is None
    assert normalize_uei(value) != "ABC123DEF456"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("54", "54"),
        ("541", "541"),
        ("5417", "5417"),
        ("54171", "54171"),
        ("541712", "541712"),
        ("  541712  ", "541712"),
        ("541712.0", "541712"),
        ("5417.00", "5417"),
        (541712, "541712"),
        (541712.0, "541712"),
        (np.int64(5417), "5417"),
        (np.float64(541712.0), "541712"),
    ],
)
def test_normalize_naics_accepts_2_to_6_digits_without_padding(value, expected) -> None:
    assert normalize_naics(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "   ",
        pd.NA,
        float("nan"),
        "0",
        "5",
        "1234567",
        "5417120",
        "54-17",
        "54 17",
        "abc",
        "NAICS:5417",
        "541712.5",
        541712.5,
        "005417",
        "054171",
        -5417,
        True,
        "\u0665\u0664",  # Arabic-Indic digits are not ASCII digits
    ],
)
def test_normalize_naics_rejects_malformed_values(value) -> None:
    assert normalize_naics(value) is None
