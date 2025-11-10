"""
Tests for src/transition/features/patent_analyzer.py

Tests the PatentSignalExtractor for extracting patent-related signals
that indicate SBIR Phase III commercialization through federal contracts.
"""

from datetime import date, timedelta
from unittest.mock import Mock, patch

import pytest

from src.models.patent import Patent
from src.models.transition_models import PatentSignal
from src.transition.features.patent_analyzer import PatentSignalExtractor


@pytest.fixture
def extractor():
    """Default PatentSignalExtractor for testing."""
    return PatentSignalExtractor(
        topic_similarity_threshold=0.7,
        use_abstract=True,
        use_title=True,
    )


@pytest.fixture
def sample_patents():
    """Sample patent data for testing."""
    return [
        Patent(
            patent_id="US001",
            title="Advanced Machine Learning System",
            abstract="A novel machine learning system for data analysis",
            filing_date=date(2023, 3, 1),
            assignee="Acme Corporation",
        ),
        Patent(
            patent_id="US002",
            title="Distributed Computing Framework",
            abstract="Framework for distributed computation across nodes",
            filing_date=date(2023, 7, 15),
            assignee="Acme Corporation",
        ),
        Patent(
            patent_id="US003",
            title="Data Encryption Method",
            abstract="Novel approach to data encryption",
            filing_date=date(2024, 1, 10),
            assignee="Beta Technologies",  # Different assignee
        ),
    ]


class TestPatentSignalExtractorInitialization:
    """Tests for PatentSignalExtractor initialization."""

    def test_initialization_with_defaults(self):
        """Test initialization with default parameters."""
        extractor = PatentSignalExtractor()

        assert extractor.topic_similarity_threshold == 0.7
        assert extractor.use_abstract is True
        assert extractor.use_title is True
        assert extractor.vectorizer is not None

    def test_initialization_with_custom_params(self):
        """Test initialization with custom parameters."""
        extractor = PatentSignalExtractor(
            topic_similarity_threshold=0.8,
            use_abstract=False,
            use_title=True,
        )

        assert extractor.topic_similarity_threshold == 0.8
        assert extractor.use_abstract is False
        assert extractor.use_title is True

    def test_vectorizer_configuration(self):
        """Test TF-IDF vectorizer is configured correctly."""
        extractor = PatentSignalExtractor()

        assert extractor.vectorizer.max_features == 500
        assert extractor.vectorizer.stop_words == "english"
        assert extractor.vectorizer.ngram_range == (1, 2)
        assert extractor.vectorizer.lowercase is True


