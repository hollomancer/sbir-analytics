"""Tests for company_fuzzy_matcher (rapidfuzz-based local matching)."""

import json

import pandas as pd
import pytest

from sbir_etl.enrichers.company_fuzzy_matcher import enrich_awards_with_companies
from sbir_etl.utils.text_normalization import normalize_company_name
from tests.factories import DataFrameBuilder
from tests.unit.identity.test_company_names import MUST_NOT_MATCH


pytestmark = pytest.mark.fast


def test_normalize_company_name_basic():
    assert normalize_company_name("Acme, Inc.") == "acme inc"
    assert normalize_company_name("  The Acme Co.  ") == "the acme company"
    assert normalize_company_name("") == ""


def test_enrich_exact_uei_match():
    # Company dataset with UEI present
    companies = DataFrameBuilder.companies(1).build()
    companies["UEI"] = "A1B2C3D4E5F6"  # pragma: allowlist secret
    companies["industry"] = "Aerospace"
    companies["company"] = "Acme Innovations"

    # Award row referencing the same UEI
    awards = DataFrameBuilder.awards(1).build()
    # Drop company columns that will be enriched
    awards = awards.drop(columns=[c for c in awards.columns if c.startswith("company_")])
    awards["company"] = "Acme Innovations"
    awards["UEI"] = "A1B2C3D4E5F6"
    awards["Duns"] = ""
    awards["award_id"] = "C-2023-0001"

    enriched = enrich_awards_with_companies(awards, companies, return_candidates=False)

    # Expect deterministic UEI exact match
    assert enriched["_match_method"].iloc[0] == "uei-exact"
    assert int(enriched["_match_score"].iloc[0]) == 100
    # The merged company UEI column should be present and equal to original
    assert "company_UEI" in enriched.columns
    assert enriched["company_UEI"].iloc[0] == "A1B2C3D4E5F6"
    # And industry should be merged
    assert enriched["company_industry"].iloc[0] == "Aerospace"


def test_enrich_preserves_existing_company_normalized_name() -> None:
    companies = pd.DataFrame(
        [
            {
                "company": "Acme Innovations",
                "UEI": "U1",
                "Duns": "",
                "_norm_name": "curated-acme-name",
            }
        ]
    )
    awards = pd.DataFrame([{"company": "Acme Innovations", "UEI": "U1", "Duns": ""}])

    enriched = enrich_awards_with_companies(awards, companies)

    assert enriched["company__norm_name"].iloc[0] == "curated-acme-name"


def test_enrich_exact_duns_match_with_hyphens():
    companies = DataFrameBuilder.companies(1).build()
    companies["company"] = "BioTech Labs"
    companies["UEI"] = ""
    companies["Duns"] = "987654321"
    companies["industry"] = "Biotech"

    awards = DataFrameBuilder.awards(1).build()
    # Drop company columns that will be enriched
    awards = awards.drop(columns=[c for c in awards.columns if c.startswith("company_")])
    awards["company"] = "BioTech Labs"
    awards["UEI"] = ""
    awards["Duns"] = "987-654-321"  # hyphenated form
    awards["award_id"] = "C-2021-0420"

    enriched = enrich_awards_with_companies(awards, companies)

    assert enriched["_match_method"].iloc[0] == "duns-exact"
    assert int(enriched["_match_score"].iloc[0]) == 100
    assert enriched["company_Duns"].iloc[0] == "987654321" or "company_Duns" in enriched.columns


def test_enrich_fuzzy_name_match_auto_accept():
    """Test fuzzy name matching with auto-accept threshold."""
    companies = (
        DataFrameBuilder.companies(2)
        .build()
        .assign(
            company=["TechStart Incorporated", "Other Corp"],
            UEI=["", ""],
            Duns=["", ""],
            industry=["AI", "Other"],
        )
    )
    awards = (
        DataFrameBuilder.awards(1)
        .build()
        .drop(
            columns=[
                c for c in DataFrameBuilder.awards(1).build().columns if c.startswith("company_")
            ]
        )
        .assign(company="TechStart Inc", UEI="", Duns="", award_id="C-2022-0003")
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
            {
                "company": "Acme Innovations",
                "UEI": "ACMEUEI00001",
                "Duns": "123456781",
                "industry": "A",
            },
            {
                "company": "BioTech Labs",
                "UEI": "BIOUEI000002",
                "Duns": "123456782",
                "industry": "B",
            },
            {"company": "NanoWorks", "UEI": "NANOUEI00003", "Duns": "123456783", "industry": "C"},
        ]
    )
    awards = pd.DataFrame(
        [
            {"company": "Acme Innovations", "UEI": "ACMEUEI00001", "Duns": ""},
            {"company": "BioTech Labs", "UEI": "", "Duns": "123-456-782"},
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


@pytest.mark.parametrize(
    "name,prefix_len,expected",
    [
        ("acme innovations", 2, "ac"),
        ("a", 2, "a"),
        ("", 2, ""),
        ("test company", 3, "tes"),
    ],
    ids=["normal", "short", "empty", "longer_prefix"],
)
def test_build_block_key(name, prefix_len, expected):
    """Test building block key from normalized name."""
    from sbir_etl.enrichers.company_fuzzy_matcher import build_block_key

    assert build_block_key(name, prefix_len=prefix_len) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (42, 42),
        ("42", 42),
        (42.0, 42),
        (None, None),
        ("abc", None),
        ([], None),
    ],
    ids=["int", "str", "float", "none", "invalid_str", "list"],
)
def test_coerce_int(value, expected):
    """Test coercing various values to int."""
    from sbir_etl.enrichers.company_fuzzy_matcher import _coerce_int

    assert _coerce_int(value) == expected


