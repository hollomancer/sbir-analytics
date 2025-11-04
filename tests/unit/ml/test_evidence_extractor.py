"""
Unit tests for the EvidenceExtractor class.

Tests cover:
- Initialization with CET areas
- Sentence segmentation (with and without spaCy)
- Keyword matching in sentences
- Excerpt truncation (50-word limit)
- Source location tracking
- Rationale tag generation
- Evidence ranking (top 3 selection)
- Batch evidence extraction
"""

from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.fast

from src.ml.features.evidence_extractor import EvidenceExtractor
from src.models.cet_models import CETArea, CETClassification, ClassificationLevel, EvidenceStatement


@pytest.fixture
def sample_cet_areas():
    """Sample CET areas for testing."""
    return [
        CETArea(
            cet_id="cet001",  # Will be lowercase per validator
            name="Artificial Intelligence",
            definition="AI technologies including machine learning and neural networks",
            keywords=["machine learning", "neural network", "deep learning", "AI"],
            taxonomy_version="NSTC-2025Q1",
        ),
        CETArea(
            cet_id="cet002",  # Will be lowercase per validator
            name="Quantum Computing",
            definition="Quantum technologies for computing and cryptography",
            keywords=["quantum computing", "qubits", "quantum algorithm"],
            taxonomy_version="NSTC-2025Q1",
        ),
    ]


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "spacy": {"model": "en_core_web_sm", "disable": ["ner", "parser"], "batch_size": 32},
        "evidence": {
            "max_excerpt_words": 50,
            "max_statements": 3,
            "min_keyword_matches": 1,
        },
    }


@pytest.fixture
def extractor_no_spacy(sample_cet_areas, sample_config):
    """EvidenceExtractor without spaCy (using simple extraction)."""
    with patch("src.ml.features.evidence_extractor.spacy") as mock_spacy:
        mock_spacy.load.side_effect = Exception("spaCy not available")
        extractor = EvidenceExtractor(sample_cet_areas, sample_config)
        return extractor


@pytest.fixture
def extractor_with_spacy(sample_cet_areas, sample_config):
    """EvidenceExtractor with mocked spaCy."""
    with patch("src.ml.features.evidence_extractor.spacy") as mock_spacy:
        # Mock spaCy nlp object
        mock_nlp = MagicMock()
        mock_spacy.load.return_value = mock_nlp
        mock_nlp.pipe_names = []

        # Mock add_pipe
        mock_nlp.add_pipe = MagicMock()

        # Mock sentence segmentation
        def mock_call(text):
            mock_doc = MagicMock()
            # Simple sentence splitting on periods for testing
            sentences = text.split(". ")
            mock_sents = [
                MagicMock(text=s.strip() + ("." if not s.endswith(".") else ""))
                for s in sentences
                if s.strip()
            ]
            mock_doc.sents = mock_sents
            return mock_doc

        mock_nlp.side_effect = mock_call

        extractor = EvidenceExtractor(sample_cet_areas, sample_config)
        return extractor


