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


# --- Positive counterpart -----------------------------------------------------
#
# `MUST_NOT_MATCH` has no positive twin, so a matcher that rejects everything
# passes it for free. These pairs are the recall check.
#
# Source (2026-09-11, full corpus, not a sample): group
# `data/raw/sbir/award_data.csv` (219,501 rows) by `Duns` and find DUNS values
# carrying more than one distinct `Company` string -- one legal entity written
# more than one way. 15 DUNS groups match; one of them is `Duns == "0"`, a
# missing-data sentinel shared by 3 unrelated firms (4 rows total across the
# whole file), not a real identifier, and is excluded as junk. The remaining
# 14 real DUNS carry exactly one pair of names each.
#
# Not every one of those 14 belongs here. Two kinds appear:
#   - name variants: the same name rendered differently (suffix, case, an
#     article, a dropped/added token). A matcher should bridge these.
#   - renames/rebrands: the same legal entity under an unrelated name. A name
#     matcher cannot and should not bridge these -- only an identifier join
#     can, and putting them here would force thresholds down until
#     MUST_NOT_MATCH breaks again (see #713, #714).
#
# Excluded as renames (4 of 14), with the call:
#   - "ALTRAZEAL LIFE SCIENCES INC" / "Uluru Inc." -- zero shared token,
#     unrelated brand names.
#   - "Joule Therapeutics, Inc" / "TARN BIOSCIENCES, INC." -- zero shared
#     token, unrelated brand names.
#   - "RGBSI AEROSPACE & DEFENSE LLC" /
#     "Rapid Global Business Solutions Inc (RGBSI) Aerospace & Defense" --
#     the full string self-declares the initialism in a parenthetical, but no
#     normalization profile in this codebase expands company-specific
#     acronyms, so no available text comparison bridges "RGBSI" to "Rapid
#     Global Business Solutions Inc" (it needs an abbreviation lookup, not a
#     string metric). Functions as a rename for this primitive; excluded.
#   - "GAMMA ALLOYS INC" / "Gamma Technology, LLC" -- borderline, called NOT a
#     match. The only shared token, "Gamma", is a generic scientific prefix
#     (compare "Compass"/"Silicon" in MUST_NOT_MATCH) reused across unrelated
#     firms; "Alloys" and "Technology" name unrelated businesses. Matching on
#     one generic token is the exact false-positive shape MUST_NOT_MATCH
#     exists to catch.
#
# Kept as a variant (1 of 14 borderline, called a match): "WEINBERG MEDICAL
# PHYSICS, LLC" / "Weinberg Medical Holdings" -- unlike Gamma, the shared
# span is two words ("Weinberg Medical"), and "Weinberg" is a distinctive
# surname, not a generic word. "Physics" vs "Holdings" reads as an operating
# company renaming itself into a holding-company structure while keeping its
# founder-derived name, not a rebrand to an unrelated identity.
#
# The other 9 of 14 are unambiguous variants: 6 are byte-for-byte identical
# after `CompanyNameProfile.RECIPIENT_V1` normalization (case, punctuation,
# and legal-suffix differences only); 3 keep a distinctive token but add a
# suffix, an article, or drop a descriptor word.
MUST_MATCH = [
    ("Mystic Spear", "MYSTIC SPEAR, LLC", "DUNS 017854463: case + suffix"),
    (
        "Convergent Manufacturing Technologies US",
        "CONVERGENT MANUFACTURING TECHNOLOGIES US INC",
        "DUNS 079729780: case + suffix",
    ),
    ("Qunnect LLC", "QUNNECT, INC", "DUNS 080969063: case + suffix swap"),
    ("SPZ TECHNOLOGIE LLC", "SPZ Technologie, LLC", "DUNS 081020673: case only"),
    ("TIAMI NETWORKS", "Tiami, LLC", "DUNS 084613536: suffix, descriptor word dropped"),
    ("Aromha Inc", "AROMHA, INC.", "DUNS 118263562: case + punctuation"),
    ("AnySignal, Inc.", "ANYSIGNAL INC", "DUNS 118694667: case + punctuation"),
    ("NAVSYS Corporation", "THE NAVSYS CORPORATION", "DUNS 182097444: article + case"),
    ("RAM Photonics", "RAM PHOTONICS INDUSTRIAL, LLC", "DUNS 831819979: token subset"),
    (
        "WEINBERG MEDICAL PHYSICS, LLC",
        "Weinberg Medical Holdings",
        "DUNS 809594661: borderline, called a match -- see reasoning above",
    ),
]

