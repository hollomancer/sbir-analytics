"""
Tests for src/transition/detection/detector.py

Tests the TransitionDetector orchestration class that coordinates
vendor matching, scoring, evidence generation, and metrics tracking
for the complete transition detection pipeline.
"""

from datetime import date, timedelta
from unittest.mock import Mock
from uuid import UUID

import pytest

from src.models.transition_models import (
    ConfidenceLevel,
    FederalContract,
    Transition,
    TransitionSignals,
)
from src.transition.detection.detector import TransitionDetector


pytestmark = pytest.mark.fast
# Note: Fixtures are now imported from tests/unit/transition/conftest.py
# (default_transition_config, mock_vendor_resolver, mock_scorer,
#  mock_evidence_generator, sample_award)


@pytest.fixture
def sample_contract():
    """Sample federal contract for testing."""
    return FederalContract(
        contract_id="CTR001",
        agency="DOD",
        vendor_name="Acme Corporation",
        vendor_uei="ABC123DEF456",  # pragma: allowlist secret
        vendor_cage=None,
        vendor_duns=None,
        start_date=date(2023, 9, 1),
        amount=500000,
        description="R&D Services",
        naics_code="541715",
    )


class TestTransitionDetectorInitialization:
    """Tests for TransitionDetector initialization."""

    def test_initialization_with_defaults(self, default_config):
        """Test detector initializes with default dependencies."""
        detector = TransitionDetector(config=default_config)

        assert detector.config == default_config
        assert detector.min_days_after == 0
        assert detector.max_days_after == 730
        assert detector.require_vendor_match is True
        assert detector.vendor_resolver is not None
        assert detector.scorer is not None
        assert detector.evidence_generator is not None

        # Check metrics initialized
        assert detector.metrics["total_awards_processed"] == 0
        assert detector.metrics["total_detections"] == 0

    def test_initialization_with_custom_dependencies(
        self, default_config, mock_vendor_resolver, mock_scorer, mock_evidence_generator
    ):
        """Test detector initializes with custom dependencies."""
        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        assert detector.vendor_resolver is mock_vendor_resolver
        assert detector.scorer is mock_scorer
        assert detector.evidence_generator is mock_evidence_generator

    def test_initialization_extracts_timing_config(self):
        """Test timing window configuration is extracted correctly."""
        config = {
            "timing_window": {
                "min_days_after_completion": 30,
                "max_days_after_completion": 365,
            },
            "vendor_matching": {"require_match": False},
        }

        detector = TransitionDetector(config=config)

        assert detector.min_days_after == 30
        assert detector.max_days_after == 365
        assert detector.require_vendor_match is False


