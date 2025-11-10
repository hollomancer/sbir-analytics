"""
Tests for src/transition/features/cet_analyzer.py

Tests the CETSignalExtractor for extracting CET (Critical and Emerging
Technologies) area alignment signals between SBIR awards and contracts.
"""

import pytest

from src.models.transition_models import CETSignal
from src.transition.features.cet_analyzer import (
    CET_KEYWORD_MAPPINGS,
    CETAnalysisResult,
    CETSignalExtractor,
    create_cet_extractor,
)


@pytest.fixture
def extractor():
    """Default CETSignalExtractor for testing."""
    return CETSignalExtractor()


@pytest.fixture
def custom_keywords():
    """Custom CET keyword mappings for testing."""
    return {
        "Test Technology": ["test keyword", "sample tech"],
        "Research Area": ["research", "development"],
    }


class TestCETSignalExtractorInitialization:
    """Tests for CETSignalExtractor initialization."""

    def test_initialization_with_defaults(self):
        """Test initialization with default keyword mappings."""
        extractor = CETSignalExtractor()

        assert extractor.keyword_mappings == CET_KEYWORD_MAPPINGS
        assert extractor.compiled_patterns is not None
        assert len(extractor.compiled_patterns) > 0

    def test_initialization_with_custom_keywords(self, custom_keywords):
        """Test initialization with custom keyword mappings."""
        extractor = CETSignalExtractor(cet_keyword_mappings=custom_keywords)

        assert extractor.keyword_mappings == custom_keywords
        assert len(extractor.compiled_patterns) == 2
        assert "Test Technology" in extractor.compiled_patterns
        assert "Research Area" in extractor.compiled_patterns

    def test_pattern_compilation(self, extractor):
        """Test regex patterns are compiled for all CET areas."""
        # Should have patterns for all CET areas
        assert len(extractor.compiled_patterns) > 0

        # Each area should have list of compiled patterns
        for _cet_area, patterns in extractor.compiled_patterns.items():
            assert isinstance(patterns, list)
            assert len(patterns) > 0

    def test_patterns_are_case_insensitive(self, extractor):
        """Test compiled patterns are case-insensitive."""
        # Get a pattern from AI area
        ai_patterns = extractor.compiled_patterns.get("Artificial Intelligence", [])
        assert len(ai_patterns) > 0

        # Test that pattern matches regardless of case
        test_pattern = ai_patterns[0]  # Should be for "artificial intelligence"
        assert test_pattern.search("Artificial Intelligence") is not None
        assert test_pattern.search("ARTIFICIAL INTELLIGENCE") is not None
        assert test_pattern.search("artificial intelligence") is not None


class TestExtractAwardCET:
    """Tests for extract_award_cet method."""

    def test_extract_award_cet_from_cet_area_field(self, extractor):
        """Test extracting CET from cet_area field."""
        award = {"cet_area": "Artificial Intelligence"}

        result = extractor.extract_award_cet(award)

        assert result == "Artificial Intelligence"

    def test_extract_award_cet_from_technology_area_field(self, extractor):
        """Test extracting CET from technology_area field."""
        award = {"technology_area": "Quantum Computing"}

        result = extractor.extract_award_cet(award)

        assert result == "Quantum Computing"

    def test_extract_award_cet_from_focus_area_field(self, extractor):
        """Test extracting CET from focus_area field."""
        award = {"focus_area": "Biotechnology"}

        result = extractor.extract_award_cet(award)

        assert result == "Biotechnology"

    def test_extract_award_cet_from_research_area_field(self, extractor):
        """Test extracting CET from research_area field."""
        award = {"research_area": "Space Technology"}

        result = extractor.extract_award_cet(award)

        assert result == "Space Technology"

    def test_extract_award_cet_from_CET_field(self, extractor):
        """Test extracting CET from CET field."""
        award = {"CET": "Microelectronics"}

        result = extractor.extract_award_cet(award)

        assert result == "Microelectronics"

    def test_extract_award_cet_field_priority(self, extractor):
        """Test extraction uses first available field."""
        award = {
            "cet_area": "AI",
            "technology_area": "Quantum",
        }

        result = extractor.extract_award_cet(award)

        # Should return first field found (cet_area)
        assert result == "AI"

    def test_extract_award_cet_strips_whitespace(self, extractor):
        """Test extraction strips whitespace."""
        award = {"cet_area": "  Artificial Intelligence  "}

        result = extractor.extract_award_cet(award)

        assert result == "Artificial Intelligence"

    def test_extract_award_cet_no_field(self, extractor):
        """Test extraction returns None when no CET field present."""
        award = {"agency": "DOD", "award_id": "123"}

        result = extractor.extract_award_cet(award)

        assert result is None

    def test_extract_award_cet_empty_string(self, extractor):
        """Test extraction returns None for empty string."""
        award = {"cet_area": ""}

        result = extractor.extract_award_cet(award)

        assert result is None

    def test_extract_award_cet_none_value(self, extractor):
        """Test extraction returns None for None value."""
        award = {"cet_area": None}

        result = extractor.extract_award_cet(award)

        assert result is None

    def test_extract_award_cet_from_none_award(self, extractor):
        """Test extraction handles None award gracefully."""
        result = extractor.extract_award_cet(None)

        assert result is None


