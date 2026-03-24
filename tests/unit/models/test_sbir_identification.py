"""Tests for SBIR/STTR identification reference data and classification functions."""

import pytest

from sbir_etl.models.sbir_identification import (
    ALL_SBIR_ALNS,
    EXCLUSIVE_SBIR_ALNS,
    RESEARCH_CODE_DETAIL,
    SBIR_ASSISTANCE_LISTING_NUMBERS,
    SBIR_ONLY_CODES,
    SBIR_RESEARCH_CODES,
    STTR_ONLY_CODES,
    SbirResearchCode,
    classify_sbir_award,
    is_sbir_grant,
    parse_research_code,
    _parse_sbir_from_description,
)


pytestmark = pytest.mark.fast


# ---------------------------------------------------------------------------
# Constants validation
# ---------------------------------------------------------------------------


class TestConstants:
    """Validate module-level constants and data integrity."""

    def test_sbir_research_codes_has_six_entries(self):
        assert len(SBIR_RESEARCH_CODES) == 6

    def test_sbir_research_codes_matches_enum(self):
        assert SBIR_RESEARCH_CODES == frozenset(c.value for c in SbirResearchCode)

    def test_sbir_only_codes_are_subset(self):
        assert SBIR_ONLY_CODES < SBIR_RESEARCH_CODES

    def test_sttr_only_codes_are_subset(self):
        assert STTR_ONLY_CODES < SBIR_RESEARCH_CODES

    def test_sbir_and_sttr_codes_partition_all_codes(self):
        assert SBIR_ONLY_CODES | STTR_ONLY_CODES == SBIR_RESEARCH_CODES
        assert SBIR_ONLY_CODES & STTR_ONLY_CODES == frozenset()

    def test_research_code_detail_has_six_entries(self):
        assert len(RESEARCH_CODE_DETAIL) == 6

    def test_all_sbir_alns_is_superset_of_exclusive(self):
        assert EXCLUSIVE_SBIR_ALNS <= ALL_SBIR_ALNS

    def test_exclusive_alns_is_strict_subset(self):
        # There are non-exclusive agencies so exclusive should be strictly smaller
        assert EXCLUSIVE_SBIR_ALNS < ALL_SBIR_ALNS

    def test_every_agency_has_nonempty_alns_list(self):
        for agency, info in SBIR_ASSISTANCE_LISTING_NUMBERS.items():
            assert len(info["alns"]) > 0, f"{agency} has empty alns list"

    def test_every_agency_has_exclusive_flag(self):
        for agency, info in SBIR_ASSISTANCE_LISTING_NUMBERS.items():
            assert isinstance(info["exclusive"], bool), f"{agency} missing boolean exclusive flag"

    def test_all_sbir_alns_count_matches_individual_agencies(self):
        expected = set()
        for info in SBIR_ASSISTANCE_LISTING_NUMBERS.values():
            expected.update(info["alns"])
        assert ALL_SBIR_ALNS == frozenset(expected)


# ---------------------------------------------------------------------------
# parse_research_code()
# ---------------------------------------------------------------------------


class TestParseResearchCode:
    """Tests for parse_research_code()."""

    @pytest.mark.parametrize(
        "code, expected",
        [
            ("SR1", ("SBIR", 1)),
            ("SR2", ("SBIR", 2)),
            ("SR3", ("SBIR", 3)),
            ("ST1", ("STTR", 1)),
            ("ST2", ("STTR", 2)),
            ("ST3", ("STTR", 3)),
        ],
    )
    def test_valid_codes(self, code, expected):
        assert parse_research_code(code) == expected

    def test_none_input(self):
        assert parse_research_code(None) is None

    def test_empty_string(self):
        assert parse_research_code("") is None

    def test_whitespace_only(self):
        assert parse_research_code("   ") is None

    @pytest.mark.parametrize("code", ["sr1", "sr2", "st3", "Sr1", "sT2"])
    def test_case_insensitive(self, code):
        result = parse_research_code(code)
        assert result is not None

    def test_leading_trailing_whitespace(self):
        assert parse_research_code("  SR1  ") == ("SBIR", 1)

    @pytest.mark.parametrize("code", ["SR4", "ST0", "XX1", "SBIR", "foo", "12"])
    def test_invalid_codes(self, code):
        assert parse_research_code(code) is None

    def test_returns_tuple_of_str_and_int(self):
        program, phase = parse_research_code("SR2")
        assert isinstance(program, str)
        assert isinstance(phase, int)


