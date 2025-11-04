"""Unit tests for PatentSignalExtractor."""

from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.fast

from src.models.patent import Patent
from src.transition.features.patent_analyzer import PatentSignalExtractor


@pytest.fixture
def extractor():
    """Create patent signal extractor with default settings."""
    return PatentSignalExtractor(
        topic_similarity_threshold=0.7,
        use_abstract=True,
        use_title=True,
    )


@pytest.fixture
def base_date():
    """Base date for testing (award completion)."""
    return date(2024, 1, 15)


@pytest.fixture
def sample_patents(base_date):
    """Sample patents for testing."""
    return [
        Patent(
            patent_number="US10000001",
            title="Advanced Radar System for Defense Applications",
            abstract="A novel radar system with improved target detection capabilities for military use.",
            filing_date=base_date + timedelta(days=30),  # 1 month after award
            grant_date=base_date + timedelta(days=400),
            assignee="Acme Defense Corp",
            uspc_class="342",
        ),
        Patent(
            patent_number="US10000002",
            title="Signal Processing Method for Radar",
            abstract="Improved signal processing algorithm for enhanced radar performance.",
            filing_date=base_date + timedelta(days=120),  # 4 months after award
            grant_date=base_date + timedelta(days=500),
            assignee="Acme Defense Corp",
            uspc_class="342",
        ),
        Patent(
            patent_number="US10000003",
            title="Unrelated Software Patent",
            abstract="A method for social media content recommendation.",
            filing_date=base_date - timedelta(days=200),  # Before award
            grant_date=base_date - timedelta(days=50),
            assignee="Acme Defense Corp",
            uspc_class="707",
        ),
    ]


def test_extract_signals_with_no_patents(extractor, base_date):
    """Test extraction with no patents."""
    contract_date = base_date + timedelta(days=200)

    signal = extractor.extract_signals(
        patents=[],
        award_completion_date=base_date,
        contract_start_date=contract_date,
        contract_description="Radar system development",
    )

    assert signal.patent_count == 0
    assert signal.patents_pre_contract == 0
    assert signal.patent_topic_similarity is None
    assert signal.patent_score == 0.0


def test_extract_signals_with_relevant_patents(extractor, sample_patents, base_date):
    """Test extraction with patents in timing window."""
    contract_date = base_date + timedelta(days=200)  # ~6.5 months after award

    signal = extractor.extract_signals(
        patents=sample_patents,
        award_completion_date=base_date,
        contract_start_date=contract_date,
        contract_description="Advanced radar system for defense applications",
        vendor_name="Acme Defense Corp",
    )

    assert signal.patent_count == 3
    assert signal.patents_pre_contract == 3  # All filed before contract
    assert signal.patent_topic_similarity is not None
    assert signal.patent_topic_similarity > 0.3  # Should have some similarity (radar keywords)
    assert signal.patent_score > 0.0


def test_timing_window_filtering(extractor, sample_patents, base_date):
    """Test that patents are correctly filtered by timing window."""
    contract_date = base_date + timedelta(days=150)

    # Patent 1: filed 30 days after award (within window)
    # Patent 2: filed 120 days after award (within window)
    # Patent 3: filed before award (outside window)

    patents_in_window = extractor._filter_by_timing(
        sample_patents,
        base_date,
        contract_date,
    )

    # Should include patents 1 and 2 (filed between award and contract)
    assert len(patents_in_window) >= 2
    patent_numbers = [p.patent_number for p in patents_in_window]
    assert "US10000001" in patent_numbers
    assert "US10000002" in patent_numbers


def test_timing_window_includes_pre_award_buffer(extractor, base_date):
    """Test that timing window includes 6-month buffer before award."""
    # Patent filed 3 months before award completion
    pre_award_patent = Patent(
        patent_number="US9999999",
        title="Early Research Patent",
        abstract="Patent filed during award execution",
        filing_date=base_date - timedelta(days=90),
        grant_date=base_date + timedelta(days=200),
        assignee="Test Corp",
    )

    contract_date = base_date + timedelta(days=100)

    patents_in_window = extractor._filter_by_timing(
        [pre_award_patent],
        base_date,
        contract_date,
    )

    # Should include patent filed 3 months before (within 6-month buffer)
    assert len(patents_in_window) == 1


def test_topic_similarity_with_matching_content(extractor):
    """Test topic similarity with matching patent/contract content."""
    patents = [
        Patent(
            patent_number="US10000001",
            title="Advanced Radar Detection System",
            abstract="Novel methods for radar target detection and tracking in defense applications.",
            filing_date=date(2024, 1, 1),
            grant_date=date(2024, 6, 1),
            assignee="Test Corp",
        ),
    ]

    contract_description = "Development of advanced radar systems for military target detection"

    similarity = extractor._calculate_topic_similarity(
        patents,
        contract_description,
    )

    assert similarity is not None
    assert (
        similarity > 0.2
    )  # Should have reasonable similarity due to "radar", "detection" keywords


