"""Tests for NIH RePORTER record normalization."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sbir_etl.enrichers.nih_reporter.schema import normalize_reporter_result


pytestmark = pytest.mark.fast

FIXTURE = Path(__file__).parent / "fixtures" / "search_page.json"


def test_normalize_recorded_fixture() -> None:
    payload = json.loads(FIXTURE.read_text())
    record = normalize_reporter_result(payload["results"][0], payload_hash="abc")
    assert record.appl_id == "10824314"
    assert record.fy == 2024
    assert record.upsert_key() == ("1R43AI123456-01", 2024)
    assert record.org_uei == "DPMGH9MG1X67"
    assert record.org_duns == "076580745"
    assert record.pi_names == ("Ada Lovelace",)
    assert record.foa_number == "PA-22-176"
    assert record.study_section == "ZRG1"
    assert record.award_amount == 275000.0
    assert record.source == "nih_reporter"
    assert record.payload_hash == "abc"


def test_normalize_keeps_multiple_org_identifiers() -> None:
    record = normalize_reporter_result(
        {
            "appl_id": 1,
            "fiscal_year": 2023,
            "project_num": "1R44CA000001-01",
            "organization": {
                "org_ueis": ["UEIAAAA11111", "UEIBBBB22222"],
                "primary_duns": "123456789",
            },
        }
    )
    assert record.org_ueis == ("UEIAAAA11111", "UEIBBBB22222")
    assert record.org_duns == "123456789"
    assert record.org_duns_values == ("123456789",)


def test_normalize_requires_appl_id_and_fy() -> None:
    with pytest.raises(ValueError, match="appl_id or fiscal_year"):
        normalize_reporter_result({"project_num": "1R43AI123456-01"})