class TestExtractSignals:
    """Tests for extract_signals method."""

    def test_extract_signals_no_patents(self, extractor):
        """Test extract_signals with no patents returns zero signal."""
        award_completion = date(2023, 6, 1)
        contract_start = date(2023, 9, 1)

        signal = extractor.extract_signals(
            patents=[],
            award_completion_date=award_completion,
            contract_start_date=contract_start,
        )

        assert signal.patent_count == 0
        assert signal.patents_pre_contract == 0
        assert signal.patent_topic_similarity is None
        assert signal.avg_filing_lag_days is None
        assert signal.patent_score == 0.0

    def test_extract_signals_with_patents(self, extractor, sample_patents):
        """Test extract_signals with patent data."""
        award_completion = date(2023, 6, 1)
        contract_start = date(2023, 9, 1)

        signal = extractor.extract_signals(
            patents=sample_patents,
            award_completion_date=award_completion,
            contract_start_date=contract_start,
            contract_description="Machine learning analysis system",
            vendor_name="Acme Corporation",
        )

        assert signal.patent_count == 3
        assert signal.patents_pre_contract == 1  # US001 filed before contract
        assert signal.patent_score > 0.0

    def test_extract_signals_counts_pre_contract_patents(self, extractor):
        """Test extract_signals counts patents filed before contract start."""
        patents = [
            Patent(
                patent_id="US001",
                title="Test Patent 1",
                filing_date=date(2023, 5, 1),  # Before contract
                assignee="Acme",
            ),
            Patent(
                patent_id="US002",
                title="Test Patent 2",
                filing_date=date(2023, 8, 1),  # Before contract
                assignee="Acme",
            ),
            Patent(
                patent_id="US003",
                title="Test Patent 3",
                filing_date=date(2023, 10, 1),  # After contract
                assignee="Acme",
            ),
        ]

        signal = extractor.extract_signals(
            patents=patents,
            award_completion_date=date(2023, 6, 1),
            contract_start_date=date(2023, 9, 1),
        )

        assert signal.patents_pre_contract == 2

    def test_extract_signals_calculates_avg_filing_lag(self, extractor):
        """Test extract_signals calculates average filing lag in days."""
        award_completion = date(2023, 6, 1)
        contract_start = date(2023, 9, 1)

        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2023, 6, 11),  # 10 days after award
                assignee="Acme",
            ),
            Patent(
                patent_id="US002",
                title="Test",
                filing_date=date(2023, 7, 1),  # 30 days after award
                assignee="Acme",
            ),
        ]

        signal = extractor.extract_signals(
            patents=patents,
            award_completion_date=award_completion,
            contract_start_date=contract_start,
        )

        # Average: (10 + 30) / 2 = 20 days
        assert signal.avg_filing_lag_days == 20.0

    def test_extract_signals_no_patents_in_window(self, extractor):
        """Test extract_signals when no patents in timing window."""
        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2022, 1, 1),  # Way before award
                assignee="Acme",
            ),
        ]

        signal = extractor.extract_signals(
            patents=patents,
            award_completion_date=date(2023, 6, 1),
            contract_start_date=date(2023, 9, 1),
        )

        assert signal.patent_count == 1
        assert signal.avg_filing_lag_days is None  # No patents in window

    def test_extract_signals_with_topic_similarity(self, extractor, sample_patents):
        """Test extract_signals calculates topic similarity."""
        signal = extractor.extract_signals(
            patents=sample_patents,
            award_completion_date=date(2023, 6, 1),
            contract_start_date=date(2023, 9, 1),
            contract_description="Machine learning system for advanced data analysis",
            award_description="Research into ML algorithms",
        )

        # Should have topic similarity since we have matching keywords
        assert signal.patent_topic_similarity is not None
        assert 0.0 <= signal.patent_topic_similarity <= 1.0

    def test_extract_signals_without_contract_description(self, extractor, sample_patents):
        """Test extract_signals without contract description skips similarity."""
        signal = extractor.extract_signals(
            patents=sample_patents,
            award_completion_date=date(2023, 6, 1),
            contract_start_date=date(2023, 9, 1),
            contract_description=None,  # No description
        )

        assert signal.patent_topic_similarity is None


