"""Tests for Phase 2 Form D input normalization."""

from __future__ import annotations

import json

import pytest

from sbir_analytics.assets.agency_private_capital.form_d_inputs import (
    load_form_d_control_universe,
    load_form_d_matches,
    normalize_name,
)


pytestmark = pytest.mark.fast


def _write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def test_normalize_name_uppercases_and_squashes_whitespace() -> None:
    assert normalize_name("  Acme   Corp ") == "ACME CORP"


def test_load_form_d_matches_keeps_high_non_excluded_offerings(tmp_path) -> None:
    path = tmp_path / "form_d_details.jsonl"
    _write_jsonl(
        path,
        [
            {
                "company_name": "Acme Corp",
                "form_d_cik": "0000123",
                "match_confidence": {"tier": "high"},
                "offerings": [
                    {
                        "entity_name": "ACME CORP",
                        "filing_date": "2021-03-01",
                        "state": "CA",
                        "industry_group": "Other Technology",
                        "total_amount_sold": 1_000_000,
                        "total_offering_amount": 2_000_000,
                        "securities_types": ["Equity"],
                    },
                    {
                        "entity_name": "ACME FUND",
                        "filing_date": "2021-04-01",
                        "state": "CA",
                        "industry_group": "Pooled Investment Fund",
                        "total_amount_sold": 9_000_000,
                    },
                ],
            },
            {
                "company_name": "Low Match",
                "form_d_cik": "0000456",
                "match_confidence": {"tier": "low"},
                "offerings": [
                    {
                        "filing_date": "2021-01-01",
                        "state": "MA",
                        "industry_group": "Other Technology",
                        "total_amount_sold": 500,
                    }
                ],
            },
        ],
    )

    df = load_form_d_matches(path, tier_filter={"high"}, year_min=2009, year_max=2024)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["company_key"] == "ACME CORP"
    assert row["form_d_cik"] == "123"
    assert row["total_form_d_raised"] == 1_000_000
    assert row["first_form_d_year"] == 2021


def test_load_form_d_control_universe_excludes_sbir_ciks(tmp_path) -> None:
    path = tmp_path / "controls.jsonl"
    _write_jsonl(
        path,
        [
            {
                "issuer_name": "Control One",
                "cik": "0000999",
                "filing_date": "2020-01-01",
                "state": "CA",
                "industry_group": "Other Technology",
                "total_amount_sold": 2_000_000,
            },
            {
                "issuer_name": "Already SBIR",
                "cik": "0000123",
                "filing_date": "2020-01-01",
                "state": "CA",
                "industry_group": "Other Technology",
                "total_amount_sold": 3_000_000,
            },
        ],
    )

    df = load_form_d_control_universe(path, sbir_ciks={"123"}, year_min=2009, year_max=2024)

    assert len(df) == 1
    assert df.iloc[0]["issuer_key"] == "CONTROL ONE"
    assert df.iloc[0]["form_d_cik"] == "999"


def test_load_form_d_control_universe_dedupes_duplicate_ciks(tmp_path) -> None:
    path = tmp_path / "controls.jsonl"
    _write_jsonl(
        path,
        [
            {
                "issuer_name": "Control One",
                "cik": "0000999",
                "filing_date": "2020-01-01",
                "state": "CA",
                "industry_group": "Other Technology",
                "total_amount_sold": 2_000_000,
            },
            {
                "issuer_name": "Control One Duplicate",
                "cik": "0000999",
                "filing_date": "2021-01-01",
                "state": "CA",
                "industry_group": "Other Technology",
                "total_amount_sold": 3_000_000,
            },
        ],
    )

    df = load_form_d_control_universe(path, sbir_ciks=set(), year_min=2009, year_max=2024)

    assert len(df) == 1
    assert df.iloc[0]["form_d_cik"] == "999"
    assert df.iloc[0]["first_form_d_year"] == 2020