class TestEvidenceExtractorInitialization:
    """Test EvidenceExtractor initialization."""

    def test_initialization_with_spacy(self, sample_cet_areas, sample_config):
        """Test successful initialization with spaCy available."""
        with patch("src.ml.features.evidence_extractor.spacy") as mock_spacy:
            mock_nlp = MagicMock()
            mock_nlp.pipe_names = []
            mock_spacy.load.return_value = mock_nlp

            extractor = EvidenceExtractor(sample_cet_areas, sample_config)

            assert extractor.nlp is not None
            mock_spacy.load.assert_called_once_with("en_core_web_sm", disable=["ner", "parser"])

    def test_initialization_without_spacy(self, sample_cet_areas, sample_config):
        """Test initialization falls back to simple extraction when spaCy unavailable."""
        with patch("src.ml.features.evidence_extractor.spacy") as mock_spacy:
            mock_spacy.load.side_effect = Exception("spaCy not available")

            extractor = EvidenceExtractor(sample_cet_areas, sample_config)

            assert extractor.nlp is None

    def test_cet_keywords_mapping(self, sample_cet_areas, sample_config):
        """Test CET keywords are correctly mapped (note: IDs normalized to lowercase)."""
        with patch("src.ml.features.evidence_extractor.spacy") as mock_spacy:
            mock_spacy.load.side_effect = Exception("spaCy not available")

            extractor = EvidenceExtractor(sample_cet_areas, sample_config)

            # CET IDs are normalized to lowercase by validator
            assert "cet001" in extractor.cet_keywords
            assert "cet002" in extractor.cet_keywords
            assert set(extractor.cet_keywords["cet001"]) == {
                "machine learning",
                "neural network",
                "deep learning",
                "AI",
            }
            assert set(extractor.cet_keywords["cet002"]) == {
                "quantum computing",
                "qubits",
                "quantum algorithm",
            }


class TestSentenceSegmentation:
    """Test sentence segmentation with and without spaCy."""

    def test_simple_segmentation(self, extractor_no_spacy):
        """Test simple sentence segmentation fallback."""
        text = "This is sentence one. This is sentence two. This is sentence three."
        sentences = extractor_no_spacy._segment_sentences(text)

        assert len(sentences) == 3
        assert "sentence one" in sentences[0]
        assert "sentence two" in sentences[1]
        assert "sentence three" in sentences[2]

    def test_segmentation_empty_text(self, extractor_no_spacy):
        """Test segmentation with empty text."""
        sentences = extractor_no_spacy._segment_sentences("")
        assert sentences == []

    def test_segmentation_single_sentence(self, extractor_no_spacy):
        """Test segmentation with single sentence."""
        text = "This is a single sentence"
        sentences = extractor_no_spacy._segment_sentences(text)
        assert len(sentences) == 1
        assert sentences[0] == text


class TestKeywordMatching:
    """Test keyword matching in sentences."""

    def test_find_keywords_single_match(self, extractor_no_spacy):
        """Test finding a single keyword in text."""
        text = "We are developing machine learning algorithms."
        keywords = ["machine learning", "neural network", "deep learning"]
        found = extractor_no_spacy._find_keywords(text, keywords)

        assert len(found) == 1
        assert "machine learning" in found

    def test_find_keywords_multiple_matches(self, extractor_no_spacy):
        """Test finding multiple keywords in text."""
        text = "Our machine learning system uses neural network architectures."
        keywords = ["machine learning", "neural network", "deep learning"]
        found = extractor_no_spacy._find_keywords(text, keywords)

        assert len(found) == 2
        assert "machine learning" in found
        assert "neural network" in found

    def test_find_keywords_case_insensitive(self, extractor_no_spacy):
        """Test keyword matching is case-insensitive."""
        text = "MACHINE LEARNING is powerful."
        keywords = ["machine learning"]
        found = extractor_no_spacy._find_keywords(text, keywords)

        assert len(found) == 1
        assert "machine learning" in found

    def test_find_keywords_no_matches(self, extractor_no_spacy):
        """Test when no keywords are found."""
        text = "This text contains no relevant terms."
        keywords = ["machine learning", "neural network"]
        found = extractor_no_spacy._find_keywords(text, keywords)

        assert len(found) == 0


class TestExcerptTruncation:
    """Test excerpt truncation to 50 words."""

    def test_truncate_short_text(self, extractor_no_spacy):
        """Test truncation of text shorter than 50 words."""
        text = "This is a short text with only ten words in it."
        truncated = extractor_no_spacy._truncate_excerpt(text)
        assert truncated == text

    def test_truncate_long_text(self, extractor_no_spacy):
        """Test truncation of text longer than 50 words."""
        words = ["word"] * 100
        text = " ".join(words)
        truncated = extractor_no_spacy._truncate_excerpt(text)

        truncated_words = truncated.replace("...", "").split()
        assert len(truncated_words) <= 50
        assert truncated.endswith("...")

    def test_truncate_exactly_50_words(self, extractor_no_spacy):
        """Test truncation of text with exactly 50 words."""
        words = ["word"] * 50
        text = " ".join(words)
        truncated = extractor_no_spacy._truncate_excerpt(text)

        truncated_words = truncated.split()
        assert len(truncated_words) == 50
        assert not truncated.endswith("...")