# ---------------------------------------------------------------------------
# is_sbir_grant()
# ---------------------------------------------------------------------------


class TestIsSbirGrant:
    """Tests for is_sbir_grant()."""

    # --- exclusive ALNs ---
    @pytest.mark.parametrize(
        "aln",
        [
            "10.212",   # USDA
            "12.910",   # DOD
            "12.911",   # DOD
            "43.002",   # NASA
            "43.003",   # NASA
            "47.041",   # NSF
            "47.084",   # NSF
            "66.511",   # EPA
            "66.512",   # EPA
            "97.077",   # DHS
        ],
    )
    def test_exclusive_alns_match(self, aln):
        assert is_sbir_grant(aln) is True

    @pytest.mark.parametrize(
        "aln",
        [
            "10.212",
            "12.910",
        ],
    )
    def test_exclusive_alns_match_strict(self, aln):
        assert is_sbir_grant(aln, strict=True) is True

    # --- shared (non-exclusive) ALNs ---
    @pytest.mark.parametrize(
        "aln",
        [
            "81.049",   # DOE
            "20.701",   # DOT
            "84.133",   # ED
            "93.855",   # HHS
        ],
    )
    def test_shared_alns_match_non_strict(self, aln):
        assert is_sbir_grant(aln) is True

    @pytest.mark.parametrize(
        "aln",
        [
            "81.049",   # DOE
            "20.701",   # DOT
            "84.133",   # ED
            "93.855",   # HHS
        ],
    )
    def test_shared_alns_rejected_strict(self, aln):
        assert is_sbir_grant(aln, strict=True) is False

    # --- non-SBIR ALNs ---
    @pytest.mark.parametrize("aln", ["99.999", "10.001", "00.000", "12.345"])
    def test_non_sbir_alns(self, aln):
        assert is_sbir_grant(aln) is False

    def test_none_input(self):
        assert is_sbir_grant(None) is False

    def test_empty_string(self):
        assert is_sbir_grant("") is False

    def test_whitespace_stripped(self):
        assert is_sbir_grant("  12.910  ") is True

    def test_whitespace_only(self):
        assert is_sbir_grant("   ") is False


# ---------------------------------------------------------------------------
# _parse_sbir_from_description()
# ---------------------------------------------------------------------------


class TestParseSbirFromDescription:
    """Tests for _parse_sbir_from_description()."""

    def test_sbir_keyword(self):
        result = _parse_sbir_from_description("SBIR award for research")
        assert result is not None
        assert result["program"] == "SBIR"

    def test_sttr_keyword(self):
        result = _parse_sbir_from_description("STTR Phase I contract")
        assert result is not None
        assert result["program"] == "STTR"

    def test_both_sbir_and_sttr_prefers_sbir(self):
        # When both present, is_sbir is True and is_sttr is True,
        # but the logic: "STTR" if is_sttr and not is_sbir → False → "SBIR"
        result = _parse_sbir_from_description("SBIR and STTR combined program")
        assert result is not None
        assert result["program"] == "SBIR"

    def test_case_insensitive(self):
        result = _parse_sbir_from_description("sbir phase ii research")
        assert result is not None
        assert result["program"] == "SBIR"

    # --- phase extraction with roman numerals ---
    @pytest.mark.parametrize(
        "desc, expected_phase",
        [
            ("SBIR Phase I award", 1),
            ("SBIR Phase II contract", 2),
            ("SBIR Phase III production", 3),
        ],
    )
    def test_phase_roman_numeral(self, desc, expected_phase):
        result = _parse_sbir_from_description(desc)
        assert result["phase"] == expected_phase

    # --- phase extraction with arabic numerals ---
    @pytest.mark.parametrize(
        "desc, expected_phase",
        [
            ("SBIR Phase 1 award", 1),
            ("SBIR Phase 2 contract", 2),
            ("SBIR Phase 3 production", 3),
        ],
    )
    def test_phase_arabic_numeral(self, desc, expected_phase):
        result = _parse_sbir_from_description(desc)
        assert result["phase"] == expected_phase

    def test_no_phase_detected(self):
        result = _parse_sbir_from_description("SBIR research grant")
        assert result is not None
        assert result["phase"] is None
        assert result["confidence"] == 0.5

    def test_phase_increases_confidence(self):
        with_phase = _parse_sbir_from_description("SBIR Phase II")
        without_phase = _parse_sbir_from_description("SBIR grant")
        assert with_phase["confidence"] == 0.7
        assert without_phase["confidence"] == 0.5

    def test_small_business_innovation_fallback(self):
        result = _parse_sbir_from_description("Small Business Innovation Research")
        assert result is not None
        assert result["program"] == "SBIR/STTR"

    def test_small_business_technology_fallback(self):
        result = _parse_sbir_from_description("Small Business Technology Transfer")
        assert result is not None
        assert result["program"] == "SBIR/STTR"

    def test_no_match_returns_none(self):
        assert _parse_sbir_from_description("Generic defense contract") is None

    def test_empty_string_returns_none(self):
        assert _parse_sbir_from_description("") is None

    def test_method_is_description_parsing(self):
        result = _parse_sbir_from_description("SBIR Phase I")
        assert result["method"] == "description_parsing"

    def test_phase_iii_matched_before_phase_i(self):
        """Phase III pattern checked before Phase I to avoid partial match."""
        result = _parse_sbir_from_description("SBIR Phase III")
        assert result["phase"] == 3