class TestInferContractCET:
    """Tests for infer_contract_cet method."""

    def test_infer_contract_cet_ai_keywords(self, extractor):
        """Test inferring AI CET from contract description."""
        description = "Develop artificial intelligence and machine learning system"

        cet, confidence = extractor.infer_contract_cet(description)

        assert cet == "Artificial Intelligence"
        assert confidence > 0.0

    def test_infer_contract_cet_quantum_keywords(self, extractor):
        """Test inferring quantum CET from description."""
        description = "Research in quantum computing and quantum sensing technologies"

        cet, confidence = extractor.infer_contract_cet(description)

        assert cet == "Quantum Information Science"
        assert confidence > 0.0

    def test_infer_contract_cet_biotech_keywords(self, extractor):
        """Test inferring biotech CET from description."""
        description = "CRISPR-based genetic engineering for vaccine development"

        cet, confidence = extractor.infer_contract_cet(description)

        assert cet == "Biotechnology"
        assert confidence > 0.0

    def test_infer_contract_cet_space_keywords(self, extractor):
        """Test inferring space CET from description."""
        description = "Development of satellite systems for orbital missions"

        cet, confidence = extractor.infer_contract_cet(description)

        assert cet == "Space Technology"
        assert confidence > 0.0

    def test_infer_contract_cet_multiple_matches(self, extractor):
        """Test inference returns best match when multiple CET areas match."""
        # Description with both AI and quantum keywords
        description = (
            "quantum computing machine learning artificial intelligence quantum sensing"
        )

        cet, confidence = extractor.infer_contract_cet(description)

        # Should return one of the matching areas (the one with highest score)
        assert cet is not None
        assert cet in ["Artificial Intelligence", "Quantum Information Science"]

    def test_infer_contract_cet_case_insensitive(self, extractor):
        """Test inference is case-insensitive."""
        description = "ARTIFICIAL INTELLIGENCE AND MACHINE LEARNING"

        cet, confidence = extractor.infer_contract_cet(description)

        assert cet == "Artificial Intelligence"
        assert confidence > 0.0

    def test_infer_contract_cet_word_boundaries(self, extractor):
        """Test inference respects word boundaries."""
        # "AI" should only match as whole word, not in "SAIL"
        description = "sailing vessel navigation system"

        cet, confidence = extractor.infer_contract_cet(description)

        # Should not match AI
        if cet == "Artificial Intelligence":
            # If it matched, confidence should be low
            assert confidence < 0.1
        else:
            # Or it should match a different area or None
            assert cet != "Artificial Intelligence"

    def test_infer_contract_cet_confidence_based_on_density(self, extractor):
        """Test confidence score based on keyword density."""
        # More keywords should give higher confidence
        dense_description = (
            "machine learning deep learning neural network AI computer vision NLP"
        )
        sparse_description = "system with machine learning"

        _, dense_conf = extractor.infer_contract_cet(dense_description)
        _, sparse_conf = extractor.infer_contract_cet(sparse_description)

        assert dense_conf > sparse_conf

    def test_infer_contract_cet_no_match(self, extractor):
        """Test inference returns None when no keywords match."""
        description = "Generic IT support services"

        cet, confidence = extractor.infer_contract_cet(description)

        assert cet is None
        assert confidence == 0.0

    def test_infer_contract_cet_none_description(self, extractor):
        """Test inference handles None description."""
        cet, confidence = extractor.infer_contract_cet(None)

        assert cet is None
        assert confidence == 0.0

    def test_infer_contract_cet_empty_description(self, extractor):
        """Test inference handles empty description."""
        cet, confidence = extractor.infer_contract_cet("")

        assert cet is None
        assert confidence == 0.0

    def test_infer_contract_cet_non_string_description(self, extractor):
        """Test inference handles non-string description."""
        cet, confidence = extractor.infer_contract_cet(123)

        assert cet is None
        assert confidence == 0.0


