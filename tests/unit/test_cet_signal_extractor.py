"""
Unit tests for CETSignalExtractor.

Tests cover CET area extraction, inference, alignment calculation,
and batch processing for transition detection signals.
"""

import pytest

from src.transition.features.cet_analyzer import (
    CETAnalysisResult,
    CETSignalExtractor,
    create_cet_extractor,
)


@pytest.fixture
def cet_extractor():
    """Create a CETSignalExtractor instance for testing."""
    return CETSignalExtractor()


@pytest.fixture
def sample_awards():
    """Sample awards with various CET classifications."""
    return [
        {
            "award_id": "A1",
            "cet_area": "Artificial Intelligence",
            "description": "AI research project",
        },
        {
            "award_id": "A2",
            "technology_area": "Advanced Manufacturing",
            "description": "Manufacturing research",
        },
        {
            "award_id": "A3",
            "cet_code": "BIO",
            "description": "Biology research",
        },
        {
            "award_id": "A4",
            # No CET classification
            "description": "Generic research",
        },
    ]


@pytest.fixture
def sample_contracts():
    """Sample contracts with descriptions."""
    return [
        {
            "contract_id": "C1",
            "description": "Development of machine learning and neural network systems for autonomous vehicles",
        },
        {
            "contract_id": "C2",
            "description": "Advanced manufacturing using 3D printing and additive manufacturing techniques",
        },
        {
            "contract_id": "C3",
            "description": "Quantum computing research and quantum sensing applications",
        },
        {
            "contract_id": "C4",
            "description": "Standard software development and IT infrastructure",
        },
    ]


class TestExtractAwardCET:
    """Tests for extract_award_cet method."""

    def test_extract_from_cet_area_field(self, cet_extractor):
        """Test extraction from 'cet_area' field."""
        award = {"cet_area": "Artificial Intelligence"}
        result = cet_extractor.extract_award_cet(award)
        assert result == "Artificial Intelligence"

    def test_extract_from_technology_area_field(self, cet_extractor):
        """Test extraction from 'technology_area' field."""
        award = {"technology_area": "Advanced Manufacturing"}
        result = cet_extractor.extract_award_cet(award)
        assert result == "Advanced Manufacturing"

    def test_extract_from_cet_code_field(self, cet_extractor):
        """Test extraction from 'cet_code' field."""
        award = {"cet_code": "BIO"}
        result = cet_extractor.extract_award_cet(award)
        assert result == "BIO"

    def test_extract_returns_none_when_missing(self, cet_extractor):
        """Test returns None when no CET field present."""
        award = {"award_id": "A1", "description": "Generic award"}
        result = cet_extractor.extract_award_cet(award)
        assert result is None

    def test_extract_returns_none_for_empty_string(self, cet_extractor):
        """Test returns None when CET field is empty string."""
        award = {"cet_area": ""}
        result = cet_extractor.extract_award_cet(award)
        assert result is None

    def test_extract_returns_none_for_none_input(self, cet_extractor):
        """Test returns None for None input."""
        result = cet_extractor.extract_award_cet(None)
        assert result is None

    def test_extract_strips_whitespace(self, cet_extractor):
        """Test extracts and strips whitespace."""
        award = {"cet_area": "  Artificial Intelligence  "}
        result = cet_extractor.extract_award_cet(award)
        assert result == "Artificial Intelligence"