class TestFilterByTiming:
    """Tests for _filter_by_timing method."""

    def test_filter_by_timing_patents_in_window(self, extractor):
        """Test filtering patents in timing window."""
        award_completion = date(2023, 6, 1)
        contract_start = date(2023, 9, 1)

        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2023, 7, 1),  # In window
                assignee="Acme",
            ),
            Patent(
                patent_id="US002",
                title="Test",
                filing_date=date(2023, 8, 15),  # In window
                assignee="Acme",
            ),
        ]

        filtered = extractor._filter_by_timing(patents, award_completion, contract_start)

        assert len(filtered) == 2

    def test_filter_by_timing_allows_pre_award_buffer(self, extractor):
        """Test filtering allows patents up to 6 months before award."""
        award_completion = date(2023, 6, 1)
        contract_start = date(2023, 9, 1)

        # 6 months before award = Dec 1, 2022 (180 days)
        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2022, 12, 3),  # ~180 days before award (in window)
                assignee="Acme",
            ),
            Patent(
                patent_id="US002",
                title="Test",
                filing_date=date(2022, 11, 1),  # Too early (out of window)
                assignee="Acme",
            ),
        ]

        filtered = extractor._filter_by_timing(patents, award_completion, contract_start)

        assert len(filtered) == 1
        assert filtered[0].patent_id == "US001"

    def test_filter_by_timing_allows_post_contract_buffer(self, extractor):
        """Test filtering allows patents up to 90 days after contract."""
        award_completion = date(2023, 6, 1)
        contract_start = date(2023, 9, 1)

        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2023, 10, 15),  # Within 90 days after contract
                assignee="Acme",
            ),
            Patent(
                patent_id="US002",
                title="Test",
                filing_date=date(2024, 1, 1),  # Too late (>90 days)
                assignee="Acme",
            ),
        ]

        filtered = extractor._filter_by_timing(patents, award_completion, contract_start)

        assert len(filtered) == 1
        assert filtered[0].patent_id == "US001"

    def test_filter_by_timing_skips_patents_without_dates(self, extractor):
        """Test filtering skips patents without filing dates."""
        award_completion = date(2023, 6, 1)
        contract_start = date(2023, 9, 1)

        patents = [
            Patent(patent_id="US001", title="Test", filing_date=None, assignee="Acme"),
            Patent(
                patent_id="US002",
                title="Test",
                filing_date=date(2023, 7, 1),
                assignee="Acme",
            ),
        ]

        filtered = extractor._filter_by_timing(patents, award_completion, contract_start)

        assert len(filtered) == 1
        assert filtered[0].patent_id == "US002"


class TestCalculateTopicSimilarity:
    """Tests for _calculate_topic_similarity method."""

    def test_calculate_topic_similarity_with_similar_content(self, extractor):
        """Test topic similarity with similar patent and contract content."""
        patents = [
            Patent(
                patent_id="US001",
                title="Machine Learning System",
                abstract="Advanced machine learning for data analysis",
                filing_date=date(2023, 7, 1),
                assignee="Acme",
            ),
        ]

        similarity = extractor._calculate_topic_similarity(
            patents=patents,
            contract_description="Machine learning data analysis system",
        )

        assert similarity is not None
        assert similarity > 0.5  # Should be fairly similar

    def test_calculate_topic_similarity_with_different_content(self, extractor):
        """Test topic similarity with unrelated content."""
        patents = [
            Patent(
                patent_id="US001",
                title="Medical Device Innovation",
                abstract="Novel approach to medical diagnostics",
                filing_date=date(2023, 7, 1),
                assignee="Acme",
            ),
        ]

        similarity = extractor._calculate_topic_similarity(
            patents=patents,
            contract_description="Software development for financial systems",
        )

        assert similarity is not None
        assert similarity < 0.5  # Should be dissimilar

    def test_calculate_topic_similarity_uses_title_only(self):
        """Test topic similarity uses only title when configured."""
        extractor = PatentSignalExtractor(use_title=True, use_abstract=False)

        patents = [
            Patent(
                patent_id="US001",
                title="Machine Learning",
                abstract="Unrelated abstract about biology",  # Should be ignored
                filing_date=date(2023, 7, 1),
                assignee="Acme",
            ),
        ]

        similarity = extractor._calculate_topic_similarity(
            patents=patents,
            contract_description="Machine learning system",
        )

        # Should still find similarity based on title
        assert similarity is not None
        assert similarity > 0.3

    def test_calculate_topic_similarity_uses_abstract_only(self):
        """Test topic similarity uses only abstract when configured."""
        extractor = PatentSignalExtractor(use_title=False, use_abstract=True)

        patents = [
            Patent(
                patent_id="US001",
                title="Unrelated Title",  # Should be ignored
                abstract="Machine learning data analysis system",
                filing_date=date(2023, 7, 1),
                assignee="Acme",
            ),
        ]

        similarity = extractor._calculate_topic_similarity(
            patents=patents,
            contract_description="Machine learning analysis",
        )

        # Should find similarity based on abstract
        assert similarity is not None
        assert similarity > 0.3

    def test_calculate_topic_similarity_includes_award_description(self, extractor):
        """Test topic similarity includes award description in contract text."""
        patents = [
            Patent(
                patent_id="US001",
                title="Quantum Computing",
                abstract="Novel quantum computing approach",
                filing_date=date(2023, 7, 1),
                assignee="Acme",
            ),
        ]

        # Award and contract both mention quantum - should boost similarity
        similarity = extractor._calculate_topic_similarity(
            patents=patents,
            contract_description="Research services",
            award_description="Quantum computing research",
        )

        assert similarity is not None

    def test_calculate_topic_similarity_no_patents(self, extractor):
        """Test topic similarity with no patents returns None."""
        similarity = extractor._calculate_topic_similarity(
            patents=[],
            contract_description="Some contract description",
        )

        assert similarity is None

    def test_calculate_topic_similarity_no_contract_description(self, extractor):
        """Test topic similarity without contract description returns None."""
        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                abstract="Test abstract",
                filing_date=date(2023, 7, 1),
                assignee="Acme",
            ),
        ]

        similarity = extractor._calculate_topic_similarity(
            patents=patents,
            contract_description=None,
        )

        assert similarity is None

    def test_calculate_topic_similarity_patents_without_text(self, extractor):
        """Test topic similarity with patents missing title/abstract."""
        patents = [
            Patent(
                patent_id="US001",
                title=None,
                abstract=None,
                filing_date=date(2023, 7, 1),
                assignee="Acme",
            ),
        ]

        similarity = extractor._calculate_topic_similarity(
            patents=patents,
            contract_description="Some description",
        )

        assert similarity is None

    def test_calculate_topic_similarity_returns_max_similarity(self, extractor):
        """Test topic similarity returns maximum across all patents."""
        patents = [
            Patent(
                patent_id="US001",
                title="Unrelated Topic",
                abstract="Something completely different",
                filing_date=date(2023, 7, 1),
                assignee="Acme",
            ),
            Patent(
                patent_id="US002",
                title="Machine Learning System",
                abstract="Advanced machine learning",
                filing_date=date(2023, 8, 1),
                assignee="Acme",
            ),
        ]

        similarity = extractor._calculate_topic_similarity(
            patents=patents,
            contract_description="Machine learning research",
        )

        # Should return max similarity (from US002)
        assert similarity is not None
        assert similarity > 0.3