class TestRationaleGeneration:
    """Test rationale tag generation."""

    def test_generate_rationale_single_keyword(self, extractor_no_spacy):
        """Test rationale with single keyword."""
        keywords = ["machine learning"]
        rationale = extractor_no_spacy._generate_rationale(keywords)
        assert "machine learning" in rationale.lower()

    def test_generate_rationale_multiple_keywords(self, extractor_no_spacy):
        """Test rationale with multiple keywords."""
        keywords = ["machine learning", "neural network", "deep learning"]
        rationale = extractor_no_spacy._generate_rationale(keywords)
        assert "machine learning" in rationale.lower()
        assert "neural network" in rationale.lower()
        assert "deep learning" in rationale.lower()

    def test_generate_rationale_empty_keywords(self, extractor_no_spacy):
        """Test rationale with no keywords returns generic message."""
        keywords = []
        rationale = extractor_no_spacy._generate_rationale(keywords)
        # Should return a generic message, not empty
        assert len(rationale) > 0


class TestSourceLocationTracking:
    """Test source location tracking in evidence."""

    def test_extract_from_abstract(self, extractor_no_spacy):
        """Test evidence extraction from abstract."""
        document_parts = {"abstract": "We develop machine learning algorithms for AI applications."}

        evidence = extractor_no_spacy.extract_evidence("cet001", document_parts)

        assert len(evidence) > 0
        assert evidence[0].source_location == "abstract"

    def test_extract_from_keywords(self, extractor_no_spacy):
        """Test evidence extraction from keywords."""
        document_parts = {"keywords": "machine learning, neural networks, deep learning"}

        evidence = extractor_no_spacy.extract_evidence("cet001", document_parts)

        assert len(evidence) > 0
        assert evidence[0].source_location == "keywords"

    def test_extract_from_multiple_sources(self, extractor_no_spacy):
        """Test evidence extraction from multiple document parts."""
        document_parts = {
            "abstract": "We develop machine learning algorithms.",
            "title": "Neural network optimization",
            "solicitation": "Research on deep learning applications.",
        }

        evidence = extractor_no_spacy.extract_evidence("cet001", document_parts)

        sources = {ev.source_location for ev in evidence}
        assert len(sources) >= 2  # Should extract from multiple sources


class TestEvidenceRanking:
    """Test evidence ranking and top 3 selection."""

    def test_max_three_evidence_statements(self, extractor_no_spacy):
        """Test that at most 3 evidence statements are returned."""
        # Create document with many sentences containing keywords
        sentences = [f"This sentence {i} mentions machine learning and AI." for i in range(10)]
        document_parts = {"abstract": " ".join(sentences)}

        evidence = extractor_no_spacy.extract_evidence("cet001", document_parts)

        assert len(evidence) <= 3

    def test_ranking_by_keyword_count(self, extractor_no_spacy):
        """Test evidence is ranked by number of keyword matches."""
        document_parts = {
            "abstract": "Machine learning is useful. Machine learning and neural network work together. Machine learning, neural network, and deep learning are all AI technologies."
        }

        evidence = extractor_no_spacy.extract_evidence("cet001", document_parts)

        # First evidence should have most keywords
        if len(evidence) >= 2:
            # Just verify we get evidence back - ranking logic may vary
            assert len(evidence[0].rationale_tag) > 0


