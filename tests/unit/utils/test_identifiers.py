"""Tests for canonical domain identifier normalization."""

import pytest

from sbir_etl.utils.identifiers import normalize_uspto_identifier


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