class TestDetectTechnologyTransfer:
    """Tests for _detect_technology_transfer method."""

    def test_detect_technology_transfer_same_assignee(self, extractor):
        """Test no technology transfer when assignee matches vendor."""
        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2023, 7, 1),
                assignee="Acme Corporation",
            ),
            Patent(
                patent_id="US002",
                title="Test",
                filing_date=date(2023, 8, 1),
                assignee="ACME CORPORATION",  # Case variation
            ),
        ]

        has_transfer = extractor._detect_technology_transfer(
            patents=patents,
            vendor_name="Acme Corporation",
        )

        assert has_transfer is False

    def test_detect_technology_transfer_different_assignee(self, extractor):
        """Test technology transfer detected with different assignee."""
        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2023, 7, 1),
                assignee="Beta Technologies",  # Different assignee
            ),
        ]

        has_transfer = extractor._detect_technology_transfer(
            patents=patents,
            vendor_name="Acme Corporation",
        )

        assert has_transfer is True

    def test_detect_technology_transfer_partial_match(self, extractor):
        """Test partial name match counts as same assignee."""
        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2023, 7, 1),
                assignee="Acme Corporation LLC",  # Partial match
            ),
        ]

        has_transfer = extractor._detect_technology_transfer(
            patents=patents,
            vendor_name="Acme Corporation",
        )

        # "Acme Corporation" is in "Acme Corporation LLC"
        assert has_transfer is False

    def test_detect_technology_transfer_no_patents(self, extractor):
        """Test no transfer when no patents provided."""
        has_transfer = extractor._detect_technology_transfer(
            patents=[],
            vendor_name="Acme Corporation",
        )

        assert has_transfer is False

    def test_detect_technology_transfer_no_vendor_name(self, extractor):
        """Test no transfer when vendor name not provided."""
        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2023, 7, 1),
                assignee="Some Company",
            ),
        ]

        has_transfer = extractor._detect_technology_transfer(
            patents=patents,
            vendor_name=None,
        )

        assert has_transfer is False

    def test_detect_technology_transfer_patent_without_assignee(self, extractor):
        """Test skips patents without assignee."""
        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2023, 7, 1),
                assignee=None,
            ),
        ]

        has_transfer = extractor._detect_technology_transfer(
            patents=patents,
            vendor_name="Acme Corporation",
        )

        assert has_transfer is False

    def test_detect_technology_transfer_mixed_assignees(self, extractor):
        """Test transfer detected when any patent has different assignee."""
        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2023, 7, 1),
                assignee="Acme Corporation",  # Same
            ),
            Patent(
                patent_id="US002",
                title="Test",
                filing_date=date(2023, 8, 1),
                assignee="Different Company",  # Different
            ),
        ]

        has_transfer = extractor._detect_technology_transfer(
            patents=patents,
            vendor_name="Acme Corporation",
        )

        assert has_transfer is True


