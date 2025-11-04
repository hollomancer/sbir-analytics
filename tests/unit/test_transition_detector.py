"""
Unit tests for transition detection pipeline.

Tests the TransitionDetector's complete workflow including
candidate selection, vendor matching, scoring, and evidence generation.
"""

from datetime import date, timedelta

import pytest

pytestmark = pytest.mark.fast

from src.models.transition_models import (
    CompetitionType,
    ConfidenceLevel,
    FederalContract,
    Transition,
)
from src.transition.detection.detector import TransitionDetector
from src.transition.features.vendor_resolver import VendorResolver


@pytest.fixture
def sample_config() -> dict:
    """Sample configuration for detector."""
    return {
        "base_score": 0.15,
        "timing_window": {
            "min_days_after_completion": 0,
            "max_days_after_completion": 730,
        },
        "vendor_matching": {
            "require_match": True,
            "fuzzy_threshold": 0.85,
        },
        "scoring": {
            "agency_continuity": {
                "enabled": True,
                "weight": 0.25,
                "same_agency_bonus": 0.25,
                "cross_service_bonus": 0.125,
                "different_dept_bonus": 0.05,
            },
            "timing_proximity": {
                "enabled": True,
                "weight": 0.20,
                "windows": [
                    {"range": [0, 90], "score": 1.0},
                    {"range": [91, 365], "score": 0.75},
                    {"range": [366, 730], "score": 0.5},
                ],
            },
            "competition_type": {
                "enabled": True,
                "weight": 0.20,
                "sole_source_bonus": 0.20,
                "limited_competition_bonus": 0.10,
                "full_and_open_bonus": 0.0,
            },
            "patent_signal": {
                "enabled": True,
                "weight": 0.15,
                "has_patent_bonus": 0.05,
                "patent_pre_contract_bonus": 0.03,
                "patent_topic_match_bonus": 0.02,
                "patent_similarity_threshold": 0.7,
            },
            "cet_alignment": {
                "enabled": True,
                "weight": 0.10,
                "same_cet_area_bonus": 0.05,
            },
        },
        "confidence_thresholds": {
            "high": 0.85,
            "likely": 0.65,
        },
    }


@pytest.fixture
def vendor_resolver():
    """Create vendor resolver with sample data."""
    from src.transition.features.vendor_resolver import VendorRecord

    # Create sample vendor records
    sample_vendors = [
        VendorRecord(
            uei="UEI123",
            cage="CAGE001",
            duns="DUNS001",
            name="Acme Corporation",
            metadata={"vendor_id": "VENDOR-001"},
        ),
        VendorRecord(
            uei="UEI456",
            cage="CAGE002",
            duns="DUNS002",
            name="Tech Innovations Inc",
            metadata={"vendor_id": "VENDOR-002"},
        ),
    ]

    resolver = VendorResolver.from_records(sample_vendors)
    return resolver


@pytest.fixture
def detector(sample_config, vendor_resolver):
    """Create transition detector instance."""
    return TransitionDetector(
        config=sample_config,
        vendor_resolver=vendor_resolver,
    )


@pytest.fixture
def sample_award() -> dict:
    """Sample SBIR award for testing."""
    return {
        "award_id": "AWARD-123",
        "agency": "DOD",
        "department": "Air Force",
        "completion_date": date(2024, 1, 15),
        "vendor_id": "VENDOR-001",
        "vendor_uei": "UEI123",
        "vendor_cage": "CAGE001",
        "vendor_name": "Acme Corporation",
    }


