"""Unit tests for USAspending match logic."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from src.enrichers.usaspending import enrich_sbir_with_usaspending


pytestmark = pytest.mark.fast


@pytest.fixture
def sample_sbir_data() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Company": "Acme Innovations Inc",
                "UEI": "A1B2C3D4E5F6G7H8",
                "Duns": "123456789",
                "Contract": "C-2023-0001",
            },
            {
                "Company": "BioTech Laboratories LLC",
                "UEI": "B2C3D4E5F6G7H8I9",
                "Duns": "987654321",
                "Contract": "C-2023-0002",
            },
            {
                "Company": "NanoWorks Corp",
                "UEI": "N3O4W5R6K7S8T9U0",
                "Duns": "555666777",
                "Contract": "C-2023-0003",
            },
        ]
    )


@pytest.fixture
def sample_usaspending_data() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "recipient_name": "Acme Innovations Inc",
                "recipient_uei": "A1B2C3D4E5F6G7H8",
                "recipient_duns": "123456789",
                "recipient_city": "Springfield",
                "recipient_state": "IL",
            },
            {
                "recipient_name": "BioTech Laboratories LLC",
                "recipient_uei": "B2C3D4E5F6G7H8I9",
                "recipient_duns": "987654321",
                "recipient_city": "Boston",
                "recipient_state": "MA",
            },
            {
                "recipient_name": "Nano Works Corporation",
                "recipient_uei": "",
                "recipient_duns": "",
                "recipient_city": "Austin",
                "recipient_state": "TX",
            },
        ]
    )


def test_exact_uei_match(sample_sbir_data: pd.DataFrame, sample_usaspending_data: pd.DataFrame) -> None:
    enriched = enrich_sbir_with_usaspending(sample_sbir_data, sample_usaspending_data)
    assert enriched["_usaspending_match_method"].iloc[0] == "uei-exact"
    assert enriched["_usaspending_match_score"].iloc[0] == 100
    assert enriched["usaspending_recipient_recipient_city"].iloc[0] == "Springfield"


def test_exact_duns_match(sample_sbir_data: pd.DataFrame, sample_usaspending_data: pd.DataFrame) -> None:
    enriched = enrich_sbir_with_usaspending(sample_sbir_data, sample_usaspending_data)
    assert enriched["_usaspending_match_method"].iloc[1] == "duns-exact"
    assert enriched["_usaspending_match_score"].iloc[1] == 100


def test_fuzzy_match(sample_sbir_data: pd.DataFrame, sample_usaspending_data: pd.DataFrame) -> None:
    enriched = enrich_sbir_with_usaspending(
        sample_sbir_data,
        sample_usaspending_data,
        high_threshold=80,
        low_threshold=60,
    )
    assert enriched["_usaspending_match_method"].iloc[2].startswith("name-fuzzy")
    assert enriched["_usaspending_match_score"].iloc[2] >= 60


def test_no_match_returns_nan() -> None:
    sbir_df = pd.DataFrame(
        [
            {
                "Company": "Missing Co",
                "UEI": "UEI-MISSING",
                "Duns": "",
                "Contract": "C-000",
            }
        ]
    )
    empty_df = pd.DataFrame(
        [
            {
                "recipient_name": "Different",
                "recipient_uei": "UEI-OTHER",
                "recipient_duns": "000",
            }
        ]
    )
    enriched = enrich_sbir_with_usaspending(sbir_df, empty_df)
    assert pd.isna(enriched["_usaspending_match_method"].iloc[0])
    assert pd.isna(enriched["_usaspending_match_score"].iloc[0])


def test_return_candidates(sample_sbir_data: pd.DataFrame, sample_usaspending_data: pd.DataFrame) -> None:
    enriched = enrich_sbir_with_usaspending(
        sample_sbir_data,
        sample_usaspending_data,
        return_candidates=True,
    )
    candidates_json = enriched["_usaspending_match_candidates"].iloc[2]
    if pd.notna(candidates_json):
        candidates = json.loads(candidates_json)
        assert candidates
        assert {"idx", "score"} <= candidates[0].keys()


def test_match_rate_bounds(sample_sbir_data: pd.DataFrame, sample_usaspending_data: pd.DataFrame) -> None:
    enriched = enrich_sbir_with_usaspending(sample_sbir_data, sample_usaspending_data)
    total = len(enriched)
    matched = enriched["_usaspending_match_method"].notna().sum()
    match_rate = matched / total if total else 0
    assert 0 <= match_rate <= 1


def test_exact_matches_have_full_score(
    sample_sbir_data: pd.DataFrame, sample_usaspending_data: pd.DataFrame
) -> None:
    enriched = enrich_sbir_with_usaspending(sample_sbir_data, sample_usaspending_data)
    mask = enriched["_usaspending_match_method"].str.contains("exact", na=False)
    if mask.any():
        assert (enriched.loc[mask, "_usaspending_match_score"] == 100).all()