# Trivially-true pairs: identical strings, pure case, and punctuation-only
# differences. Cheap, and they catch a catastrophic regression (e.g. the
# scorer always returning 0.0) even without touching real data.
#
# One of these -- pure case, no other difference -- turned out not to be
# trivial. See the floor discussion below.
MUST_MATCH_TRIVIAL = [
    ("Acme Corporation", "Acme Corporation", "identical strings"),
    ("Acme Corporation", "ACME CORPORATION", "pure case difference"),
    ("Acme Inc.", "Acme Inc", "trailing period only"),
    ("Acme  Corp", "Acme Corp", "double space only"),
]

# Floor chosen from real scores, not asserted in advance. Under the exact
# configuration MUST_NOT_MATCH audits -- TOKEN_SET, no normalization
# profile, matching the two live consumers that call this primitive on raw,
# separately-uppercased text -- the 10 MUST_MATCH pairs score 0.148-0.539,
# and the 4 MUST_MATCH_TRIVIAL pairs score 0.188-1.000 (the pure-case pair is
# the 0.188; the rest are >=0.941). 0.10 sits under every one of those with
# room to spare, and still fails on a scorer that returns ~0.
#
# It is NOT a precision floor, and the gap this file's docstring asks for
# does not hold. Under this same configuration, MUST_NOT_MATCH's ceiling
# pairs score up to 0.882 (ADELPHI TECHNOLOGY vs ADEPT TECHNOLOGY) -- higher
# than every single MUST_MATCH pair here (max 0.539). Three more
# MUST_NOT_MATCH pairs (BAL/BALL CORP 0.500, ADT Pharmaceuticals/ADT Inc.
# 0.545, plus ADELPHI/ADEPT above) also outscore most of MUST_MATCH. No
# single threshold on this configuration separates the two tables: raising
# the floor to catch real matches also readmits real non-matches, at a lower
# floor than the false positives this file exists to keep out.
#
# The cause is not a scoring/business-logic defect: RapidFuzz's
# `token_set_ratio` is case-sensitive with no processor applied, and this
# call path applies none. "Acme Corporation" vs "ACME CORPORATION" -- the
# same name, no other difference -- scores 0.188 for exactly that reason.
# The two production consumers this configuration models
# (`sbir_etl/enrichers/sec_edgar/enricher.py::_search_form_d_filings` and
# `::_search_filing_mentions_filtered`) avoid this by uppercasing both sides
# themselves before calling; MUST_NOT_MATCH's own literals are typed in
# mixed case and are not run through that same uppercasing, so its 0.95
# ceiling is not a faithful replay of the production call either. Full
# analysis, including scores for two alternative configurations that were
# rejected because they break MUST_NOT_MATCH's ceiling instead of fixing
# this gap, is in
# `.superpowers/sdd/2026-09-10-verification-practices/must-match-report.md`.
MUST_MATCH_FLOOR = 0.10


@pytest.mark.parametrize("left,right,reason", MUST_MATCH)
def test_same_firm_scores_above_the_match_floor(left: str, right: str, reason: str) -> None:
    """Real DUNS-confirmed name variants, scored the same way MUST_NOT_MATCH is.

    See the module-level comment above `MUST_MATCH` for how each pair was
    classified (variant vs. rename) and the comment above `MUST_MATCH_FLOOR`
    for why 0.10 is a regression guard, not a validated precision floor.
    """
    score = company_name_similarity(left, right, metric=CompanyNameMetric.TOKEN_SET)
    assert score >= MUST_MATCH_FLOOR, f"{left!r} vs {right!r} scored {score}: {reason}"


@pytest.mark.parametrize("left,right,reason", MUST_MATCH_TRIVIAL)
def test_trivial_same_firm_pairs_score_above_the_match_floor(
    left: str, right: str, reason: str
) -> None:
    score = company_name_similarity(left, right, metric=CompanyNameMetric.TOKEN_SET)
    assert score >= MUST_MATCH_FLOOR, f"{left!r} vs {right!r} scored {score}: {reason}"