@pytest.fixture
def sample_contracts() -> list[FederalContract]:
    """Sample federal contracts for testing."""
    base_date = date(2024, 1, 15)

    contracts = [
        # High-confidence match: same agency, sole source, within 3 months
        FederalContract(
            contract_id="CONTRACT-001",
            agency="DOD",
            sub_agency="Air Force",
            vendor_uei="UEI123",
            vendor_name="Acme Corporation",
            start_date=base_date + timedelta(days=60),  # 2 months after
            obligation_amount=500000.0,
            competition_type=CompetitionType.SOLE_SOURCE,
        ),
        # Moderate match: same agency, limited competition, 6 months after
        FederalContract(
            contract_id="CONTRACT-002",
            agency="DOD",
            sub_agency="Navy",
            vendor_cage="CAGE001",
            vendor_name="Acme Corporation",
            start_date=base_date + timedelta(days=180),  # 6 months after
            obligation_amount=250000.0,
            competition_type=CompetitionType.LIMITED,
        ),
        # Lower confidence: different agency, full and open, 18 months after
        FederalContract(
            contract_id="CONTRACT-003",
            agency="NASA",
            vendor_duns="DUNS001",
            vendor_name="Acme Corporation",
            start_date=base_date + timedelta(days=540),  # 18 months after
            obligation_amount=1000000.0,
            competition_type=CompetitionType.FULL_AND_OPEN,
        ),
        # Out of window: 3 years after completion
        FederalContract(
            contract_id="CONTRACT-004",
            agency="DOD",
            vendor_uei="UEI123",
            start_date=base_date + timedelta(days=1095),  # 3 years after
            obligation_amount=750000.0,
            competition_type=CompetitionType.SOLE_SOURCE,
        ),
        # Different vendor: should not match
        FederalContract(
            contract_id="CONTRACT-005",
            agency="DOD",
            vendor_uei="UEI456",  # Different vendor
            vendor_name="Tech Innovations Inc",
            start_date=base_date + timedelta(days=90),
            obligation_amount=300000.0,
            competition_type=CompetitionType.SOLE_SOURCE,
        ),
    ]

    return contracts


class TestTimingWindowFiltering:
    """Test timing window filtering logic."""

    def test_filter_within_window(self, detector, sample_award, sample_contracts):
        """Test filtering keeps contracts within timing window."""
        completion_date = sample_award["completion_date"]

        filtered = detector.filter_by_timing_window(completion_date, sample_contracts)

        # Should exclude CONTRACT-004 (out of window)
        contract_ids = [c.contract_id for c in filtered]
        assert "CONTRACT-001" in contract_ids
        assert "CONTRACT-002" in contract_ids
        assert "CONTRACT-003" in contract_ids
        assert "CONTRACT-004" not in contract_ids

    def test_filter_no_start_date(self, detector):
        """Test filtering handles contracts without start dates."""
        completion_date = date(2024, 1, 1)
        contracts = [
            FederalContract(
                contract_id="NO-DATE",
                agency="DOD",
                vendor_name="Test",
                start_date=None,
            ),
        ]

        filtered = detector.filter_by_timing_window(completion_date, contracts)

        # Should exclude contract without start date
        assert len(filtered) == 0


class TestVendorMatching:
    """Test vendor matching logic."""

    def test_match_by_uei(self, detector, sample_contracts):
        """Test vendor matching via UEI."""
        contract = sample_contracts[0]  # Has UEI123

        match = detector.match_vendor(contract)

        assert match is not None
        assert match.method == "uei"
        assert match.score == 1.0
        assert match.vendor_id == "VENDOR-001"

    def test_match_by_cage(self, detector):
        """Test vendor matching via CAGE code."""
        contract = FederalContract(
            contract_id="TEST",
            agency="DOD",
            vendor_cage="CAGE001",
            vendor_name="Some Name",
            start_date=date(2024, 1, 1),
        )

        match = detector.match_vendor(contract)

        assert match is not None
        assert match.method == "cage"
        assert match.vendor_id == "VENDOR-001"

    def test_match_by_duns(self, detector):
        """Test vendor matching via DUNS number."""
        contract = FederalContract(
            contract_id="TEST",
            agency="DOD",
            vendor_duns="DUNS001",
            vendor_name="Some Name",
            start_date=date(2024, 1, 1),
        )

        match = detector.match_vendor(contract)

        assert match is not None
        assert match.method == "duns"

    def test_match_by_fuzzy_name(self, detector):
        """Test vendor matching via fuzzy name matching."""
        contract = FederalContract(
            contract_id="TEST",
            agency="DOD",
            vendor_name="Acme Corp",  # Close to "Acme Corporation"
            start_date=date(2024, 1, 1),
        )

        match = detector.match_vendor(contract)

        assert match is not None
        assert match.method == "name_fuzzy"
        assert 0.0 < match.score <= 1.0

    def test_no_match(self, detector):
        """Test vendor matching when no match found."""
        contract = FederalContract(
            contract_id="TEST",
            agency="DOD",
            vendor_name="Unknown Company XYZ",
            start_date=date(2024, 1, 1),
        )

        match = detector.match_vendor(contract)

        # Should return None when no match
        assert match is None