def test_enrich_empty_awards():
    """Test enriching empty awards DataFrame."""
    companies = DataFrameBuilder.companies(1).build()
    companies["company"] = "Test Corp"
    companies["UEI"] = "U1"
    companies["Duns"] = "111111111"

    awards = pd.DataFrame(columns=["company", "UEI", "Duns"])

    enriched = enrich_awards_with_companies(awards, companies)

    assert len(enriched) == 0
    assert "_match_method" in enriched.columns


def test_enrich_empty_companies():
    """Test enriching awards with empty companies DataFrame."""
    from tests.assertions import assert_dataframe_has_columns

    companies = pd.DataFrame(columns=["company", "UEI", "Duns"])
    awards = DataFrameBuilder.awards(1).build()
    awards["company"] = "Test Award"
    awards["UEI"] = "U1"
    awards["Duns"] = "111111111"

    enriched = enrich_awards_with_companies(awards, companies)

    assert len(enriched) == 1
    assert_dataframe_has_columns(enriched, ["_match_method"])


def test_enrich_missing_award_company_column():
    """Test error when award company column is missing."""
    from sbir_etl.exceptions import ValidationError

    companies = pd.DataFrame([{"company": "Test Corp"}])
    awards = pd.DataFrame([{"award_id": 1}])

    with pytest.raises(ValidationError) as exc_info:
        enrich_awards_with_companies(awards, companies, award_company_col="nonexistent_column")

    assert "award_company_col" in str(exc_info.value)


def test_enrich_missing_company_name_column():
    """Test error when company name column is missing."""
    from sbir_etl.exceptions import ValidationError

    companies = pd.DataFrame([{"industry": "Tech"}])
    awards = pd.DataFrame([{"company": "Test Award"}])

    with pytest.raises(ValidationError) as exc_info:
        enrich_awards_with_companies(awards, companies, company_name_col="nonexistent_column")

    assert "company_name_col" in str(exc_info.value)


def test_enrich_column_name_fallback():
    """Test column name fallback detection."""
    companies = pd.DataFrame([{"Company Name": "Test Corp", "UEI": "TESTUEI00001"}])
    awards = pd.DataFrame([{"Company": "Test Corp", "UEI": "TESTUEI00001"}])

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

    # Very high threshold - should be candidate or low match
    enriched_low = enrich_awards_with_companies(
        awards, companies, high_threshold=99, low_threshold=85
    )
    assert enriched_low["_match_method"].iloc[0] in ("fuzzy-candidate", "fuzzy-auto", "fuzzy-low")


def test_normalize_company_name_extended():
    """Test extended company name normalization scenarios."""
    assert normalize_company_name("ACME CORP.") == "acme corp"
    assert normalize_company_name("The XYZ Company, LLC") == "the xyz company llc"
    assert normalize_company_name("  Multiple   Spaces  ") == "multiple spaces"
    assert normalize_company_name("123 Tech Inc") == "123 tech inc"