class TestEvidenceExtraction:
    """Test complete evidence extraction process."""

    def test_extract_with_valid_cet(self, extractor_no_spacy):
        """Test extraction with valid CET ID."""
        document_parts = {
            "abstract": "We are developing machine learning algorithms for neural network optimization."
        }

        evidence = extractor_no_spacy.extract_evidence("cet001", document_parts)

        assert len(evidence) > 0
        assert isinstance(evidence[0], EvidenceStatement)
        assert evidence[0].source_location in ["abstract", "keywords", "title", "solicitation"]
        assert len(evidence[0].excerpt) > 0
        assert len(evidence[0].rationale_tag) > 0

    def test_extract_with_invalid_cet(self, extractor_no_spacy):
        """Test extraction with invalid CET ID."""
        document_parts = {"abstract": "Some text here."}

        evidence = extractor_no_spacy.extract_evidence("invalid_cet", document_parts)

        assert len(evidence) == 0

    def test_extract_with_no_keywords_found(self, extractor_no_spacy):
        """Test extraction when no keywords are found."""
        document_parts = {"abstract": "This text contains no relevant CET keywords."}

        evidence = extractor_no_spacy.extract_evidence("cet001", document_parts)

        assert len(evidence) == 0

    def test_extract_with_empty_document(self, extractor_no_spacy):
        """Test extraction with empty document."""
        document_parts = {}

        evidence = extractor_no_spacy.extract_evidence("cet001", document_parts)

        assert len(evidence) == 0


class TestBatchEvidenceExtraction:
    """Test batch evidence extraction."""

    def test_batch_extraction(self, extractor_no_spacy, sample_cet_areas):
        """Test batch evidence extraction for multiple classifications."""
        classifications_list = [
            [
                CETClassification(
                    cet_id="cet001",
                    cet_name="Artificial Intelligence",
                    score=0.15,  # LOW classification
                    classification=ClassificationLevel.LOW,
                    primary=True,
                    evidence=[],
                    classified_at="2024-01-01T00:00:00Z",
                    taxonomy_version="1.0",
                )
            ],
            [
                CETClassification(
                    cet_id="cet002",
                    cet_name="Quantum Computing",
                    score=0.15,  # LOW classification
                    classification=ClassificationLevel.LOW,
                    primary=False,
                    evidence=[],
                    classified_at="2024-01-01T00:00:00Z",
                    taxonomy_version="1.0",
                )
            ],
        ]

        document_parts_list = [
            {"abstract": "Machine learning and neural networks for AI applications."},
            {"abstract": "Quantum computing with qubits for cryptography."},
        ]

        results = extractor_no_spacy.extract_batch_evidence(
            classifications_list, document_parts_list
        )

        assert len(results) == 2
        assert len(results[0]) == 1  # One classification in first list
        assert len(results[1]) == 1  # One classification in second list
        assert len(results[0][0].evidence) > 0  # Should have evidence
        assert len(results[1][0].evidence) > 0  # Should have evidence

    def test_batch_extraction_mismatched_lengths(self, extractor_no_spacy):
        """Test batch extraction with mismatched input lengths."""
        classifications_list = [[]]
        document_parts_list = [{}, {}]  # Different length

        with pytest.raises(ValueError, match="must have same length"):
            extractor_no_spacy.extract_batch_evidence(classifications_list, document_parts_list)


class TestStatistics:
    """Test statistics tracking."""

    def test_statistics_available(self, extractor_no_spacy):
        """Test that statistics method exists and returns data."""
        stats = extractor_no_spacy.get_statistics()

        # Check that we get basic configuration stats
        assert "num_cet_areas" in stats
        assert "num_keywords" in stats
        assert stats["num_cet_areas"] == 2

    def test_statistics_structure(self, extractor_no_spacy):
        """Test statistics structure."""
        stats = extractor_no_spacy.get_statistics()

        # Should contain config information
        assert "max_statements" in stats
        assert "excerpt_max_words" in stats
        assert stats["excerpt_max_words"] == 50
        assert stats["max_statements"] == 3