def test_topic_similarity_with_non_matching_content(extractor):
    """Test topic similarity with non-matching content."""
    patents = [
        Patent(
            patent_number="US10000001",
            title="Social Media Recommendation Algorithm",
            abstract="Methods for recommending content to users on social media platforms.",
            filing_date=date(2024, 1, 1),
            grant_date=date(2024, 6, 1),
            assignee="Test Corp",
        ),
    ]

    contract_description = "Development of advanced radar systems for military applications"

    similarity = extractor._calculate_topic_similarity(
        patents,
        contract_description,
    )

    assert similarity is not None
    assert similarity < 0.3  # Should have low similarity (different topics)


def test_topic_similarity_with_no_patent_text(extractor):
    """Test topic similarity when patents have no text content."""
    patents = [
        Patent(
            patent_number="US10000001",
            title="",  # Empty string instead of None (title is required)
            abstract="",  # Empty string instead of None
            filing_date=date(2024, 1, 1),
            grant_date=date(2024, 6, 1),
            assignee="Test Corp",
        ),
    ]

    contract_description = "Some contract description"

    similarity = extractor._calculate_topic_similarity(
        patents,
        contract_description,
    )

    assert similarity is None  # Cannot calculate without text


def test_topic_similarity_with_award_description(extractor):
    """Test that award description is included in similarity calculation."""
    patents = [
        Patent(
            patent_number="US10000001",
            title="Research System",
            abstract="Basic research on detection systems.",
            filing_date=date(2024, 1, 1),
            grant_date=date(2024, 6, 1),
            assignee="Test Corp",
        ),
    ]

    contract_description = "System development"
    award_description = "Research on advanced detection methods for target tracking"

    # With award description, should increase context and potentially improve matching
    similarity_with_award = extractor._calculate_topic_similarity(
        patents,
        contract_description,
        award_description,
    )

    similarity_without_award = extractor._calculate_topic_similarity(
        patents,
        contract_description,
    )

    assert similarity_with_award is not None
    assert similarity_without_award is not None
    # Both should work, values may differ due to additional context


def test_technology_transfer_detection_same_assignee(extractor):
    """Test technology transfer detection with same assignee."""
    patents = [
        Patent(
            patent_number="US10000001",
            title="Test Patent",
            filing_date=date(2024, 1, 1),
            assignee="Acme Corporation",
        ),
    ]

    has_transfer = extractor._detect_technology_transfer(
        patents,
        vendor_name="Acme Corporation",
    )

    assert has_transfer is False  # Same assignee, no transfer


def test_technology_transfer_detection_different_assignee(extractor):
    """Test technology transfer detection with different assignee."""
    patents = [
        Patent(
            patent_number="US10000001",
            title="Test Patent",
            filing_date=date(2024, 1, 1),
            assignee="Big Tech Company",
        ),
    ]

    has_transfer = extractor._detect_technology_transfer(
        patents,
        vendor_name="Small Startup Inc",
    )

    assert has_transfer is True  # Different assignee, transfer detected


def test_technology_transfer_with_partial_name_match(extractor):
    """Test technology transfer with partial name matching."""
    patents = [
        Patent(
            patent_number="US10000001",
            title="Test Patent",
            filing_date=date(2024, 1, 1),
            assignee="Acme Corporation of America",
        ),
    ]

    # Vendor name is substring of assignee - should match
    has_transfer = extractor._detect_technology_transfer(
        patents,
        vendor_name="Acme Corporation",
    )

    assert has_transfer is False  # Partial match counts as same assignee


def test_technology_transfer_with_no_assignee(extractor):
    """Test technology transfer when patent has no assignee."""
    patents = [
        Patent(
            patent_number="US10000001",
            title="Test Patent",
            filing_date=date(2024, 1, 1),
            assignee=None,
        ),
    ]

    has_transfer = extractor._detect_technology_transfer(
        patents,
        vendor_name="Test Corp",
    )

    assert has_transfer is False  # Cannot detect without assignee info


def test_patent_score_calculation_no_patents(extractor):
    """Test patent score with no patents."""
    score = extractor._calculate_patent_score(
        patent_count=0,
        patents_in_window=0,
        patents_pre_contract=0,
        topic_similarity=None,
        has_tech_transfer=False,
    )

    assert score == 0.0


def test_patent_score_calculation_with_all_signals(extractor):
    """Test patent score with all positive signals."""
    score = extractor._calculate_patent_score(
        patent_count=5,
        patents_in_window=3,
        patents_pre_contract=4,
        topic_similarity=0.85,  # Above threshold (0.7)
        has_tech_transfer=False,
    )

    # Should have: 0.3 (has patents) + 0.2 (in window) + 0.2 (pre-contract) + 0.2 (topic) = 0.9
    assert abs(score - 0.9) < 0.01  # Use approximate comparison for floating point