# ---------------------------------------------------------------------------
# classify_sbir_award()
# ---------------------------------------------------------------------------


class TestClassifySbirAward:
    """Tests for classify_sbir_award() — precedence and method selection."""

    # --- precedence: research_code > cfda > description ---
    def test_research_code_takes_precedence_over_cfda(self):
        result = classify_sbir_award(research_code="SR2", cfda_number="12.910")
        assert result["method"] == "fpds_research_field"
        assert result["program"] == "SBIR"
        assert result["phase"] == 2

    def test_research_code_takes_precedence_over_description(self):
        result = classify_sbir_award(research_code="ST1", description="SBIR Phase II")
        assert result["method"] == "fpds_research_field"
        assert result["program"] == "STTR"
        assert result["phase"] == 1

    def test_cfda_takes_precedence_over_description(self):
        result = classify_sbir_award(cfda_number="12.910", description="SBIR Phase II")
        assert result["method"] == "assistance_listing_number"

    # --- research_code method ---
    def test_classify_via_research_code(self):
        result = classify_sbir_award(research_code="SR1")
        assert result == {
            "program": "SBIR",
            "phase": 1,
            "method": "fpds_research_field",
            "confidence": 1.0,
        }

    def test_classify_via_sttr_research_code(self):
        result = classify_sbir_award(research_code="ST3")
        assert result["program"] == "STTR"
        assert result["phase"] == 3
        assert result["confidence"] == 1.0

    # --- cfda method ---
    def test_classify_via_exclusive_aln(self):
        result = classify_sbir_award(cfda_number="12.910")
        assert result["method"] == "assistance_listing_number"
        assert result["program"] == "SBIR/STTR"
        assert result["phase"] is None
        assert result["confidence"] == 1.0

    def test_classify_via_shared_aln(self):
        result = classify_sbir_award(cfda_number="81.049")
        assert result["method"] == "assistance_listing_number"
        assert result["confidence"] == 0.8

    def test_non_sbir_aln_falls_through(self):
        result = classify_sbir_award(cfda_number="99.999")
        assert result is None

    # --- description method ---
    def test_classify_via_description(self):
        result = classify_sbir_award(description="SBIR Phase II research")
        assert result["method"] == "description_parsing"
        assert result["program"] == "SBIR"
        assert result["phase"] == 2

    def test_classify_description_no_match(self):
        result = classify_sbir_award(description="Generic procurement award")
        assert result is None

    # --- all None ---
    def test_all_none_returns_none(self):
        result = classify_sbir_award()
        assert result is None

    def test_all_empty_returns_none(self):
        result = classify_sbir_award(research_code="", cfda_number="", description="")
        assert result is None

    # --- invalid research_code falls through to cfda ---
    def test_invalid_research_code_falls_to_cfda(self):
        result = classify_sbir_award(research_code="XX9", cfda_number="12.910")
        assert result["method"] == "assistance_listing_number"

    # --- invalid research_code and cfda falls to description ---
    def test_invalid_code_and_cfda_falls_to_description(self):
        result = classify_sbir_award(
            research_code="XX9", cfda_number="99.999", description="STTR Phase III"
        )
        assert result["method"] == "description_parsing"
        assert result["program"] == "STTR"
        assert result["phase"] == 3