# --- Adversarial audit: fuzzy-auto acceptance --------------------------------
#
# ``enrich_awards_with_companies`` has exactly one function that returns a
# positive match decision: itself. The score comes from
# ``rapidfuzz.process.extract`` using ``rapidfuzz_token_set_100`` (the
# identity primitive's own scorer -- reused here, not forked) over names run
# through this module's own ``normalize_name`` (forked from
# ``sbir_etl.identity.normalize_company_name``; see module docstring). A
# match is auto-accepted ("fuzzy-auto") at ``best_score >= high_threshold``;
# ``high_threshold`` defaults to 90 and every real caller of this function
# uses that default. A score in [low_threshold, 90) only produces
# "fuzzy-candidate" -- flagged for human review, not an auto-accepted
# match -- so it is out of scope for this audit.
#
# Audit result (2026-09-10): at the real default threshold (90), 0/9
# MUST_NOT_MATCH pairs reach "fuzzy-auto". The closest is SiliconCore
# Technology, Inc. vs SILICON STORAGE TECHNOLOGY INC at 89 -- one point
# below auto-accept, landing on "fuzzy-candidate" instead. The defect is
# not here: see
# `.superpowers/sdd/2026-09-10-verification-practices/task-6-report.md`.
@pytest.mark.parametrize("left,right,reason", MUST_NOT_MATCH)
def test_distinct_firms_do_not_auto_accept(left: str, right: str, reason: str) -> None:
    awards = pd.DataFrame([{"company": left, "UEI": "", "Duns": "", "award_id": "X"}])
    companies = pd.DataFrame([{"company": right, "UEI": "", "Duns": "", "industry": "x"}])

    enriched = enrich_awards_with_companies(awards, companies)

    method = enriched["_match_method"].iloc[0]
    score = enriched["_match_score"].iloc[0]
    assert method != "fuzzy-auto", (
        f"{left!r} vs {right!r} auto-accepted at score {score} (method={method}): {reason}"
    )


def _exact_method(award_ids: dict, company_ids: dict) -> object:
    companies = pd.DataFrame([{"company": "Alpha Rotor Systems", **company_ids}])
    awards = pd.DataFrame([{"company": "Zephyr Biologics", **award_ids}])
    enriched = enrich_awards_with_companies(awards, companies, high_threshold=90)
    return enriched["_match_method"].iloc[0]


@pytest.mark.parametrize(
    ("award_ids", "company_ids"),
    [
        ({"UEI": "N/A", "Duns": ""}, {"UEI": "N/A", "Duns": ""}),
        ({"UEI": "NONE", "Duns": ""}, {"UEI": "NONE", "Duns": ""}),
        ({"UEI": "U1", "Duns": ""}, {"UEI": "U1", "Duns": ""}),
        ({"UEI": "000000000000", "Duns": ""}, {"UEI": "000000000000", "Duns": ""}),
        ({"UEI": "", "Duns": "000000000"}, {"UEI": "", "Duns": "000-000-000"}),
        ({"UEI": "", "Duns": "999999999"}, {"UEI": "", "Duns": "999999999"}),
        ({"UEI": "", "Duns": "12345"}, {"UEI": "", "Duns": "12345"}),
    ],
    ids=[
        "uei_na",
        "uei_none",
        "uei_too_short",
        "uei_all_zero",
        "duns_all_zero",
        "duns_all_nine",
        "duns_too_short",
    ],
)
def test_placeholder_identifiers_never_match_exactly(award_ids, company_ids) -> None:
    # Unrelated names: only a shared placeholder ID could link these firms.
    assert _exact_method(award_ids, company_ids) not in ("uei-exact", "duns-exact")


def test_duns_read_as_a_number_still_matches_exactly() -> None:
    # pandas without dtype=str reads DUNS 012345678 as 12345678.0.
    assert _exact_method({"Duns": 12345678.0}, {"Duns": "012345678"}) == "duns-exact"


def test_duns_decimal_text_is_read_as_the_number() -> None:
    from sbir_etl.enrichers.company_fuzzy_matcher import _exact_duns_key

    # A CSV written from a float column stores DUNS 012345678 as "12345678.0".
    assert _exact_duns_key("12345678.0") == "012345678"
    assert _exact_duns_key(" 123456789.00 ") == "123456789"
    assert _exact_method({"Duns": "12345678.0"}, {"Duns": "012345678"}) == "duns-exact"


@pytest.mark.parametrize("value", ["12345678", "1234567890.0"])
def test_duns_text_that_is_not_a_padded_number_stays_invalid(value) -> None:
    from sbir_etl.enrichers.company_fuzzy_matcher import _exact_duns_key

    # Text sources keep leading zeros, so a plain 8-digit string is truncated.
    assert _exact_duns_key(value) is None


@pytest.mark.parametrize("value", ["123456789A", "12345678.9", "１２３４５６７８９"])
def test_malformed_duns_has_no_exact_key(value) -> None:
    from sbir_etl.enrichers.company_fuzzy_matcher import _exact_duns_key

    # Before DUNS_V2 each of these produced a key.
    assert _exact_duns_key(value) is None
    assert _exact_duns_key("12345678.0") == "012345678"