class TestFilterByTimingWindow:
    """Tests for timing window filtering."""

    def test_filter_within_window(self, default_config):
        """Test contracts within timing window are included."""
        detector = TransitionDetector(config=default_config)
        completion_date = date(2023, 6, 1)

        # Contract 90 days after completion (within 0-730 day window)
        contract = FederalContract(
            contract_id="CTR001",
            agency="DOD",
            vendor_name="Acme",
            start_date=completion_date + timedelta(days=90),
            amount=100000,
            description="Services",
            naics_code="541715",
        )

        filtered = detector.filter_by_timing_window(completion_date, [contract])

        assert len(filtered) == 1
        assert filtered[0].contract_id == "CTR001"

    def test_filter_outside_window_too_early(self, default_config):
        """Test contracts before min_days_after are excluded."""
        config = {**default_config}
        config["timing_window"]["min_days_after_completion"] = 30

        detector = TransitionDetector(config=config)
        completion_date = date(2023, 6, 1)

        # Contract 15 days after (before 30-day minimum)
        contract = FederalContract(
            contract_id="CTR001",
            agency="DOD",
            vendor_name="Acme",
            start_date=completion_date + timedelta(days=15),
            amount=100000,
            description="Services",
            naics_code="541715",
        )

        filtered = detector.filter_by_timing_window(completion_date, [contract])

        assert len(filtered) == 0

    def test_filter_outside_window_too_late(self, default_config):
        """Test contracts after max_days_after are excluded."""
        detector = TransitionDetector(config=default_config)
        completion_date = date(2023, 6, 1)

        # Contract 800 days after (beyond 730-day maximum)
        contract = FederalContract(
            contract_id="CTR001",
            agency="DOD",
            vendor_name="Acme",
            start_date=completion_date + timedelta(days=800),
            amount=100000,
            description="Services",
            naics_code="541715",
        )

        filtered = detector.filter_by_timing_window(completion_date, [contract])

        assert len(filtered) == 0

    def test_filter_exact_boundaries(self, default_config):
        """Test contracts exactly at window boundaries are included."""
        config = {**default_config}
        config["timing_window"]["min_days_after_completion"] = 30
        config["timing_window"]["max_days_after_completion"] = 365

        detector = TransitionDetector(config=config)
        completion_date = date(2023, 6, 1)

        # Contracts exactly at min and max boundaries
        contracts = [
            FederalContract(
                contract_id="CTR_MIN",
                agency="DOD",
                vendor_name="Acme",
                start_date=completion_date + timedelta(days=30),
                amount=100000,
                description="Services",
                naics_code="541715",
            ),
            FederalContract(
                contract_id="CTR_MAX",
                agency="DOD",
                vendor_name="Acme",
                start_date=completion_date + timedelta(days=365),
                amount=100000,
                description="Services",
                naics_code="541715",
            ),
        ]

        filtered = detector.filter_by_timing_window(completion_date, contracts)

        assert len(filtered) == 2
        assert {c.contract_id for c in filtered} == {"CTR_MIN", "CTR_MAX"}

    def test_filter_skips_contracts_without_start_date(self, default_config):
        """Test contracts without start_date are excluded."""
        detector = TransitionDetector(config=default_config)
        completion_date = date(2023, 6, 1)

        contract = FederalContract(
            contract_id="CTR001",
            agency="DOD",
            vendor_name="Acme",
            start_date=None,  # Missing start date
            amount=100000,
            description="Services",
            naics_code="541715",
        )

        filtered = detector.filter_by_timing_window(completion_date, [contract])

        assert len(filtered) == 0


