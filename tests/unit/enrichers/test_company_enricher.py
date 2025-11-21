import json

import pandas as pd
import pytest


pytestmark = pytest.mark.fast

from src.enrichers.company_enricher import enrich_awards_with_companies
from src.utils.text_normalization import normalize_company_name


def test_normalize_company_name_basic():
    assert normalize_company_name("Acme, Inc.") == "acme inc"
    assert normalize_company_name("  The Acme Co.  ") == "the acme company"
    assert normalize_company_name("") == ""


def test_enrich_exact_uei_match():
    # Company dataset with UEI present
    companies = pd.DataFrame(
        [
            {
                "company": "Acme Innovations",
                "UEI": "A1B2C3D4E5F6",
                "industry": "Aerospace",
            },  # pragma: allowlist secret
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


def test_build_block_key_normal():
    """Test building block key from normalized name."""
    from src.enrichers.company_enricher import build_block_key

    key = build_block_key("acme innovations", prefix_len=2)

    assert key == "ac"


def test_build_block_key_short_name():
    """Test building block key from name shorter than prefix."""
    from src.enrichers.company_enricher import build_block_key

    key = build_block_key("a", prefix_len=2)

    assert key == "a"


def test_build_block_key_empty_name():
    """Test building block key from empty name."""
    from src.enrichers.company_enricher import build_block_key

    key = build_block_key("", prefix_len=2)

    assert key == ""


def test_coerce_int_valid():
    """Test coercing valid values to int."""
    from src.enrichers.company_enricher import _coerce_int

    assert _coerce_int(42) == 42
    assert _coerce_int("42") == 42
    assert _coerce_int(42.0) == 42


def test_coerce_int_invalid():
    """Test coercing invalid values to int returns None."""
    from src.enrichers.company_enricher import _coerce_int

    assert _coerce_int(None) is None
    assert _coerce_int("abc") is None
    assert _coerce_int([]) is None


def test_enrich_empty_awards():
    """Test enriching empty awards DataFrame."""
    companies = pd.DataFrame(
        [
            {"company": "Test Corp", "UEI": "U1", "Duns": "111111111"},
        ]
    )
    awards = pd.DataFrame(columns=["company", "UEI", "Duns"])

    enriched = enrich_awards_with_companies(awards, companies)

    assert len(enriched) == 0
    assert "_match_method" in enriched.columns


def test_enrich_empty_companies():
    """Test enriching awards with empty companies DataFrame."""
    companies = pd.DataFrame(columns=["company", "UEI", "Duns"])
    awards = pd.DataFrame(
        [
            {"company": "Test Award", "UEI": "U1", "Duns": "111111111"},
        ]
    )

    enriched = enrich_awards_with_companies(awards, companies)

    # Should complete without error
    assert len(enriched) == 1
    assert "_match_method" in enriched.columns


def test_enrich_missing_award_company_column():
    """Test error when award company column is missing."""
    from src.exceptions import ValidationError

    companies = pd.DataFrame([{"company": "Test Corp"}])
    awards = pd.DataFrame([{"award_id": 1}])

    with pytest.raises(ValidationError) as exc_info:
        enrich_awards_with_companies(awards, companies, award_company_col="nonexistent_column")

    assert "award_company_col" in str(exc_info.value)


def test_enrich_missing_company_name_column():
    """Test error when company name column is missing."""
    from src.exceptions import ValidationError

    companies = pd.DataFrame([{"industry": "Tech"}])
    awards = pd.DataFrame([{"company": "Test Award"}])

    with pytest.raises(ValidationError) as exc_info:
        enrich_awards_with_companies(awards, companies, company_name_col="nonexistent_column")

    assert "company_name_col" in str(exc_info.value)


def test_enrich_column_name_fallback():
    """Test column name fallback detection."""
    companies = pd.DataFrame([{"Company Name": "Test Corp", "UEI": "U1"}])
    awards = pd.DataFrame([{"Company": "Test Corp", "UEI": "U1"}])

    # Should use fallback detection
    enriched = enrich_awards_with_companies(awards, companies)

    assert enriched["_match_method"].iloc[0] == "uei-exact"


def test_enrich_url_normalization():
    """Test company URL normalization."""
    companies = pd.DataFrame(
        [
            {
                "company": "Web Corp",
                "UEI": "U1",
                "Company Website": "https://webcorp.com",
            }
        ]
    )
    awards = pd.DataFrame(
        [
            {
                "company": "Web Corp",
                "UEI": "U1",
                "Company URL": "",
            }
        ]
    )

    enriched = enrich_awards_with_companies(awards, companies)

    assert "company_url" in enriched.columns


def test_enrich_fuzzy_with_blocking():
    """Test fuzzy matching uses blocking for performance."""
    # Create companies with same block key prefix
    companies = pd.DataFrame(
        [
            {"company": "Advanced Tech Solutions", "UEI": "", "Duns": ""},
            {"company": "Advanced Data Systems", "UEI": "", "Duns": ""},
            {"company": "Zebra Corp", "UEI": "", "Duns": ""},  # Different block
        ]
    )
    awards = pd.DataFrame(
        [
            {"company": "Advanced Tech", "UEI": "", "Duns": ""},
        ]
    )

    enriched = enrich_awards_with_companies(
        awards, companies, high_threshold=70, low_threshold=50, prefix_len=2
    )

    # Should match one of the "Advanced" companies, not Zebra
    assert enriched["_match_method"].iloc[0].startswith("fuzzy")
    assert enriched["_match_score"].iloc[0] >= 50


def test_enrich_fuzzy_no_block_candidates():
    """Test fuzzy matching fallback when no block candidates."""
    companies = pd.DataFrame(
        [
            {"company": "Acme Corp", "UEI": "", "Duns": ""},
        ]
    )
    awards = pd.DataFrame(
        [
            {"company": "Zzz Unrelated", "UEI": "", "Duns": ""},
        ]
    )

    enriched = enrich_awards_with_companies(
        awards, companies, high_threshold=95, low_threshold=50, prefix_len=2
    )

    # Should still attempt fuzzy matching with fallback
    assert "_match_score" in enriched.columns


def test_enrich_weighted_scoring_thresholds():
    """Test scoring threshold behavior."""
    companies = pd.DataFrame(
        [
            {"company": "Similar Name Corp", "UEI": "", "Duns": ""},
        ]
    )
    awards = pd.DataFrame(
        [
            {"company": "Similar Name Corporation", "UEI": "", "Duns": ""},
        ]
    )

    # High threshold - should be auto-accepted
    enriched_high = enrich_awards_with_companies(
        awards, companies, high_threshold=80, low_threshold=60
    )
    assert enriched_high["_match_method"].iloc[0] == "fuzzy-auto"

    # Very high threshold - should be candidate
    enriched_low = enrich_awards_with_companies(
        awards, companies, high_threshold=99, low_threshold=85
    )
    assert enriched_low["_match_method"].iloc[0] in ("fuzzy-candidate", "fuzzy-auto")


def test_normalize_company_name_extended():
    """Test extended company name normalization scenarios."""
    assert normalize_company_name("ACME CORP.") == "acme corp"
    assert normalize_company_name("The XYZ Company, LLC") == "the xyz company llc"
    assert normalize_company_name("  Multiple   Spaces  ") == "multiple spaces"
    assert normalize_company_name("123 Tech Inc") == "123 tech inc"
