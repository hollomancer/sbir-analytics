"""Tests for UCC debtor-side fuzzy matching with address + person-name filters."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "data"))

from ucc.matcher import (  # noqa: E402
    address_city_state,
    address_overlap_score,
    classify_match,
    is_debtor_side_match,
    looks_like_person_name,
    match_extraction,
    normalize_name,
)


# ---- 20-pair test set: 10 matches, 10 non-matches (per plan) ----

MATCH_PAIRS = [
    ("Acme Tech, Inc.", "ACME TECH INC."),
    ("3D Systems Corporation", "3D SYSTEMS CORP"),
    ("Quantum Computing LLC", "Quantum Computing, L.L.C."),
    ("Foo Bar Industries", "Foo Bar Industries Inc"),
    ("Genome Sciences, Inc.", "Genome Sciences Inc."),
    ("Pacific Biosciences of California", "PACIFIC BIOSCIENCES OF CALIFORNIA"),
    ("BioMarin Pharmaceutical", "BIOMARIN PHARMACEUTICAL INC"),
    ("Advanced Materials Corp", "ADVANCED MATERIALS CORPORATION"),
    ("Inhibrx, Inc.", "Inhibrx Inc"),
    ("Cohu, Inc.", "COHU, INC."),
]

NON_MATCH_PAIRS = [
    ("Acme Tech, Inc.", "Acme Manufacturing, Inc."),
    ("Pacific Biosciences of California", "Pacific Industries"),
    ("3D Systems", "5D Systems"),
    ("BioMarin", "BioGen"),
    ("Quantum Computing", "Classical Computing"),
    ("AeroVironment", "Aerodyne Systems"),
    ("Tesla, Inc.", "Cisco Systems, Inc."),
    ("Inhibrx, Inc.", "InhibitionRx, Inc."),
    ("Genome Sciences", "Genome Therapeutics"),
    ("Cohu", "Coho Systems"),
]


def test_normalize_name_strips_punctuation_and_lowercases():
    assert normalize_name("Acme, Inc.") == normalize_name("ACME INC")


def test_normalize_name_handles_suffix_variations():
    assert normalize_name("Advanced Materials Corp") == normalize_name(
        "Advanced Materials Corporation"
    )


def test_all_match_pairs_classify_high_or_medium():
    for cohort, ucc in MATCH_PAIRS:
        tier, score = classify_match(cohort, ucc)
        assert tier in ("high", "medium"), (
            f"{cohort!r} vs {ucc!r}: got tier={tier}, score={score:.3f}"
        )


def test_all_non_match_pairs_classify_low_or_drop():
    for cohort, ucc in NON_MATCH_PAIRS:
        tier, score = classify_match(cohort, ucc)
        assert tier in ("low", "drop"), f"{cohort!r} vs {ucc!r}: got tier={tier}, score={score:.3f}"


# ---- Address city/state extraction ----


def test_address_city_state_parses_full_address():
    # CA UCC format: "STREET ADDRESS, CITY, ST  ZIP" (double space common)
    city, state = address_city_state("11025 N TORREY PINES RD STE 200, LA JOLLA, CA  920371030")
    assert city == "LA JOLLA"
    assert state == "CA"


def test_address_city_state_handles_short_address():
    city, state = address_city_state("CARLSBAD, CA")
    assert city == "CARLSBAD"
    assert state == "CA"


def test_address_city_state_returns_empty_for_invalid():
    assert address_city_state("") == ("", "")
    assert address_city_state(None) == ("", "")


# ---- Address overlap scoring ----


def test_address_overlap_exact_city_state_match():
    """Same city + state = 1.0"""
    s = address_overlap_score(
        cohort_state="CA",
        filing_address="MAIN ST, CARLSBAD, CA",
    )
    # Without cohort_city we can only check state
    assert s >= 0.5


def test_address_overlap_state_match_only():
    s = address_overlap_score(
        cohort_state="CA",
        filing_address="1 BANK ST, SAN FRANCISCO, CA  94104",
    )
    assert 0.4 <= s <= 0.6  # state-only is partial credit


def test_address_overlap_state_mismatch():
    """Cohort firm in CA, filing debtor in TX → mismatch."""
    s = address_overlap_score(
        cohort_state="CA",
        filing_address="1 MAIN ST, AUSTIN, TX  78701",
    )
    assert s == 0.0


def test_address_overlap_city_match_bonus():
    """Same city should score higher than state-only."""
    state_only = address_overlap_score(
        cohort_state="CA",
        cohort_city="CARLSBAD",
        filing_address="1 BANK ST, SAN FRANCISCO, CA",
    )
    same_city = address_overlap_score(
        cohort_state="CA",
        cohort_city="CARLSBAD",
        filing_address="500 LAB DR, CARLSBAD, CA",
    )
    assert same_city > state_only
    assert same_city >= 0.9


# ---- Person-name detection ----


def test_looks_like_person_name_true_for_first_last():
    assert looks_like_person_name("AADITI MUJUMDAR") is True
    assert looks_like_person_name("JOHN SMITH") is True
    assert looks_like_person_name("Mary Johnson") is True


def test_looks_like_person_name_true_for_first_middle_last():
    assert looks_like_person_name("ROBERT J SMITH") is True
    assert looks_like_person_name("MARY ANNE WILSON") is True


def test_looks_like_person_name_false_for_entity_with_suffix():
    assert looks_like_person_name("ACME, INC.") is False
    assert looks_like_person_name("SMITH HOLDINGS LLC") is False
    assert looks_like_person_name("AADI BIOSCIENCE INC") is False
    assert looks_like_person_name("DOE TRUST") is False  # trusts aren't natural persons in UCC


def test_looks_like_person_name_false_for_descriptive_company():
    """Multi-word descriptive names shouldn't trigger even without suffix."""
    assert looks_like_person_name("PACIFIC BIOSCIENCES OF CALIFORNIA") is False
    assert looks_like_person_name("ADVANCED MATERIALS RESEARCH") is False