def test_patent_score_with_tech_transfer_penalty(extractor):
    """Test that technology transfer reduces score."""
    score_without_transfer = extractor._calculate_patent_score(
        patent_count=5,
        patents_in_window=3,
        patents_pre_contract=4,
        topic_similarity=0.85,
        has_tech_transfer=False,
    )

    score_with_transfer = extractor._calculate_patent_score(
        patent_count=5,
        patents_in_window=3,
        patents_pre_contract=4,
        topic_similarity=0.85,
        has_tech_transfer=True,
    )

    # Tech transfer should reduce score by 0.1
    assert score_with_transfer == score_without_transfer - 0.1


def test_patent_score_below_topic_threshold(extractor):
    """Test that low topic similarity doesn't add bonus."""
    score_high_similarity = extractor._calculate_patent_score(
        patent_count=5,
        patents_in_window=3,
        patents_pre_contract=4,
        topic_similarity=0.75,  # Above threshold
        has_tech_transfer=False,
    )

    score_low_similarity = extractor._calculate_patent_score(
        patent_count=5,
        patents_in_window=3,
        patents_pre_contract=4,
        topic_similarity=0.50,  # Below threshold (0.7)
        has_tech_transfer=False,
    )

    # Low similarity should not get topic bonus
    assert score_low_similarity == score_high_similarity - 0.2


def test_patent_score_bounds(extractor):
    """Test that patent score stays within [0, 1] bounds."""
    # Try to create score above 1.0
    score = extractor._calculate_patent_score(
        patent_count=100,
        patents_in_window=100,
        patents_pre_contract=100,
        topic_similarity=1.0,
        has_tech_transfer=False,
    )
    assert 0.0 <= score <= 1.0

    # Try to create score below 0.0 (with tech transfer)
    score_negative = extractor._calculate_patent_score(
        patent_count=0,
        patents_in_window=0,
        patents_pre_contract=0,
        topic_similarity=None,
        has_tech_transfer=True,  # -0.1 penalty
    )
    assert score_negative >= 0.0


def test_extract_signals_end_to_end(extractor, sample_patents, base_date):
    """Test full signal extraction pipeline."""
    contract_date = base_date + timedelta(days=180)

    signal = extractor.extract_signals(
        patents=sample_patents,
        award_completion_date=base_date,
        contract_start_date=contract_date,
        contract_description="Advanced radar detection and tracking system for defense",
        award_description="Research on radar technology for military applications",
        vendor_name="Acme Defense Corp",
    )

    # Should extract all signals
    assert signal.patent_count == 3
    assert signal.patents_pre_contract > 0
    assert signal.patent_topic_similarity is not None
    assert signal.patent_score > 0.0

    # Check that score is reasonable
    assert 0.0 <= signal.patent_score <= 1.0


def test_custom_similarity_threshold():
    """Test extractor with custom similarity threshold."""
    strict_extractor = PatentSignalExtractor(
        topic_similarity_threshold=0.9,  # Very strict
    )

    lenient_extractor = PatentSignalExtractor(
        topic_similarity_threshold=0.5,  # Lenient
    )

    # Strict extractor should require higher similarity for bonus
    strict_score = strict_extractor._calculate_patent_score(
        patent_count=5,
        patents_in_window=3,
        patents_pre_contract=4,
        topic_similarity=0.75,  # Below 0.9 threshold
        has_tech_transfer=False,
    )

    lenient_score = lenient_extractor._calculate_patent_score(
        patent_count=5,
        patents_in_window=3,
        patents_pre_contract=4,
        topic_similarity=0.75,  # Above 0.5 threshold
        has_tech_transfer=False,
    )

    assert lenient_score > strict_score


def test_use_title_and_abstract_flags():
    """Test that title/abstract flags control what text is used."""
    title_only_extractor = PatentSignalExtractor(
        use_title=True,
        use_abstract=False,
    )

    abstract_only_extractor = PatentSignalExtractor(
        use_title=False,
        use_abstract=True,
    )

    patents = [
        Patent(
            patent_number="US10000001",
            title="Radar System",
            abstract="Completely unrelated content about software development",
            filing_date=date(2024, 1, 1),
            assignee="Test Corp",
        ),
    ]

    # With title only, should match "Radar System"
    similarity_title = title_only_extractor._calculate_topic_similarity(
        patents,
        "Development of radar systems",
    )

    # With abstract only, should not match well
    similarity_abstract = abstract_only_extractor._calculate_topic_similarity(
        patents,
        "Development of radar systems",
    )

    assert similarity_title is not None
    assert similarity_abstract is not None
    # Title similarity should be higher (has "Radar System")
    assert similarity_title > similarity_abstract