class TestCalculateAlignment:
    """Tests for calculate_alignment method."""

    def test_calculate_alignment_exact_match(self, extractor):
        """Test alignment score for exact match."""
        alignment = extractor.calculate_alignment(
            "Artificial Intelligence",
            "Artificial Intelligence",
        )

        assert alignment == 1.0

    def test_calculate_alignment_exact_match_case_insensitive(self, extractor):
        """Test exact match is case-insensitive."""
        alignment = extractor.calculate_alignment(
            "Artificial Intelligence",
            "artificial intelligence",
        )

        assert alignment == 1.0

    def test_calculate_alignment_partial_match_substring(self, extractor):
        """Test partial match for substring."""
        alignment = extractor.calculate_alignment(
            "AI",
            "Artificial Intelligence",
        )

        assert alignment == 0.5

    def test_calculate_alignment_partial_match_reverse_substring(self, extractor):
        """Test partial match works in reverse direction."""
        alignment = extractor.calculate_alignment(
            "Quantum Information Science",
            "Quantum",
        )

        assert alignment == 0.5

    def test_calculate_alignment_no_match(self, extractor):
        """Test alignment score for no match."""
        alignment = extractor.calculate_alignment(
            "Artificial Intelligence",
            "Biotechnology",
        )

        assert alignment == 0.0

    def test_calculate_alignment_none_award_cet(self, extractor):
        """Test alignment returns 0.0 when award CET is None."""
        alignment = extractor.calculate_alignment(
            None,
            "Artificial Intelligence",
        )

        assert alignment == 0.0

    def test_calculate_alignment_none_contract_cet(self, extractor):
        """Test alignment returns 0.0 when contract CET is None."""
        alignment = extractor.calculate_alignment(
            "Artificial Intelligence",
            None,
        )

        assert alignment == 0.0

    def test_calculate_alignment_both_none(self, extractor):
        """Test alignment returns 0.0 when both are None."""
        alignment = extractor.calculate_alignment(None, None)

        assert alignment == 0.0

    def test_calculate_alignment_strips_whitespace(self, extractor):
        """Test alignment strips whitespace before comparison."""
        alignment = extractor.calculate_alignment(
            "  Artificial Intelligence  ",
            "Artificial Intelligence",
        )

        assert alignment == 1.0


class TestExtractSignal:
    """Tests for extract_signal method."""

    def test_extract_signal_with_exact_match(self, extractor):
        """Test signal extraction with exact CET match."""
        award = {"cet_area": "Artificial Intelligence"}
        description = "Machine learning and artificial intelligence research"

        signal = extractor.extract_signal(award, description, weight=0.10)

        assert isinstance(signal, CETSignal)
        assert signal.award_cet == "Artificial Intelligence"
        assert signal.contract_cet == "Artificial Intelligence"
        # Alignment 1.0 * weight 0.10 = 0.10
        assert signal.cet_alignment_score == 0.10

    def test_extract_signal_with_no_match(self, extractor):
        """Test signal extraction with no CET match."""
        award = {"cet_area": "Space Technology"}
        description = "Machine learning artificial intelligence"

        signal = extractor.extract_signal(award, description, weight=0.10)

        assert signal.award_cet == "Space Technology"
        assert signal.contract_cet == "Artificial Intelligence"
        # No alignment (different areas) = 0.0
        assert signal.cet_alignment_score == 0.0

    def test_extract_signal_no_award_cet(self, extractor):
        """Test signal extraction when award has no CET."""
        award = {"agency": "DOD"}
        description = "Artificial intelligence research"

        signal = extractor.extract_signal(award, description, weight=0.10)

        assert signal.award_cet is None
        assert signal.contract_cet == "Artificial Intelligence"
        assert signal.cet_alignment_score == 0.0

    def test_extract_signal_no_contract_description(self, extractor):
        """Test signal extraction without contract description."""
        award = {"cet_area": "Artificial Intelligence"}

        signal = extractor.extract_signal(award, None, weight=0.10)

        assert signal.award_cet == "Artificial Intelligence"
        assert signal.contract_cet is None
        assert signal.cet_alignment_score == 0.0

    def test_extract_signal_custom_weight(self, extractor):
        """Test signal extraction with custom weight."""
        award = {"cet_area": "Artificial Intelligence"}
        description = "Machine learning system"

        signal = extractor.extract_signal(award, description, weight=0.25)

        # Alignment 1.0 * weight 0.25 = 0.25
        assert signal.cet_alignment_score == 0.25

    def test_extract_signal_partial_match(self, extractor):
        """Test signal extraction with partial match."""
        award = {"cet_area": "AI"}
        description = "Artificial intelligence research"

        signal = extractor.extract_signal(award, description, weight=0.10)

        assert signal.award_cet == "AI"
        assert signal.contract_cet == "Artificial Intelligence"
        # Partial match: alignment 0.5 * weight 0.10 = 0.05
        assert signal.cet_alignment_score == 0.05


