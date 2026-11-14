"""Focused tests for the staged SBIR enrichment asset."""

from unittest.mock import Mock

import pandas as pd
import pytest
from dagster import build_asset_context

from sbir_analytics.assets import sbir_usaspending_enrichment as enrichment


def test_build_sam_indexes_normalizes_identifiers() -> None:
    sam_entities = pd.DataFrame(
        {
            "unique_entity_id": [" abc123 ", None],
            "duns_number": ["12-34", "000 567"],
        },
        index=[10, 20],
    )

    by_uei, by_duns = enrichment._build_sam_indexes(sam_entities)

    assert by_uei == {"ABC123": 10}
    assert by_duns == {"1234": 10, "000567": 20}


def test_apply_sam_enrichment_separates_fallback_from_naics_only() -> None:
    enriched_awards = pd.DataFrame(
        {
            "_usaspending_match_method": [pd.NA, "uei-exact"],
            "uei": ["abc123", "other"],
            "duns": [None, None],
            "UEI": ["ABC123", "def456"],
            "Duns": [None, None],
        }
    )
    sam_entities = pd.DataFrame(
        {
            "unique_entity_id": ["ABC123", "DEF456"],
            "legal_business_name": ["Fallback Corp", "NAICS Corp"],
            "primary_naics": ["541715", "334511"],
        }
    )

    result = enrichment._apply_sam_enrichment(
        enriched_awards,
        sam_entities,
        build_asset_context(),
    )

    assert result["_sam_gov_match_method"].tolist() == ["sam-uei-exact", "sam-naics-uei"]
    assert result["_enrichment_source"].tolist() == ["sam_gov", "usaspending"]
    assert result["_naics_source"].tolist() == ["sam_gov", "sam_gov"]
    assert result["sam_gov_primary_naics"].tolist() == ["541715", "334511"]
    assert "_sam_gov_match_idx" not in result.columns


def test_apply_sam_enrichment_covers_duns_conflicts_and_unmatched_rows() -> None:
    enriched_awards = pd.DataFrame(
        {
            "_usaspending_match_method": [
                pd.NA,
                pd.NA,
                pd.NA,
                "uei-exact",
                "uei-exact",
                "name-fuzzy",
            ],
            # Lowercase columns drive SAM fallback for USAspending misses.
            "uei": ["U1", "", "", "unused", "unused", "unused"],
            "duns": ["222", "222", "", "", "", ""],
            # Source-style columns drive NAICS-only enrichment for existing matches.
            "UEI": ["unused", "unused", "unused", "U1", "", ""],
            "Duns": ["", "", "", "222", "222", ""],
        }
    )
    sam_entities = pd.DataFrame(
        {
            "unique_entity_id": ["U1", "U2"],
            "duns_number": ["111", "222"],
            "legal_business_name": ["UEI Corp", "DUNS Corp"],
            "primary_naics": ["541715", "334511"],
        }
    )

    result = enrichment._apply_sam_enrichment(
        enriched_awards,
        sam_entities,
        build_asset_context(),
    )

    methods = result["_sam_gov_match_method"]
    assert methods.iloc[:2].tolist() == ["sam-uei-exact", "sam-duns-exact"]
    assert pd.isna(methods.iloc[2])
    assert methods.iloc[3:5].tolist() == ["sam-naics-uei", "sam-naics-duns"]
    assert pd.isna(methods.iloc[5])

    # UEI has precedence when a different DUNS also matches.
    assert result.loc[0, "sam_gov_legal_business_name"] == "UEI Corp"
    assert result.loc[3, "sam_gov_legal_business_name"] == "UEI Corp"
    assert result.loc[1, "sam_gov_legal_business_name"] == "DUNS Corp"
    assert result.loc[4, "sam_gov_legal_business_name"] == "DUNS Corp"

    assert result["_enrichment_source"].tolist() == [
        "sam_gov",
        "sam_gov",
        None,
        "usaspending",
        "usaspending",
        "usaspending",
    ]
    assert result["_naics_source"].tolist()[:5] == [
        "sam_gov",
        "sam_gov",
        None,
        "sam_gov",
        "sam_gov",
    ]
    assert result["_naics_source"].iloc[5] is None


def test_filter_recipients_handles_empty_input() -> None:
    recipients = pd.DataFrame(columns=["uei", "duns"])
    result = enrichment._filter_recipients_by_sbir(
        pd.DataFrame({"uei": ["ABC"]}),
        recipients,
        build_asset_context(),
    )

    assert result.empty
    assert result.columns.tolist() == ["uei", "duns"]


def test_persist_enriched_awards_propagates_write_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "sbir_etl.utils.cloud_storage.get_data_root",
        lambda: tmp_path,
    )
    frame = pd.DataFrame({"award_id": ["A-1"]})
    to_parquet = Mock(side_effect=OSError("disk full"))
    monkeypatch.setattr(frame, "to_parquet", to_parquet)

    with pytest.raises(OSError, match="disk full"):
        enrichment._persist_enriched_awards(frame, build_asset_context())


def test_summarize_enrichment_preserves_reported_counts() -> None:
    frame = pd.DataFrame(
        {
            "_usaspending_match_method": ["uei-exact", "name-fuzzy", pd.NA],
            "_sam_gov_match_method": ["sam-naics-uei", pd.NA, "sam-duns-exact"],
        }
    )

    summary = enrichment._summarize_enrichment(frame)

    assert summary.total_awards == 3
    assert summary.usaspending_matches == 2
    assert summary.sam_gov_matches == 2
    assert summary.total_matched == 4
    assert summary.exact_matches == 1
    assert summary.fuzzy_matches == 1
    assert summary.match_rate == pytest.approx(4 / 3)