class TestInferContractCET:
    """Tests for infer_contract_cet method."""

    def test_infer_ai_from_description(self, cet_extractor):
        """Test infers AI from contract description."""
        description = "Development of machine learning and neural networks"
        cet_area, confidence = cet_extractor.infer_contract_cet(description)
        assert cet_area == "Artificial Intelligence"
        assert confidence > 0.0

    def test_infer_manufacturing_from_description(self, cet_extractor):
        """Test infers manufacturing from contract description."""
        description = "3D printing and additive manufacturing systems"
        cet_area, confidence = cet_extractor.infer_contract_cet(description)
        assert cet_area == "Advanced Manufacturing"
        assert confidence > 0.0

    def test_infer_quantum_from_description(self, cet_extractor):
        """Test infers quantum from contract description."""
        description = "Quantum sensing and quantum cryptography for secure communications"
        cet_area, confidence = cet_extractor.infer_contract_cet(description)
        assert cet_area in ["Quantum Information Science", "Advanced Computing"]
        assert confidence > 0.0

    def test_infer_returns_none_for_no_match(self, cet_extractor):
        """Test returns None when no CET keywords found."""
        description = "Standard software development and IT infrastructure"
        cet_area, confidence = cet_extractor.infer_contract_cet(description)
        assert cet_area is None
        assert confidence == 0.0

    def test_infer_returns_none_for_empty_description(self, cet_extractor):
        """Test returns None for empty description."""
        cet_area, confidence = cet_extractor.infer_contract_cet("")
        assert cet_area is None
        assert confidence == 0.0

    def test_infer_returns_none_for_none_input(self, cet_extractor):
        """Test returns None for None input."""
        cet_area, confidence = cet_extractor.infer_contract_cet(None)
        assert cet_area is None
        assert confidence == 0.0

    def test_infer_case_insensitive(self, cet_extractor):
        """Test keyword matching is case-insensitive."""
        description = "MACHINE LEARNING and NEURAL NETWORKS"
        cet_area, confidence = cet_extractor.infer_contract_cet(description)
        assert cet_area == "Artificial Intelligence"

    def test_infer_confidence_increases_with_keyword_density(self, cet_extractor):
        """Test confidence score increases with more keywords."""
        description_single = "machine learning"
        _, confidence_single = cet_extractor.infer_contract_cet(description_single)

        description_multiple = (
            "machine learning neural networks deep learning "
            "computer vision autonomous AI/ML systems and NLP"
        )
        _, confidence_multiple = cet_extractor.infer_contract_cet(description_multiple)

        # Confidence should be higher with more matching keywords
        assert confidence_multiple >= confidence_single


class TestCalculateAlignment:
    """Tests for calculate_alignment method."""

    def test_exact_match_returns_one(self, cet_extractor):
        """Test exact match returns 1.0."""
        score = cet_extractor.calculate_alignment(
            "Artificial Intelligence", "Artificial Intelligence"
        )
        assert score == 1.0

    def test_case_insensitive_exact_match(self, cet_extractor):
        """Test exact match is case-insensitive."""
        score = cet_extractor.calculate_alignment(
            "Artificial Intelligence", "artificial intelligence"
        )
        assert score == 1.0

    def test_substring_match_returns_half(self, cet_extractor):
        """Test substring match returns 0.5."""
        score = cet_extractor.calculate_alignment(
            "Advanced Manufacturing", "Advanced Manufacturing Systems"
        )
        assert score == 0.5

    def test_no_match_returns_zero(self, cet_extractor):
        """Test no match returns 0.0."""
        score = cet_extractor.calculate_alignment("Artificial Intelligence", "Biotechnology")
        assert score == 0.0

    def test_missing_award_cet_returns_zero(self, cet_extractor):
        """Test missing award CET returns 0.0."""
        score = cet_extractor.calculate_alignment(None, "Artificial Intelligence")
        assert score == 0.0

    def test_missing_contract_cet_returns_zero(self, cet_extractor):
        """Test missing contract CET returns 0.0."""
        score = cet_extractor.calculate_alignment("Artificial Intelligence", None)
        assert score == 0.0

    def test_both_missing_returns_zero(self, cet_extractor):
        """Test both missing returns 0.0."""
        score = cet_extractor.calculate_alignment(None, None)
        assert score == 0.0


class TestExtractSignal:
    """Tests for extract_signal method."""

    def test_extract_signal_with_exact_match(self, cet_extractor):
        """Test signal extraction with exact CET match."""
        award = {"cet_area": "Artificial Intelligence"}
        description = "Development of machine learning systems"
        signal = cet_extractor.extract_signal(award, description)

        assert signal.award_cet == "Artificial Intelligence"
        assert signal.contract_cet == "Artificial Intelligence"
        assert signal.cet_alignment_score > 0.0

    def test_extract_signal_with_no_alignment(self, cet_extractor):
        """Test signal extraction with no alignment."""
        award = {"cet_area": "Biotechnology"}
        description = "Standard software development"
        signal = cet_extractor.extract_signal(award, description)

        assert signal.award_cet == "Biotechnology"
        assert signal.contract_cet is None
        assert signal.cet_alignment_score == 0.0

    def test_extract_signal_with_missing_award_cet(self, cet_extractor):
        """Test signal extraction when award has no CET."""
        award = {"award_id": "A1"}
        description = "Machine learning systems"
        signal = cet_extractor.extract_signal(award, description)

        assert signal.award_cet is None
        assert signal.contract_cet == "Artificial Intelligence"
        assert signal.cet_alignment_score == 0.0

    def test_extract_signal_respects_weight(self, cet_extractor):
        """Test signal extraction respects weight parameter."""
        award = {"cet_area": "Artificial Intelligence"}
        description = "Machine learning systems"

        signal_default = cet_extractor.extract_signal(award, description, weight=0.10)
        signal_high_weight = cet_extractor.extract_signal(award, description, weight=0.20)

        assert signal_high_weight.cet_alignment_score > signal_default.cet_alignment_score