class TestCalculatePatentScore:
    """Tests for _calculate_patent_score method."""

    def test_calculate_patent_score_no_patents(self, extractor):
        """Test patent score with no patents."""
        score = extractor._calculate_patent_score(
            patent_count=0,
            patents_in_window=0,
            patents_pre_contract=0,
            topic_similarity=None,
            has_tech_transfer=False,
        )

        assert score == 0.0

    def test_calculate_patent_score_base_score_for_patents(self, extractor):
        """Test base score awarded for having patents."""
        score = extractor._calculate_patent_score(
            patent_count=1,
            patents_in_window=0,
            patents_pre_contract=0,
            topic_similarity=None,
            has_tech_transfer=False,
        )

        assert score == 0.3  # Base score

    def test_calculate_patent_score_with_patents_in_window(self, extractor):
        """Test bonus for patents in timing window."""
        score = extractor._calculate_patent_score(
            patent_count=2,
            patents_in_window=1,
            patents_pre_contract=0,
            topic_similarity=None,
            has_tech_transfer=False,
        )

        # 0.3 (base) + 0.2 (in window) = 0.5
        assert score == 0.5

    def test_calculate_patent_score_with_pre_contract_patents(self, extractor):
        """Test bonus for patents filed before contract."""
        score = extractor._calculate_patent_score(
            patent_count=2,
            patents_in_window=0,
            patents_pre_contract=1,
            topic_similarity=None,
            has_tech_transfer=False,
        )

        # 0.3 (base) + 0.2 (pre-contract) = 0.5
        assert score == 0.5

    def test_calculate_patent_score_with_high_topic_similarity(self, extractor):
        """Test bonus for high topic similarity."""
        score = extractor._calculate_patent_score(
            patent_count=1,
            patents_in_window=0,
            patents_pre_contract=0,
            topic_similarity=0.8,  # Above 0.7 threshold
            has_tech_transfer=False,
        )

        # 0.3 (base) + 0.2 (topic) = 0.5
        assert score == 0.5

    def test_calculate_patent_score_topic_below_threshold(self, extractor):
        """Test no bonus for topic similarity below threshold."""
        score = extractor._calculate_patent_score(
            patent_count=1,
            patents_in_window=0,
            patents_pre_contract=0,
            topic_similarity=0.5,  # Below 0.7 threshold
            has_tech_transfer=False,
        )

        # Only base score
        assert score == 0.3

    def test_calculate_patent_score_with_tech_transfer(self, extractor):
        """Test penalty for technology transfer."""
        score = extractor._calculate_patent_score(
            patent_count=1,
            patents_in_window=0,
            patents_pre_contract=0,
            topic_similarity=None,
            has_tech_transfer=True,
        )

        # 0.3 (base) - 0.1 (tech transfer) = 0.2
        assert score == 0.2

    def test_calculate_patent_score_maximum(self, extractor):
        """Test maximum patent score."""
        score = extractor._calculate_patent_score(
            patent_count=5,
            patents_in_window=3,
            patents_pre_contract=4,
            topic_similarity=0.9,
            has_tech_transfer=False,
        )

        # 0.3 + 0.2 + 0.2 + 0.2 = 0.9
        assert score == 0.9

    def test_calculate_patent_score_capped_at_one(self, extractor):
        """Test patent score capped at 1.0."""
        # Even if components sum > 1.0, should cap at 1.0
        # This shouldn't happen with current weights, but test the cap logic
        score = extractor._calculate_patent_score(
            patent_count=10,
            patents_in_window=10,
            patents_pre_contract=10,
            topic_similarity=1.0,
            has_tech_transfer=False,
        )

        assert score <= 1.0

    def test_calculate_patent_score_floored_at_zero(self, extractor):
        """Test patent score floored at 0.0."""
        # With tech transfer reducing score
        score = extractor._calculate_patent_score(
            patent_count=0,
            patents_in_window=0,
            patents_pre_contract=0,
            topic_similarity=None,
            has_tech_transfer=True,
        )

        # 0.0 - 0.1 = -0.1, but should floor at 0.0
        assert score == 0.0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_extract_signals_handles_vectorizer_error(self, extractor):
        """Test extract_signals handles TF-IDF vectorization errors gracefully."""
        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                abstract="Test",
                filing_date=date(2023, 7, 1),
                assignee="Acme",
            ),
        ]

        # Mock vectorizer to raise exception
        with patch.object(extractor.vectorizer, "fit_transform", side_effect=Exception("Error")):
            signal = extractor.extract_signals(
                patents=patents,
                award_completion_date=date(2023, 6, 1),
                contract_start_date=date(2023, 9, 1),
                contract_description="Test description",
            )

            # Should handle error and return None for topic similarity
            assert signal.patent_topic_similarity is None
            # But should still return other metrics
            assert signal.patent_count == 1

    def test_extract_signals_with_same_award_and_contract_dates(self, extractor):
        """Test extract_signals when award completion equals contract start."""
        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2023, 6, 15),  # Between award and contract
                assignee="Acme",
            ),
        ]

        signal = extractor.extract_signals(
            patents=patents,
            award_completion_date=date(2023, 6, 1),
            contract_start_date=date(2023, 6, 1),  # Same day
        )

        # Should still work
        assert signal.patent_count == 1

    def test_filter_by_timing_with_inverted_dates(self, extractor):
        """Test filtering when contract start is before award completion."""
        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2023, 7, 1),
                assignee="Acme",
            ),
        ]

        # Inverted dates (contract before award)
        filtered = extractor._filter_by_timing(
            patents=patents,
            award_completion_date=date(2023, 9, 1),
            contract_start_date=date(2023, 6, 1),
        )

        # Should still apply logic (may return patents or empty list)
        assert isinstance(filtered, list)

    def test_calculate_topic_similarity_single_word_texts(self, extractor):
        """Test topic similarity with very short texts."""
        patents = [
            Patent(
                patent_id="US001",
                title="ML",
                abstract="AI",
                filing_date=date(2023, 7, 1),
                assignee="Acme",
            ),
        ]

        similarity = extractor._calculate_topic_similarity(
            patents=patents,
            contract_description="ML",
        )

        # Should handle short texts
        assert similarity is not None

    def test_detect_technology_transfer_case_insensitive(self, extractor):
        """Test technology transfer detection is case-insensitive."""
        patents = [
            Patent(
                patent_id="US001",
                title="Test",
                filing_date=date(2023, 7, 1),
                assignee="acme corporation",  # Lowercase
            ),
        ]

        has_transfer = extractor._detect_technology_transfer(
            patents=patents,
            vendor_name="ACME CORPORATION",  # Uppercase
        )

        assert has_transfer is False  # Should match despite case difference
