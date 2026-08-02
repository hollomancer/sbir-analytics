import math

import pytest
import pandas as pd
from rapidfuzz import fuzz, process

from sbir_etl.enrichers import matching as legacy_matching
from sbir_etl.identity import (
    ENHANCED_ABBREVIATIONS,
    SUFFIX_TOKENS,
    CompanyNameMetric,
    CompanyNameProfile,
    company_name_similarity,
    normalize_company_name,
    rapidfuzz_jaro_winkler_100,
    rapidfuzz_ratio_100,
    rapidfuzz_token_set_100,
    rapidfuzz_token_sort_100,
)


@pytest.mark.parametrize(
    ("profile", "raw", "expected"),
    [
        (
            CompanyNameProfile.ORGANIZATION_KEY_V1,
            "Café Technologies, L.L.C.",
            "CAFE TECHNOLOGIES",
        ),
        (
            CompanyNameProfile.MATCHING_V1,
            "Café Technologies, Incorporated",
            "cafe technologies inc",
        ),
        (CompanyNameProfile.RECIPIENT_V1, "Café Technologies, Inc.", "cafe technologies"),
        (CompanyNameProfile.ENTITY_RESOLUTION_V1, "O'Brien & Associates Inc", "OBRIEN ASSOCIATES"),
        (CompanyNameProfile.GROUNDTRUTH_V1, "Acme Photonics, L.L.C.", "ACME PHOTONICS"),
        (CompanyNameProfile.VENDOR_CROSSWALK_V1, "Acme, Inc.", "Acme  Inc"),
        (CompanyNameProfile.VENDOR_RESOLVER_V1, "Acme & Corporation", "acme and corp"),
        (CompanyNameProfile.FORM_D_JOIN_V1, "  Acme   Corp ", "ACME CORP"),
        (CompanyNameProfile.UCC_V1, "Advanced Materials Corporation", "adv materials"),
        (CompanyNameProfile.SEC_EDGAR_V1, "QUALCOMM INC/DE", "QUALCOMM"),
        (CompanyNameProfile.SEC_EDGAR_TRAILING_V1, "QUALCOMM INC/DE", "QUALCOMM INC"),
        (CompanyNameProfile.NOTICE_KEY_V1, "Acme Photonics, Inc.", "ACMEPHOTONICS"),
        (CompanyNameProfile.PHASE3_RANKING_V1, "Acme CorpTech LLC", "ACME"),
    ],
)
def test_versioned_profiles_preserve_declared_outputs(
    profile: CompanyNameProfile,
    raw: str,
    expected: str,
) -> None:
    assert normalize_company_name(raw, profile=profile) == expected


def test_matching_profile_accepts_explicit_abbreviation_dictionary() -> None:
    normalized = normalize_company_name(
        "Advanced Technologies, Inc.",
        profile=CompanyNameProfile.MATCHING_V1,
        abbreviations=ENHANCED_ABBREVIATIONS,
    )

    assert normalized == "adv tech inc"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Coherent Photonics, Limited Liability Company", "COHERENT PHOTONICS"),
        ("Pelletized Straw, L.L.C.", "PELLETIZED STRAW"),
        ("Acme Corp Inc LLC", "ACME"),
        ("Acme LLC Limited Liability Company", "ACME"),
        ("PC Photonics", "PC PHOTONICS"),
        ("AEROPLAS CORP. INTERNATIONAL", "AEROPLAS CORP INTERNATIONAL"),
        ("Corptech, Inc.", "CORPTECH"),
    ],
)
def test_organization_key_removes_only_trailing_legal_designators(
    raw: str,
    expected: str,
) -> None:
    assert normalize_company_name(raw, profile=CompanyNameProfile.ORGANIZATION_KEY_V1) == expected


@pytest.mark.parametrize("blank", [None, "", "   ", float("nan")])
def test_all_profiles_return_empty_for_blank_values(blank: object) -> None:
    for profile in CompanyNameProfile:
        assert normalize_company_name(blank, profile=profile) == ""


def test_similarity_treats_pandas_missing_value_as_blank() -> None:
    assert company_name_similarity(pd.NA, "Acme", metric=CompanyNameMetric.TOKEN_SET) == 0.0


@pytest.mark.parametrize(
    ("metric", "direct"),
    [
        (CompanyNameMetric.RATIO, fuzz.ratio),
        (CompanyNameMetric.TOKEN_SET, fuzz.token_set_ratio),
        (CompanyNameMetric.TOKEN_SORT, fuzz.token_sort_ratio),
    ],
)
def test_similarity_contract_uses_zero_to_one_scale(metric, direct) -> None:
    left = "acme advanced systems"
    right = "advanced acme system"

    score = company_name_similarity(left, right, metric=metric)

    assert 0.0 <= score <= 1.0
    assert math.isclose(score, direct(left, right) / 100.0)


def test_rapidfuzz_adapters_preserve_historical_score_scale_and_process_api() -> None:
    left = "acme advanced systems"
    right = "advanced acme system"

    assert rapidfuzz_ratio_100(left, right) == pytest.approx(fuzz.ratio(left, right))
    assert rapidfuzz_token_set_100(left, right) == pytest.approx(fuzz.token_set_ratio(left, right))
    assert rapidfuzz_token_sort_100(left, right) == pytest.approx(
        fuzz.token_sort_ratio(left, right)
    )
    assert 0.0 <= rapidfuzz_jaro_winkler_100(left, right) <= 100.0
    assert (
        process.extractOne(
            left,
            {1: right},
            scorer=rapidfuzz_token_set_100,
        )[2]
        == 1
    )


def test_legacy_matching_constants_are_shared_identity_objects() -> None:
    assert legacy_matching.ENHANCED_ABBREVIATIONS is ENHANCED_ABBREVIATIONS
    assert legacy_matching.SUFFIX_TOKENS is SUFFIX_TOKENS