class TestBatchExtractSignals:
    """Tests for batch_extract_signals method."""

    def test_batch_extract_multiple_pairs(self, cet_extractor, sample_awards, sample_contracts):
        """Test batch extraction of multiple award-contract pairs."""
        signals = cet_extractor.batch_extract_signals(sample_awards, sample_contracts)

        # Should have 4 awards * 4 contracts = 16 pairs
        assert len(signals) == 16

        # Each signal should be a (award_idx, contract_idx, signal) tuple
        for award_idx, contract_idx, signal in signals:
            assert isinstance(award_idx, int)
            assert isinstance(contract_idx, int)
            assert hasattr(signal, "award_cet")
            assert hasattr(signal, "contract_cet")

    def test_batch_extract_returns_correct_indices(self, cet_extractor, sample_awards):
        """Test batch extraction returns correct indices."""
        contracts = [{"description": "Machine learning"}, {"description": "3D printing"}]
        signals = cet_extractor.batch_extract_signals(sample_awards, contracts)

        # Verify indices are correct
        expected_indices = []
        for i in range(len(sample_awards)):
            for j in range(len(contracts)):
                expected_indices.append((i, j))

        actual_indices = [(a, c) for a, c, _ in signals]
        assert actual_indices == expected_indices


class TestGetAnalysisReport:
    """Tests for get_analysis_report method."""

    def test_analysis_report_exact_match(self, cet_extractor):
        """Test analysis report for exact CET match."""
        award = {"cet_area": "Artificial Intelligence"}
        description = "Machine learning and neural networks"
        report = cet_extractor.get_analysis_report(award, description)

        assert isinstance(report, CETAnalysisResult)
        assert report.award_cet == "Artificial Intelligence"
        assert report.contract_cet == "Artificial Intelligence"
        assert report.alignment_score == 1.0
        assert report.confidence == "exact_match"

    def test_analysis_report_no_match(self, cet_extractor):
        """Test analysis report for no CET match."""
        award = {"cet_area": "Biotechnology"}
        description = "Standard software development"
        report = cet_extractor.get_analysis_report(award, description)

        assert report.alignment_score == 0.0
        assert report.confidence == "no_match"
        assert report.notes is not None

    def test_analysis_report_missing_award_cet(self, cet_extractor):
        """Test analysis report when award has no CET."""
        award = {"award_id": "A1"}
        description = "Machine learning"
        report = cet_extractor.get_analysis_report(award, description)

        assert report.award_cet is None
        assert report.notes is not None
        assert "no cet classification" in report.notes.lower()

    def test_analysis_report_missing_contract_cet(self, cet_extractor):
        """Test analysis report when no contract CET inferred."""
        award = {"cet_area": "Artificial Intelligence"}
        description = "Standard software"
        report = cet_extractor.get_analysis_report(award, description)

        assert report.contract_cet is None
        assert "did not match" in report.notes.lower()


class TestFactoryFunction:
    """Tests for create_cet_extractor factory function."""

    def test_factory_creates_extractor(self):
        """Test factory function creates CETSignalExtractor."""
        extractor = create_cet_extractor()
        assert isinstance(extractor, CETSignalExtractor)

    def test_factory_with_custom_keywords(self):
        """Test factory with custom keyword mappings."""
        custom_keywords = {"CustomArea": ["custom", "keyword"]}
        extractor = create_cet_extractor(custom_keywords=custom_keywords)

        cet_area, confidence = extractor.infer_contract_cet("This has custom keyword")
        assert cet_area == "CustomArea"
        assert confidence > 0.0


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_very_long_description(self, cet_extractor):
        """Test with very long description."""
        long_desc = "machine learning " * 1000  # Repeat 'machine learning' many times
        cet_area, confidence = cet_extractor.infer_contract_cet(long_desc)

        assert cet_area == "Artificial Intelligence"
        assert confidence == 1.0  # Should cap at 1.0

    def test_description_with_special_characters(self, cet_extractor):
        """Test with special characters in description."""
        description = "AI/ML (machine-learning) @ neural_networks"
        cet_area, confidence = cet_extractor.infer_contract_cet(description)

        assert cet_area == "Artificial Intelligence"
        assert confidence > 0.0

    def test_mixed_case_keywords(self, cet_extractor):
        """Test with mixed case in description."""
        description = "MaChInE LeArNiNg NeUrAl NeTwOrK"
        cet_area, confidence = cet_extractor.infer_contract_cet(description)

        assert cet_area == "Artificial Intelligence"