class TestMatchVendor:
    """Tests for vendor matching."""

    def test_match_by_uei_success(self, default_config, mock_vendor_resolver, sample_contract):
        """Test successful vendor match using UEI."""
        # Mock successful UEI match
        mock_record = Mock()
        mock_record.name = "Acme Corporation"
        mock_record.metadata = {"vendor_id": "VENDOR001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(config=default_config, vendor_resolver=mock_vendor_resolver)

        vendor_match = detector.match_vendor(sample_contract)

        assert vendor_match is not None
        assert vendor_match.vendor_id == "VENDOR001"
        assert vendor_match.method == "uei"
        assert vendor_match.score == 1.0
        assert vendor_match.matched_name == "Acme Corporation"
        assert vendor_match.metadata["uei"] == "ABC123DEF456"

        # Should try UEI first
        mock_vendor_resolver.resolve_by_uei.assert_called_once_with("ABC123DEF456")
        # Should not try other methods
        mock_vendor_resolver.resolve_by_cage.assert_not_called()

    def test_match_by_cage_when_uei_fails(self, default_config, mock_vendor_resolver):
        """Test vendor match falls back to CAGE when UEI fails."""
        contract = FederalContract(
            contract_id="CTR001",
            agency="DOD",
            vendor_name="Acme",
            vendor_uei="ABC123",
            vendor_cage="1A2B3",
            start_date=date(2023, 9, 1),
            amount=100000,
            description="Services",
            naics_code="541715",
        )

        # UEI fails, CAGE succeeds
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=None, score=0.0)
        mock_record = Mock()
        mock_record.name = "Acme Corp"
        mock_record.metadata = {"vendor_id": "VENDOR002"}
        mock_vendor_resolver.resolve_by_cage.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(config=default_config, vendor_resolver=mock_vendor_resolver)

        vendor_match = detector.match_vendor(contract)

        assert vendor_match is not None
        assert vendor_match.method == "cage"
        assert vendor_match.metadata["cage"] == "1A2B3"

        mock_vendor_resolver.resolve_by_uei.assert_called_once()
        mock_vendor_resolver.resolve_by_cage.assert_called_once_with("1A2B3")

    def test_match_by_duns_when_uei_and_cage_fail(self, default_config, mock_vendor_resolver):
        """Test vendor match falls back to DUNS when UEI and CAGE fail."""
        contract = FederalContract(
            contract_id="CTR001",
            agency="DOD",
            vendor_name="Acme",
            vendor_uei="ABC123",
            vendor_cage="1A2B3",
            vendor_duns="123456789",
            start_date=date(2023, 9, 1),
            amount=100000,
            description="Services",
            naics_code="541715",
        )

        # UEI and CAGE fail, DUNS succeeds
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=None, score=0.0)
        mock_vendor_resolver.resolve_by_cage.return_value = Mock(record=None, score=0.0)
        mock_record = Mock()
        mock_record.name = "Acme Inc"
        mock_record.metadata = {"vendor_id": "VENDOR003"}
        mock_vendor_resolver.resolve_by_duns.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(config=default_config, vendor_resolver=mock_vendor_resolver)

        vendor_match = detector.match_vendor(contract)

        assert vendor_match is not None
        assert vendor_match.method == "duns"
        assert vendor_match.metadata["duns"] == "123456789"

    def test_match_by_fuzzy_name_when_all_ids_fail(self, default_config, mock_vendor_resolver):
        """Test vendor match falls back to fuzzy name matching."""
        contract = FederalContract(
            contract_id="CTR001",
            agency="DOD",
            vendor_name="Acme Corporation LLC",
            vendor_uei=None,
            vendor_cage=None,
            vendor_duns=None,
            start_date=date(2023, 9, 1),
            amount=100000,
            description="Services",
            naics_code="541715",
        )

        # All ID methods fail, name succeeds with high score
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=None, score=0.0)
        mock_vendor_resolver.resolve_by_cage.return_value = Mock(record=None, score=0.0)
        mock_vendor_resolver.resolve_by_duns.return_value = Mock(record=None, score=0.0)
        mock_record = Mock()
        mock_record.name = "Acme Corporation"
        mock_record.metadata = {"vendor_id": "VENDOR004"}
        mock_vendor_resolver.resolve_by_name.return_value = Mock(record=mock_record, score=0.92)

        detector = TransitionDetector(config=default_config, vendor_resolver=mock_vendor_resolver)

        vendor_match = detector.match_vendor(contract)

        assert vendor_match is not None
        assert vendor_match.method == "name_fuzzy"
        assert vendor_match.score == 0.92
        assert vendor_match.metadata["input_name"] == "Acme Corporation LLC"
        assert vendor_match.metadata["fuzzy_score"] == 0.92

    def test_match_fuzzy_name_below_threshold_fails(self, default_config, mock_vendor_resolver):
        """Test fuzzy name match below threshold is rejected."""
        contract = FederalContract(
            contract_id="CTR001",
            agency="DOD",
            vendor_name="Different Company",
            vendor_uei=None,
            vendor_cage=None,
            vendor_duns=None,
            start_date=date(2023, 9, 1),
            amount=100000,
            description="Services",
            naics_code="541715",
        )

        # Fuzzy match score below 0.85 threshold
        mock_record = Mock()
        mock_record.name = "Acme Corp"
        mock_record.metadata = {"vendor_id": "VENDOR005"}
        mock_vendor_resolver.resolve_by_name.return_value = Mock(record=mock_record, score=0.60)

        detector = TransitionDetector(config=default_config, vendor_resolver=mock_vendor_resolver)

        vendor_match = detector.match_vendor(contract)

        assert vendor_match is None
        assert detector.metrics["vendor_match_failures"] == 1

    def test_match_all_methods_fail(self, default_config, mock_vendor_resolver):
        """Test vendor match returns None when all methods fail."""
        contract = FederalContract(
            contract_id="CTR001",
            agency="DOD",
            vendor_name="Unknown Vendor",
            vendor_uei="UNKNOWN",
            vendor_cage="UNKNOWN",
            vendor_duns="999999999",
            start_date=date(2023, 9, 1),
            amount=100000,
            description="Services",
            naics_code="541715",
        )

        # All methods fail
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=None, score=0.0)
        mock_vendor_resolver.resolve_by_cage.return_value = Mock(record=None, score=0.0)
        mock_vendor_resolver.resolve_by_duns.return_value = Mock(record=None, score=0.0)
        mock_vendor_resolver.resolve_by_name.return_value = Mock(record=None, score=0.0)

        detector = TransitionDetector(config=default_config, vendor_resolver=mock_vendor_resolver)

        vendor_match = detector.match_vendor(contract)

        assert vendor_match is None
        assert detector.metrics["vendor_match_failures"] == 1