class TestBatchExtractSignals:
    """Tests for batch_extract_signals method."""

    def test_batch_extract_signals_single_pairs(self, extractor):
        """Test batch extraction with single award-contract pair."""
        awards = [{"cet_area": "Artificial Intelligence"}]
        contracts = [{"description": "Machine learning research"}]

        signals = extractor.batch_extract_signals(awards, contracts, weight=0.10)

        assert len(signals) == 1
        award_idx, contract_idx, signal = signals[0]
        assert award_idx == 0
        assert contract_idx == 0
        assert signal.award_cet == "Artificial Intelligence"

    def test_batch_extract_signals_multiple_pairs(self, extractor):
        """Test batch extraction with multiple award-contract pairs."""
        awards = [
            {"cet_area": "Artificial Intelligence"},
            {"cet_area": "Space Technology"},
        ]
        contracts = [
            {"description": "Machine learning"},
            {"description": "Satellite systems"},
        ]

        signals = extractor.batch_extract_signals(awards, contracts, weight=0.10)

        # 2 awards × 2 contracts = 4 signals
        assert len(signals) == 4

        # Check that all combinations are present
        indices = {(a, c) for a, c, _ in signals}
        assert indices == {(0, 0), (0, 1), (1, 0), (1, 1)}

    def test_batch_extract_signals_empty_awards(self, extractor):
        """Test batch extraction with no awards."""
        awards = []
        contracts = [{"description": "Test"}]

        signals = extractor.batch_extract_signals(awards, contracts)

        assert len(signals) == 0

    def test_batch_extract_signals_empty_contracts(self, extractor):
        """Test batch extraction with no contracts."""
        awards = [{"cet_area": "AI"}]
        contracts = []

        signals = extractor.batch_extract_signals(awards, contracts)

        assert len(signals) == 0

    def test_batch_extract_signals_preserves_indices(self, extractor):
        """Test batch extraction preserves award and contract indices."""
        awards = [
            {"cet_area": "AI"},
            {"cet_area": "Space"},
        ]
        contracts = [
            {"description": "ML"},
            {"description": "Satellite"},
        ]

        signals = extractor.batch_extract_signals(awards, contracts)

        # Check specific pair
        award_1_contract_1 = [s for a, c, s in signals if a == 1 and c == 1][0]
        assert award_1_contract_1.award_cet == "Space"

    def test_batch_extract_signals_contract_without_description(self, extractor):
        """Test batch extraction handles contracts without description field."""
        awards = [{"cet_area": "AI"}]
        contracts = [{"contract_id": "123"}]  # No description

        signals = extractor.batch_extract_signals(awards, contracts)

        assert len(signals) == 1
        _, _, signal = signals[0]
        assert signal.contract_cet is None


class TestGetAnalysisReport:
    """Tests for get_analysis_report method."""

    def test_get_analysis_report_exact_match(self, extractor):
        """Test analysis report with exact CET match."""
        award = {"cet_area": "Artificial Intelligence"}
        description = "Machine learning and artificial intelligence"

        report = extractor.get_analysis_report(award, description)

        assert isinstance(report, CETAnalysisResult)
        assert report.award_cet == "Artificial Intelligence"
        assert report.contract_cet == "Artificial Intelligence"
        assert report.alignment_score == 1.0
        assert report.confidence == "exact_match"
        assert report.notes is None

    def test_get_analysis_report_partial_match(self, extractor):
        """Test analysis report with partial match."""
        award = {"cet_area": "AI"}
        description = "Artificial intelligence research"

        report = extractor.get_analysis_report(award, description)

        assert report.alignment_score == 0.5
        assert report.confidence == "partial_match"

    def test_get_analysis_report_no_match(self, extractor):
        """Test analysis report with no match."""
        award = {"cet_area": "Space Technology"}
        description = "Machine learning research"

        report = extractor.get_analysis_report(award, description)

        assert report.alignment_score == 0.0
        assert report.confidence == "no_match"
        assert "does not align" in report.notes

    def test_get_analysis_report_no_award_cet(self, extractor):
        """Test analysis report when award has no CET."""
        award = {"agency": "DOD"}
        description = "Machine learning"

        report = extractor.get_analysis_report(award, description)

        assert report.award_cet is None
        assert report.notes == "Award has no CET classification"

    def test_get_analysis_report_no_contract_match(self, extractor):
        """Test analysis report when contract description has no CET match."""
        award = {"cet_area": "Artificial Intelligence"}
        description = "Generic IT services"

        report = extractor.get_analysis_report(award, description)

        assert report.contract_cet is None
        assert report.notes == "Contract description did not match any CET area keywords"


