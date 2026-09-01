"""Tests for C3 collision join."""

from __future__ import annotations

import pytest

from sbir_etl.enrichers.ma_discovery.collision import apply_c3, dates_collide
from sbir_etl.enrichers.ma_discovery.confidence import assign_confidence
from sbir_etl.enrichers.ma_discovery.extractor import ExtractionVerdict


pytestmark = pytest.mark.fast


def test_dates_collide_within_thirty_days() -> None:
    assert dates_collide("2024-03-01", "2024-03-20")
    assert not dates_collide("2024-03-01", "2024-05-01")
    assert dates_collide(None, None)
    assert not dates_collide("2024-03-01", None)


def test_assign_confidence_requires_date_for_medium() -> None:
    undated = ExtractionVerdict(confirmed=True, reason="keyword", acquisition_date=None)
    dated = ExtractionVerdict(
        confirmed=True, reason="llm", acquisition_date="2024-03-12", value_usd=None
    )
    valued = ExtractionVerdict(
        confirmed=True,
        reason="llm",
        acquisition_date="2024-03-12",
        value_usd=1.0,
    )
    assert assign_confidence(undated, source_count=3) == "low"
    assert assign_confidence(dated, source_count=1) == "medium"
    assert assign_confidence(valued, source_count=2) == "high"


def test_c3_inserts_when_no_existing_row() -> None:
    result = apply_c3(
        [],
        [
            {
                "company_name": "Aether Photonics",
                "acquirer": "Helios Defense",
                "event_date": "2024-03-12",
                "confidence": "medium",
                "source": "https://example.com/a",
            }
        ],
    )
    assert len(result.inserted) == 1
    assert result.inserted[0]["signals"]["discovery_confirmed"] is True
    assert result.inserted[0]["confidence"] == "medium"


def test_c3_promotes_medium_to_high() -> None:
    existing = [
        {
            "company_name": "Aether Photonics, Inc.",
            "acquirer": "Helios Defense",
            "event_date": "2024-03-01",
            "confidence": "medium",
            "signals": {"efts_acquisition_text": True},
        }
    ]
    result = apply_c3(
        existing,
        [
            {
                "company_name": "Aether Photonics",
                "acquirer": "Helios Defense",
                "event_date": "2024-03-12",
                "confidence": "medium",
            }
        ],
    )
    assert result.rows[0]["confidence"] == "high"
    assert result.rows[0]["signals"]["discovery_confirmed"] is True
    assert len(result.promoted) == 1


def test_c3_does_not_overwrite_form_d_acquirer() -> None:
    existing = [
        {
            "company_name": "Aether Photonics",
            "acquirer": "Form D Buyer LLC",
            "event_date": "2024-03-12",
            "confidence": "high",
            "form_d_detail": {"filing_date": "2024-03-12"},
            "signals": {"form_d_business_combination": True},
        }
    ]
    result = apply_c3(
        existing,
        [
            {
                "company_name": "Aether Photonics",
                "acquirer": "Helios Defense",
                "event_date": "2024-03-12",
                "confidence": "high",
            }
        ],
    )
    assert result.rows[0]["acquirer"] == "Form D Buyer LLC"
    assert result.rows[0]["signals"]["discovered_acquirer_disagrees"] == "Helios Defense"
    assert result.promoted == []
