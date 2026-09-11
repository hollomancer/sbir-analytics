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
        (
            CompanyNameProfile.PRESS_WIRE_WATCHLIST_V1,
            "Café+ Technologies, L.L.C.",
            "cafe+ technologies",
        ),
        (CompanyNameProfile.RECIPIENT_V1, "Café Technologies, Inc.", "cafe technologies"),
        (CompanyNameProfile.ENTITY_RESOLUTION_V1, "O'Brien & Associates Inc", "OBRIEN ASSOCIATES"),
        (CompanyNameProfile.GROUNDTRUTH_V1, "Acme Photonics, L.L.C.", "ACME PHOTONICS"),
        (CompanyNameProfile.VENDOR_CROSSWALK_V1, "Acme, Inc.", "Acme  Inc"),
        (CompanyNameProfile.VENDOR_KEY_V1, "Acme & Corporation", "acme and corp"),
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
        ("SKY+", "sky+"),
        ("C++, Inc.", "c++"),
        (".NET Systems LLC", ".net systems"),
        ("Big Corp Corporation", "big corp"),
    ],
)
def test_press_wire_profile_preserves_brand_punctuation_and_strips_one_designator(
    raw: str,
    expected: str,
) -> None:
    assert (
        normalize_company_name(raw, profile=CompanyNameProfile.PRESS_WIRE_WATCHLIST_V1) == expected
    )


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


def test_vendor_key_preserves_resolver_compatibility() -> None:
    names = ["Acme Corporation", "Acme, Corp.", "Acme & Company", "Acme/LLC"]

    for name in names:
        assert normalize_company_name(
            name,
            profile=CompanyNameProfile.VENDOR_KEY_V1,
        ) == normalize_company_name(
            name,
            profile=CompanyNameProfile.VENDOR_RESOLVER_V1,
        )


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


# --- Adversarial audit -------------------------------------------------------
#
# Pairs that must NOT be treated as the same firm. Drawn from real false
# positives found in the Form D join on 2026-09-08, plus the short-name
# collisions that make `press_wire._match_company` 0/18.

MUST_NOT_MATCH = [
    ("3D Control Systems, Inc.", "3D SYSTEMS CORP", "real Form D false positive"),
    ("ADELPHI TECHNOLOGY", "ADEPT TECHNOLOGY", "real Form D false positive"),
    ("Nanomimetics", "NANOMETRICS", "real Form D false positive"),
    ("Pronghorn Technologies", "PROCORE TECHNOLOGIES", "real Form D false positive"),
    ("ADT Pharmaceuticals", "ADT Inc.", "real Form D false positive"),
    ("COMPASS SYSTEMS", "Compass, Inc.", "real Form D false positive"),
    ("Linked, Inc.", "LINKEDIN CORP", "real Form D false positive"),
    ("BAL", "BALL CORP", "real Form D false positive"),
    ("SiliconCore Technology, Inc.", "SILICON STORAGE TECHNOLOGY INC", "shared tokens"),
]


@pytest.mark.parametrize("left,right,reason", MUST_NOT_MATCH)
def test_distinct_firms_do_not_score_as_the_same_firm(left: str, right: str, reason: str) -> None:
    """Every pair here was a real attribution error or is one waiting to happen.

    This asserts a documented ceiling, not a target. If a pair scores above it,
    the number in this assertion is the thing to change deliberately, with the
    consumer thresholds re-checked.

    ``metric`` has no default on ``company_name_similarity`` (deliberately --
    a primitives-tier contract does not get to pick a hidden default policy).
    ``TOKEN_SET`` is used here because it is the metric two live consumers
    (`sbir_etl/enrichers/sec_edgar/enricher.py::_search_form_d_filings` and
    `::_search_filing_mentions_filtered`) apply directly with no normalization
    profile -- the exact shape of the real Form D false positives above. No
    profile is passed for the same reason: those two call sites pass raw,
    manually-uppercased text.

    Audit result (2026-09-10): 0/9 pairs score >= 0.95 under this
    configuration; the highest is 0.882 (ADELPHI TECHNOLOGY vs ADEPT
    TECHNOLOGY). The primitive's raw, unprofiled score stays well under this
    ceiling for every pair here. The defect is not here -- see
    `.superpowers/sdd/2026-09-10-verification-practices/task-5-report.md` for
    the consumers whose own thresholds (80, 85, 90, 0.92) sit inside the range
    these pairs actually score once each consumer's own profile normalization
    is applied.
    """
    score = company_name_similarity(left, right, metric=CompanyNameMetric.TOKEN_SET)
    assert score < 0.95, f"{left!r} vs {right!r} scored {score}: {reason}"