class TestCreateCETExtractor:
    """Tests for create_cet_extractor factory function."""

    def test_create_cet_extractor_default(self):
        """Test factory creates extractor with default mappings."""
        extractor = create_cet_extractor()

        assert isinstance(extractor, CETSignalExtractor)
        assert extractor.keyword_mappings == CET_KEYWORD_MAPPINGS

    def test_create_cet_extractor_custom_keywords(self, custom_keywords):
        """Test factory creates extractor with custom keywords."""
        extractor = create_cet_extractor(custom_keywords=custom_keywords)

        assert isinstance(extractor, CETSignalExtractor)
        assert extractor.keyword_mappings == custom_keywords


class TestCETKeywordMappings:
    """Tests for default CET keyword mappings."""

    def test_default_mappings_exist(self):
        """Test default CET keyword mappings are defined."""
        assert CET_KEYWORD_MAPPINGS is not None
        assert len(CET_KEYWORD_MAPPINGS) > 0

    def test_default_mappings_have_keywords(self):
        """Test all CET areas have keyword lists."""
        for cet_area, keywords in CET_KEYWORD_MAPPINGS.items():
            assert isinstance(cet_area, str)
            assert isinstance(keywords, list)
            assert len(keywords) > 0

    def test_default_mappings_include_ai(self):
        """Test default mappings include Artificial Intelligence."""
        assert "Artificial Intelligence" in CET_KEYWORD_MAPPINGS
        ai_keywords = CET_KEYWORD_MAPPINGS["Artificial Intelligence"]
        assert "machine learning" in ai_keywords
        assert "artificial intelligence" in ai_keywords

    def test_default_mappings_include_quantum(self):
        """Test default mappings include Quantum Information Science."""
        assert "Quantum Information Science" in CET_KEYWORD_MAPPINGS
        quantum_keywords = CET_KEYWORD_MAPPINGS["Quantum Information Science"]
        assert "quantum" in quantum_keywords

    def test_default_mappings_include_biotech(self):
        """Test default mappings include Biotechnology."""
        assert "Biotechnology" in CET_KEYWORD_MAPPINGS
        biotech_keywords = CET_KEYWORD_MAPPINGS["Biotechnology"]
        assert "biotechnology" in biotech_keywords


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_extract_award_cet_from_pydantic_model(self, extractor):
        """Test extraction works with Pydantic models."""
        # Mock Pydantic model
        class MockAward:
            def model_dump(self):
                return {"cet_area": "Artificial Intelligence"}

        award = MockAward()
        result = extractor.extract_award_cet(award)

        assert result == "Artificial Intelligence"

    def test_extract_award_cet_from_object_with_dict(self, extractor):
        """Test extraction works with objects having __dict__."""
        class MockAward:
            def __init__(self):
                self.cet_area = "Space Technology"

        award = MockAward()
        result = extractor.extract_award_cet(award)

        assert result == "Space Technology"

    def test_infer_contract_cet_with_special_characters(self, extractor):
        """Test inference handles special characters in description."""
        description = "AI/ML-based system (machine learning & deep learning)"

        cet, confidence = extractor.infer_contract_cet(description)

        # Should still match AI keywords
        assert cet == "Artificial Intelligence"

    def test_calculate_alignment_with_whitespace_only(self, extractor):
        """Test alignment with whitespace-only strings."""
        alignment = extractor.calculate_alignment("   ", "Artificial Intelligence")

        assert alignment == 0.0

    def test_extract_signal_zero_weight(self, extractor):
        """Test signal extraction with zero weight."""
        award = {"cet_area": "Artificial Intelligence"}
        description = "Machine learning"

        signal = extractor.extract_signal(award, description, weight=0.0)

        # Even with perfect alignment, score should be 0 with 0 weight
        assert signal.cet_alignment_score == 0.0

    def test_batch_extract_signals_with_non_dict_contract(self, extractor):
        """Test batch extraction handles non-dict contracts gracefully."""
        awards = [{"cet_area": "AI"}]
        contracts = ["not a dict"]  # Invalid contract

        signals = extractor.batch_extract_signals(awards, contracts)

        # Should not crash, but contract_cet will be None
        assert len(signals) == 1
        _, _, signal = signals[0]
        assert signal.contract_cet is None
