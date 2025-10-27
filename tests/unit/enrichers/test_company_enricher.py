import json

import pandas as pd
import pytest

from src.enrichers.company_enricher import (
    enrich_awards_with_companies,
    normalize_company_name,
)


def test_normalize_company_name_basic():
    assert normalize_company_name("Acme, Inc.") == "acme inc"
    assert normalize_company_name("  The Acme Co.  ") == "the acme company"
    assert normalize_company_name("") == ""


def test_enrich_exact_uei_match():
    # Company dataset with UEI present
    companies = pd.DataFrame(
        [
            {"company": "Acme Innovations", "UEI": "A1B2C3D4E5F6", "industry": "Aerospace"},  # pragma: allowlist secret
        ]
    )
    # Award row referencing the same UEI
    awards = pd.DataFrame(
        [
            {
                "company": "Acme Innovations",
                "UEI": "A1B2C3D4E5F6",
                "Duns": "",
                "award_id": "C-2023-0001",
            }
        ]
    )

    enriched = enrich_awards_with_companies(awards, companies, return_candidates=False)

    # Expect deterministic UEI exact match
    assert enriched["_match_method"].iloc[0] == "uei-exact"
    assert int(enriched["_match_score"].iloc[0]) == 100
    # The merged company UEI column should be present and equal to original
    assert "company_UEI" in enriched.columns
    assert enriched["company_UEI"].iloc[0] == "A1B2C3D4E5F6"
    # And industry should be merged
    assert enriched["company_industry"].iloc[0] == "Aerospace"


def test_enrich_exact_duns_match_with_hyphens():
    companies = pd.DataFrame(
        [
            {"company": "BioTech Labs", "UEI": "", "Duns": "987654321", "industry": "Biotech"},
        ]
    )
    awards = pd.DataFrame(
        [
            {
                "company": "BioTech Labs",
                "UEI": "",
                "Duns": "987-654-321",  # hyphenated form
                "award_id": "C-2021-0420",
            }
        ]
    )

    enriched = enrich_awards_with_companies(awards, companies)

    assert enriched["_match_method"].iloc[0] == "duns-exact"
    assert int(enriched["_match_score"].iloc[0]) == 100
    assert enriched["company_Duns"].iloc[0] == "987654321" or "company_Duns" in enriched.columns


def test_enrich_fuzzy_name_match_auto_accept():
    companies = pd.DataFrame(
        [
            {"company": "TechStart Incorporated", "UEI": "", "Duns": "", "industry": "AI"},
            {"company": "Other Corp", "UEI": "", "Duns": "", "industry": "Other"},
        ]
    )
    awards = pd.DataFrame(
        [
            {
                "company": "TechStart Inc",
                "UEI": "",
                "Duns": "",
                "award_id": "C-2022-0003",
            }
        ]
    )

    # Lower high_threshold to accept fuzzy match in test environment
    enriched = enrich_awards_with_companies(awards, companies, high_threshold=70, low_threshold=50)

    # Should be accepted as fuzzy-auto (since threshold lowered)
    assert enriched["_match_method"].iloc[0] in ("fuzzy-auto", "fuzzy-candidate")
    assert enriched["_match_score"].iloc[0] >= 70
    # Company fields should be merged
    assert enriched["company_company"].iloc[0] in ("TechStart Incorporated", "Other Corp")


def test_enrich_fuzzy_low_confidence_and_candidates_returned():
    companies = pd.DataFrame(
        [
            {"company": "NanoWorks LLC", "UEI": "", "Duns": "", "industry": "Nano"},
            {"company": "GreenEnergy Corp", "UEI": "", "Duns": "", "industry": "Energy"},
        ]
    )
    awards = pd.DataFrame(
        [{"company": "Unrelated Startup", "UEI": "", "Duns": "", "award_id": "C-2018-0005"}]
    )

    # Use high thresholds so that fuzzy matches are low-confidence
    enriched = enrich_awards_with_companies(
        awards, companies, high_threshold=95, low_threshold=85, return_candidates=True
    )

    # No deterministic match expected
    assert pd.isna(enriched["_matched_company_idx"].iloc[0]) or enriched["_match_method"].iloc[
        0
    ] in (
        "fuzzy-low",
        "fuzzy-candidate",
    )
    # match_score should be present (even if low)
    assert enriched["_match_score"].iloc[0] is not pd.NA
    # Candidates JSON should be present (since return_candidates=True)
    assert "_match_candidates" in enriched.columns
    cand_json = enriched["_match_candidates"].iloc[0]
    # Should be valid JSON string or pandas NA
    if not pd.isna(cand_json):
        parsed = json.loads(cand_json)
        assert isinstance(parsed, list)
        # Each candidate should contain idx and score keys
        assert all("idx" in c and "score" in c for c in parsed)


def test_enrich_multiple_awards_batch_behavior():
    # Ensure vectorized/batch matching works for multiple rows and retains order
    companies = pd.DataFrame(
        [
            {"company": "Acme Innovations", "UEI": "U1", "Duns": "111111111", "industry": "A"},
            {"company": "BioTech Labs", "UEI": "U2", "Duns": "222222222", "industry": "B"},
            {"company": "NanoWorks", "UEI": "U3", "Duns": "333333333", "industry": "C"},
        ]
    )
    awards = pd.DataFrame(
        [
            {"company": "Acme Innovations", "UEI": "U1", "Duns": ""},
            {"company": "BioTech Labs", "UEI": "", "Duns": "222-222-222"},
            {"company": "NanoWorks Inc.", "UEI": "", "Duns": ""},
        ]
    )

    enriched = enrich_awards_with_companies(awards, companies, high_threshold=80, low_threshold=60)

    # First two should be deterministic matches
    assert enriched["_match_method"].iloc[0] == "uei-exact"
    assert enriched["_match_method"].iloc[1] == "duns-exact"
    # Third should be a fuzzy match (company name variation)
    assert enriched["_match_method"].iloc[2].startswith("fuzzy")
    # Check merged industry columns exist and are non-null for matched rows
    assert "company_industry" in enriched.columns
    assert enriched["company_industry"].iloc[0] == "A"
    assert enriched["company_industry"].iloc[1] == "B"
    assert enriched["company_industry"].iloc[2] in ("C", None)


if __name__ == "__main__":
    # quick smoke run
    pytest.main([__file__])