# ---- Debtor-side matching (the integrated filter) ----


def test_is_debtor_side_match_inhibrx_real_case():
    """Phase 0 case: Inhibrx hit where debtor is INHIBRX and SP is EDD."""
    filing = {
        "debtor_name": "INHIBRX, INC.",
        "debtor_address": "11025 N TORREY PINES RD STE 200, LA JOLLA, CA",
        "secured_party_name": "EMPLOYMENT DEVELOPMENT DEPARTMENT",
        "secured_party_address": "722 CAPITOL MALL, SACRAMENTO, CA",
    }
    cohort_row = {"company_name": "Inhibrx, Inc.", "state": "CA"}
    assert is_debtor_side_match(cohort_row, filing) is True


def test_is_debtor_side_match_drops_pacific_biosciences_as_secured_party():
    """Phase 0 case: Pacific Bio is SP, not debtor → drop."""
    filing = {
        "debtor_name": "UC BERKELEY",
        "debtor_address": "BERKELEY, CA",
        "secured_party_name": "PACIFIC BIOSCIENCES OF CALIFORNIA, INC.",
        "secured_party_address": "MENLO PARK, CA",
    }
    cohort_row = {"company_name": "Pacific Biosciences of California, Inc.", "state": "CA"}
    assert is_debtor_side_match(cohort_row, filing) is False


def test_is_debtor_side_match_drops_address_mismatch_6k_case():
    """6K Inc. (real: Andover MA) vs '6K CONSULTING INC - SACRAMENTO, CA' should be rejected."""
    filing = {
        "debtor_name": "6K CONSULTING INC",
        "debtor_address": "1234 K ST, SACRAMENTO, CA  95814",
        "secured_party_name": "U.S. BANK",
        "secured_party_address": "MARSHALL, MN",
    }
    cohort_row = {"company_name": "6K Inc.", "state": "MA", "city": "ANDOVER"}
    # Name is very close but city/state don't match → drop
    assert is_debtor_side_match(cohort_row, filing) is False


def test_is_debtor_side_match_drops_person_name():
    """AADI case: AADITI MUJUMDAR is a person, not the firm."""
    filing = {
        "debtor_name": "AADITI MUJUMDAR",
        "debtor_address": "SANTA CLARA, CA",
        "secured_party_name": "WELLS FARGO BANK",
        "secured_party_address": "CONCORD, CA",
    }
    cohort_row = {"company_name": "AADI, LLC", "state": "CA"}
    assert is_debtor_side_match(cohort_row, filing) is False


def test_is_debtor_side_match_keeps_active_motif():
    """Active Motif Phase 0 case: matched debtor at matching city CARLSBAD CA."""
    filing = {
        "debtor_name": "ACTIVE MOTIF, INC.",
        "debtor_address": "1914 PALOMAR OAKS WAY, CARLSBAD, CA  92011",
        "secured_party_name": "LEAF CAPITAL FUNDING, LLC",
        "secured_party_address": "PHILADELPHIA, PA",
    }
    cohort_row = {"company_name": "ACTIVE MOTIF, INC.", "state": "CA", "city": "CARLSBAD"}
    assert is_debtor_side_match(cohort_row, filing) is True


# ---- match_extraction (end-to-end with tier + address) ----


def test_match_extraction_returns_match_for_clean_case():
    filing = {
        "filing_number": "ABC123",
        "filing_type": "initial",
        "debtor_name": "ACTIVE MOTIF, INC.",
        "debtor_address": "CARLSBAD, CA  92011",
        "secured_party_name": "LEAF CAPITAL FUNDING",
        "secured_party_address": "PHILADELPHIA, PA",
    }
    cohort_row = {"company_name": "Active Motif, Inc.", "state": "CA", "city": "CARLSBAD"}
    m = match_extraction(filing, cohort_row)
    assert m is not None
    assert m["match_confidence"] in ("high", "medium")
    assert m["cohort_company_name"] == "Active Motif, Inc."


def test_match_extraction_returns_none_for_person_name():
    filing = {
        "filing_number": "X",
        "filing_type": "initial",
        "debtor_name": "AADITI MUJUMDAR",
        "debtor_address": "SANTA CLARA, CA",
        "secured_party_name": "WELLS FARGO",
        "secured_party_address": "",
    }
    cohort_row = {"company_name": "AADI, LLC", "state": "CA"}
    assert match_extraction(filing, cohort_row) is None


def test_match_extraction_returns_none_for_cross_state_collision():
    filing = {
        "filing_number": "X",
        "filing_type": "initial",
        "debtor_name": "6K CONSULTING INC",
        "debtor_address": "SACRAMENTO, CA",
        "secured_party_name": "U.S. BANK",
        "secured_party_address": "",
    }
    cohort_row = {"company_name": "6K Inc.", "state": "MA"}
    assert match_extraction(filing, cohort_row) is None