class TestDetectionForAward:
    """Test single-award detection logic."""

    def test_detect_transitions(self, detector, sample_award, sample_contracts):
        """Test detection of transitions for a single award."""
        detections = detector.detect_for_award(
            award=sample_award,
            candidate_contracts=sample_contracts,
        )

        # Should detect transitions (excluding out-of-window and different vendor)
        assert len(detections) > 0
        assert all(isinstance(d, Transition) for d in detections)

        # Check detections have required fields
        for detection in detections:
            assert detection.transition_id
            assert detection.award_id == "AWARD-123"
            assert 0.0 <= detection.likelihood_score <= 1.0
            assert detection.confidence in list(ConfidenceLevel)
            assert detection.primary_contract is not None
            assert detection.signals is not None
            assert detection.evidence is not None

    def test_high_confidence_detection(self, detector, sample_award, sample_contracts):
        """Test that high-quality matches get high confidence."""
        detections = detector.detect_for_award(
            award=sample_award,
            candidate_contracts=[sample_contracts[0]],  # Best match
        )

        assert len(detections) == 1
        detection = detections[0]

        # Should have relatively high score (same agency, sole source, good timing)
        assert detection.likelihood_score > 0.3
        assert detection.primary_contract.contract_id == "CONTRACT-001"

    def test_award_without_completion_date(self, detector, sample_contracts):
        """Test handling of award without completion date."""
        incomplete_award = {
            "award_id": "INCOMPLETE",
            "agency": "DOD",
            # Missing completion_date
        }

        detections = detector.detect_for_award(
            award=incomplete_award,
            candidate_contracts=sample_contracts,
        )

        # Should return empty list
        assert len(detections) == 0

    def test_detection_with_patent_data(self, detector, sample_award, sample_contracts):
        """Test detection with patent signal data."""
        patent_data = {
            "patent_count": 3,
            "patents_pre_contract": 2,
            "patent_topic_similarity": 0.85,
        }

        detections = detector.detect_for_award(
            award=sample_award,
            candidate_contracts=[sample_contracts[0]],
            patent_data=patent_data,
        )

        assert len(detections) > 0
        detection = detections[0]

        # Check patent signal included
        assert detection.signals.patent is not None
        assert detection.signals.patent.patent_count == 3

    def test_detection_with_cet_data(self, detector, sample_award, sample_contracts):
        """Test detection with CET alignment data."""
        cet_data = {
            "award_cet": "AI/ML",
            "contract_cet": "AI/ML",
        }

        detections = detector.detect_for_award(
            award=sample_award,
            candidate_contracts=[sample_contracts[0]],
            cet_data=cet_data,
        )

        assert len(detections) > 0
        detection = detections[0]

        # Check CET signal included
        assert detection.signals.cet is not None
        assert detection.signals.cet.award_cet == "AI/ML"