class TestDetectForAward:
    """Tests for single award transition detection."""

    def test_detect_for_award_success(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
        sample_award,
        sample_contract,
    ):
        """Test successful transition detection for an award."""
        # Mock successful vendor match
        mock_record = Mock()
        mock_record.name = "Acme Corp"
        mock_record.metadata = {"vendor_id": "VENDOR001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detections = detector.detect_for_award(
            award=sample_award, candidate_contracts=[sample_contract]
        )

        assert len(detections) == 1
        transition = detections[0]

        assert transition.award_id == "AWD001"
        assert transition.likelihood_score == 0.75
        assert transition.confidence == ConfidenceLevel.LIKELY
        assert transition.primary_contract.contract_id == "CTR001"
        assert isinstance(UUID(transition.transition_id), UUID)

        # Check metrics
        assert detector.metrics["total_awards_processed"] == 1
        assert detector.metrics["total_contracts_evaluated"] == 1
        assert detector.metrics["total_detections"] == 1
        assert detector.metrics["likely_confidence"] == 1

    def test_detect_for_award_high_confidence(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
        sample_award,
        sample_contract,
    ):
        """Test high confidence detection increments correct metric."""
        # Mock high confidence score
        signals = TransitionSignals(
            agency_signal=Mock(agency_score=0.25),
            timing_signal=Mock(timing_score=0.20),
            competition_signal=Mock(competition_score=0.10),
            patent_signal=Mock(patent_score=0.15),
            cet_signal=Mock(cet_score=0.20),
        )
        mock_scorer.score_and_classify.return_value = (signals, 0.90, ConfidenceLevel.HIGH)

        mock_record = Mock()
        mock_record.name = "Acme"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detections = detector.detect_for_award(
            award=sample_award, candidate_contracts=[sample_contract]
        )

        assert len(detections) == 1
        assert detections[0].confidence == ConfidenceLevel.HIGH
        assert detector.metrics["high_confidence"] == 1

    def test_detect_for_award_skips_without_vendor_match(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
        sample_award,
        sample_contract,
    ):
        """Test detection skips contract when vendor match required but not found."""
        # No vendor match
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=None, score=0.0)
        mock_vendor_resolver.resolve_by_cage.return_value = Mock(record=None, score=0.0)
        mock_vendor_resolver.resolve_by_duns.return_value = Mock(record=None, score=0.0)
        mock_vendor_resolver.resolve_by_name.return_value = Mock(record=None, score=0.0)

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detections = detector.detect_for_award(
            award=sample_award, candidate_contracts=[sample_contract]
        )

        assert len(detections) == 0
        assert detector.metrics["total_contracts_evaluated"] == 1
        assert detector.metrics["total_detections"] == 0

    def test_detect_for_award_allows_without_vendor_match_when_not_required(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
        sample_award,
        sample_contract,
    ):
        """Test detection proceeds without vendor match when not required."""
        config = {**default_config}
        config["vendor_matching"]["require_match"] = False

        # No vendor match
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=None, score=0.0)

        detector = TransitionDetector(
            config=config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detections = detector.detect_for_award(
            award=sample_award, candidate_contracts=[sample_contract]
        )

        assert len(detections) == 1
        assert detector.metrics["total_detections"] == 1

    def test_detect_for_award_missing_completion_date(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
        sample_contract,
    ):
        """Test detection skips award missing completion_date."""
        award = {
            "award_id": "AWD001",
            "vendor_uei": "ABC123",
            "completion_date": None,  # Missing
        }

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detections = detector.detect_for_award(award=award, candidate_contracts=[sample_contract])

        assert len(detections) == 0
        assert detector.metrics["total_awards_processed"] == 0

    def test_detect_for_award_filters_by_timing_window(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
        sample_award,
    ):
        """Test detection filters contracts outside timing window."""
        # Contract 900 days after completion (beyond 730-day window)
        contract_late = FederalContract(
            contract_id="CTR_LATE",
            agency="DOD",
            vendor_name="Acme",
            vendor_uei="ABC123DEF456",
            start_date=sample_award["completion_date"] + timedelta(days=900),
            amount=100000,
            description="Services",
            naics_code="541715",
        )

        mock_record = Mock()
        mock_record.name = "Acme"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detections = detector.detect_for_award(
            award=sample_award, candidate_contracts=[contract_late]
        )

        assert len(detections) == 0
        assert detector.metrics["total_contracts_evaluated"] == 0

    def test_detect_for_award_with_patent_and_cet_data(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
        sample_award,
        sample_contract,
    ):
        """Test detection passes patent and CET data to scorer and evidence generator."""
        patent_data = {"patent_count": 5, "topics": ["AI", "ML"]}
        cet_data = {"cet_areas": ["AI"]}

        mock_record = Mock()
        mock_record.name = "Acme"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detections = detector.detect_for_award(
            award=sample_award,
            candidate_contracts=[sample_contract],
            patent_data=patent_data,
            cet_data=cet_data,
        )

        assert len(detections) == 1

        # Verify scorer was called with patent/cet data
        mock_scorer.score_and_classify.assert_called_once()
        call_args = mock_scorer.score_and_classify.call_args
        assert call_args.kwargs["patent_data"] == patent_data
        assert call_args.kwargs["cet_data"] == cet_data

        # Verify evidence generator was called with patent/cet data
        mock_evidence_generator.generate_bundle.assert_called_once()
        call_args = mock_evidence_generator.generate_bundle.call_args
        assert call_args.kwargs["patent_data"] == patent_data
        assert call_args.kwargs["cet_data"] == cet_data


class TestDetectBatch:
    """Tests for batch detection processing."""

    def test_detect_batch_success(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
    ):
        """Test successful batch detection across multiple awards."""
        awards = [
            {
                "award_id": "AWD001",
                "vendor_uei": "UEI001",
                "completion_date": date(2023, 6, 1),
                "agency": "DOD",
            },
            {
                "award_id": "AWD002",
                "vendor_uei": "UEI002",
                "completion_date": date(2023, 7, 1),
                "agency": "NASA",
            },
        ]

        contracts = [
            FederalContract(
                contract_id="CTR001",
                agency="DOD",
                vendor_name="Vendor 1",
                vendor_uei="UEI001",
                start_date=date(2023, 9, 1),
                amount=100000,
                description="Services",
                naics_code="541715",
            ),
            FederalContract(
                contract_id="CTR002",
                agency="NASA",
                vendor_name="Vendor 2",
                vendor_uei="UEI002",
                start_date=date(2023, 10, 1),
                amount=200000,
                description="Research",
                naics_code="541715",
            ),
        ]

        mock_record = Mock()
        mock_record.name = "Vendor"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detections = list(detector.detect_batch(awards, contracts, show_progress=False))

        assert len(detections) == 2
        assert {d.award_id for d in detections} == {"AWD001", "AWD002"}
        assert detector.metrics["total_awards_processed"] == 2
        assert detector.metrics["total_detections"] == 2

    def test_detect_batch_with_batch_size(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
    ):
        """Test batch processing respects batch_size parameter."""
        awards = [
            {
                "award_id": f"AWD{i:03d}",
                "vendor_uei": f"UEI{i:03d}",
                "completion_date": date(2023, 6, 1),
            }
            for i in range(10)
        ]

        contracts = [
            FederalContract(
                contract_id=f"CTR{i:03d}",
                agency="DOD",
                vendor_name=f"Vendor {i}",
                vendor_uei=f"UEI{i:03d}",
                start_date=date(2023, 9, 1),
                amount=100000,
                description="Services",
                naics_code="541715",
            )
            for i in range(10)
        ]

        mock_record = Mock()
        mock_record.name = "Vendor"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detections = list(
            detector.detect_batch(awards, contracts, batch_size=3, show_progress=False)
        )

        assert len(detections) == 10
        assert detector.metrics["total_awards_processed"] == 10

    def test_detect_batch_indexes_contracts_by_vendor(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
    ):
        """Test batch detection indexes contracts by vendor for efficiency."""
        awards = [
            {"award_id": "AWD001", "vendor_uei": "UEI001", "completion_date": date(2023, 6, 1)},
            {"award_id": "AWD002", "vendor_uei": "UEI002", "completion_date": date(2023, 7, 1)},
        ]

        # Multiple contracts for same vendors
        contracts = [
            FederalContract(
                contract_id="CTR001",
                agency="DOD",
                vendor_name="V1",
                vendor_uei="UEI001",
                start_date=date(2023, 9, 1),
                amount=100000,
                description="Services",
                naics_code="541715",
            ),
            FederalContract(
                contract_id="CTR002",
                agency="DOD",
                vendor_name="V1",
                vendor_uei="UEI001",  # Same vendor as CTR001
                start_date=date(2023, 10, 1),
                amount=150000,
                description="Services",
                naics_code="541715",
            ),
        ]

        mock_record = Mock()
        mock_record.name = "Vendor"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detections = list(detector.detect_batch(awards, contracts, show_progress=False))

        # Award 1 should match both contracts with same vendor
        award1_detections = [d for d in detections if d.award_id == "AWD001"]
        assert len(award1_detections) == 2

    def test_detect_batch_yields_results_incrementally(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
    ):
        """Test batch detection yields results as iterator."""
        awards = [
            {
                "award_id": f"AWD{i:03d}",
                "vendor_uei": f"UEI{i:03d}",
                "completion_date": date(2023, 6, 1),
            }
            for i in range(3)
        ]

        contracts = [
            FederalContract(
                contract_id=f"CTR{i:03d}",
                agency="DOD",
                vendor_name=f"V{i}",
                vendor_uei=f"UEI{i:03d}",
                start_date=date(2023, 9, 1),
                amount=100000,
                description="Services",
                naics_code="541715",
            )
            for i in range(3)
        ]

        mock_record = Mock()
        mock_record.name = "Vendor"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detection_iter = detector.detect_batch(awards, contracts, show_progress=False)

        # Should be able to iterate results one at a time
        first = next(detection_iter)
        assert isinstance(first, Transition)

        second = next(detection_iter)
        assert isinstance(second, Transition)

        # Consume rest
        rest = list(detection_iter)
        assert len(rest) == 1


class TestMetrics:
    """Tests for metrics tracking and reporting."""

    def test_get_metrics_initial_state(self, default_config):
        """Test get_metrics returns correct initial state."""
        detector = TransitionDetector(config=default_config)

        metrics = detector.get_metrics()

        assert metrics["total_awards_processed"] == 0
        assert metrics["total_detections"] == 0
        assert metrics["detection_rate"] == 0.0
        assert metrics["vendor_match_rate"] == 0.0
        assert metrics["high_confidence_rate"] == 0.0

    def test_get_metrics_calculates_rates(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
        sample_award,
        sample_contract,
    ):
        """Test get_metrics calculates rates correctly."""
        mock_record = Mock()
        mock_record.name = "Vendor"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

        # High confidence detection
        signals = TransitionSignals(
            agency_signal=Mock(agency_score=0.25),
            timing_signal=Mock(timing_score=0.20),
            competition_signal=Mock(competition_score=0.10),
            patent_signal=Mock(patent_score=0.15),
            cet_signal=Mock(cet_score=0.20),
        )
        mock_scorer.score_and_classify.return_value = (signals, 0.90, ConfidenceLevel.HIGH)

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        # Process 2 awards, 1 with detection
        detector.detect_for_award(award=sample_award, candidate_contracts=[sample_contract])
        detector.detect_for_award(
            award={**sample_award, "award_id": "AWD002"}, candidate_contracts=[]
        )

        metrics = detector.get_metrics()

        assert metrics["total_awards_processed"] == 2
        assert metrics["total_detections"] == 1
        assert metrics["detection_rate"] == 0.5  # 1/2
        assert metrics["vendor_matches"] == 1
        assert metrics["vendor_match_rate"] == 1.0  # 1/(1+0)
        assert metrics["high_confidence"] == 1
        assert metrics["high_confidence_rate"] == 1.0  # 1/1

    def test_reset_metrics(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
        sample_award,
        sample_contract,
    ):
        """Test reset_metrics clears all counters."""
        mock_record = Mock()
        mock_record.name = "Vendor"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        # Process some detections
        detector.detect_for_award(award=sample_award, candidate_contracts=[sample_contract])

        assert detector.metrics["total_awards_processed"] == 1
        assert detector.metrics["total_detections"] == 1

        # Reset
        detector.reset_metrics()

        assert detector.metrics["total_awards_processed"] == 0
        assert detector.metrics["total_detections"] == 0
        assert detector.metrics["vendor_matches"] == 0


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_candidate_contracts(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
        sample_award,
    ):
        """Test detection handles empty candidate contracts gracefully."""
        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detections = detector.detect_for_award(award=sample_award, candidate_contracts=[])

        assert len(detections) == 0
        assert detector.metrics["total_awards_processed"] == 1
        assert detector.metrics["total_detections"] == 0

    def test_multiple_contracts_for_same_award(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
        sample_award,
    ):
        """Test detection handles multiple contracts for same award."""
        contracts = [
            FederalContract(
                contract_id=f"CTR{i:03d}",
                agency="DOD",
                vendor_name="Acme",
                vendor_uei="ABC123DEF456",
                start_date=date(2023, 9, 1) + timedelta(days=i * 30),
                amount=100000,
                description="Services",
                naics_code="541715",
            )
            for i in range(5)
        ]

        mock_record = Mock()
        mock_record.name = "Acme"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detections = detector.detect_for_award(award=sample_award, candidate_contracts=contracts)

        assert len(detections) == 5
        assert detector.metrics["total_contracts_evaluated"] == 5
        assert detector.metrics["total_detections"] == 5

    def test_contract_with_partial_vendor_ids(
        self, default_config, mock_vendor_resolver, sample_award
    ):
        """Test vendor matching handles contracts with partial vendor identifiers."""
        contract = FederalContract(
            contract_id="CTR001",
            agency="DOD",
            vendor_name="Acme Corp",
            vendor_uei=None,  # Missing
            vendor_cage="1A2B3",
            vendor_duns=None,  # Missing
            start_date=date(2023, 9, 1),
            amount=100000,
            description="Services",
            naics_code="541715",
        )

        # CAGE succeeds
        mock_record = Mock()
        mock_record.name = "Acme"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_cage.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(config=default_config, vendor_resolver=mock_vendor_resolver)

        vendor_match = detector.match_vendor(contract)

        assert vendor_match is not None
        assert vendor_match.method == "cage"