class TestBatchDetection:
    """Test batch processing logic."""

    def test_batch_detection_generator(self, detector, sample_award, sample_contracts):
        """Test batch detection yields results."""
        awards = [sample_award]

        detections = list(
            detector.detect_batch(
                awards=awards,
                contracts=sample_contracts,
                batch_size=10,
                show_progress=False,
            )
        )

        assert len(detections) > 0
        assert all(isinstance(d, Transition) for d in detections)

    def test_batch_multiple_awards(self, detector, sample_contracts):
        """Test batch detection with multiple awards."""
        awards = [
            {
                "award_id": "AWARD-001",
                "agency": "DOD",
                "completion_date": date(2024, 1, 1),
                "vendor_uei": "UEI123",
            },
            {
                "award_id": "AWARD-002",
                "agency": "NASA",
                "completion_date": date(2024, 2, 1),
                "vendor_uei": "UEI456",
            },
        ]

        detections = list(
            detector.detect_batch(
                awards=awards,
                contracts=sample_contracts,
                batch_size=10,
                show_progress=False,
            )
        )

        # Should process both awards
        award_ids = {d.award_id for d in detections}
        assert len(award_ids) >= 1

    def test_batch_with_batching(self, detector, sample_contracts):
        """Test batch detection with small batch size."""
        # Create multiple awards
        awards = [
            {
                "award_id": f"AWARD-{i:03d}",
                "agency": "DOD",
                "completion_date": date(2024, 1, 1),
                "vendor_uei": "UEI123",
            }
            for i in range(10)
        ]

        list(
            detector.detect_batch(
                awards=awards,
                contracts=sample_contracts,
                batch_size=3,  # Small batches
                show_progress=False,
            )
        )

        # Should still process all awards
        assert detector.metrics["total_awards_processed"] == 10


class TestMetrics:
    """Test metrics tracking."""

    def test_metrics_tracking(self, detector, sample_award, sample_contracts):
        """Test that metrics are tracked correctly."""
        detector.reset_metrics()

        _ = detector.detect_for_award(
            award=sample_award,
            candidate_contracts=sample_contracts,
        )

        metrics = detector.get_metrics()

        assert metrics["total_awards_processed"] > 0
        assert metrics["total_contracts_evaluated"] > 0
        assert "detection_rate" in metrics
        assert "vendor_match_rate" in metrics

    def test_confidence_level_tracking(self, detector, sample_award, sample_contracts):
        """Test tracking of confidence level distribution."""
        detector.reset_metrics()

        _ = detector.detect_for_award(
            award=sample_award,
            candidate_contracts=sample_contracts,
        )

        metrics = detector.get_metrics()

        # Should have counts for confidence levels
        total_by_confidence = (
            metrics["high_confidence"]
            + metrics["likely_confidence"]
            + metrics["possible_confidence"]
        )
        assert total_by_confidence == metrics["total_detections"]

    def test_reset_metrics(self, detector, sample_award, sample_contracts):
        """Test metrics reset."""
        # Generate some detections
        _ = detector.detect_for_award(
            award=sample_award,
            candidate_contracts=sample_contracts,
        )

        # Reset
        detector.reset_metrics()

        metrics = detector.get_metrics()
        assert metrics["total_awards_processed"] == 0
        assert metrics["total_detections"] == 0


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_contract_list(self, detector, sample_award):
        """Test detection with no candidate contracts."""
        detections = detector.detect_for_award(
            award=sample_award,
            candidate_contracts=[],
        )

        assert len(detections) == 0

    def test_all_contracts_filtered(self, detector, sample_contracts):
        """Test when all contracts are outside timing window."""
        # Award completion in far future, all contracts in past and outside window
        future_award = {
            "award_id": "FUTURE",
            "agency": "DOD",
            "completion_date": date(2030, 1, 1),  # Far in future
            "vendor_uei": "UEI123",
        }

        detections = detector.detect_for_award(
            award=future_award,
            candidate_contracts=sample_contracts,
        )

        # Should have no detections (all contracts too far in past, before window)
        assert len(detections) == 0

    def test_vendor_match_not_required(self, sample_config, sample_award):
        """Test detection when vendor match not required."""
        # Modify config to not require vendor match
        config = {**sample_config, "vendor_matching": {"require_match": False}}

        detector_no_match_req = TransitionDetector(config=config)

        # Contract with no vendor identifiers
        contract = FederalContract(
            contract_id="NO-VENDOR",
            agency="DOD",
            vendor_name="Unknown Vendor",
            start_date=sample_award["completion_date"] + timedelta(days=100),
            competition_type=CompetitionType.SOLE_SOURCE,
        )

        detections = detector_no_match_req.detect_for_award(
            award=sample_award,
            candidate_contracts=[contract],
        )

        # Should still create detection even without vendor match
        assert len(detections) > 0
