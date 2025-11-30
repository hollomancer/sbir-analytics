"""Tests for TransitionDetector metrics tracking and edge cases.

Split from test_detector.py for better organization.
"""

from datetime import date, timedelta
from unittest.mock import Mock

import pytest

from src.models.transition_models import ConfidenceLevel, FederalContract, TransitionSignals
from src.transition.detection.detector import TransitionDetector
from tests.mocks import TransitionMocks

pytestmark = pytest.mark.fast


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
    ):
        """Test get_metrics calculates rates correctly."""
        sample_contract = FederalContract(
            contract_id="CTR001",
            agency="DOD",
            vendor_name="Acme",
            vendor_uei="ABC123DEF456",
            start_date=date(2023, 9, 1),
            amount=500000,
            description="Services",
            naics_code="541715",
        )

        mock_record = TransitionMocks.vendor_record()
        mock_record.name = "Vendor"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

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

        detector.detect_for_award(award=sample_award, candidate_contracts=[sample_contract])
        detector.detect_for_award(
            award={**sample_award, "award_id": "AWD002"}, candidate_contracts=[]
        )

        metrics = detector.get_metrics()

        assert metrics["total_awards_processed"] == 2
        assert metrics["total_detections"] == 1
        assert metrics["detection_rate"] == 0.5
        assert metrics["vendor_matches"] == 1
        assert metrics["high_confidence"] == 1

    def test_reset_metrics(
        self,
        default_config,
        mock_vendor_resolver,
        mock_scorer,
        mock_evidence_generator,
        sample_award,
    ):
        """Test reset_metrics clears all counters."""
        sample_contract = FederalContract(
            contract_id="CTR001",
            agency="DOD",
            vendor_name="Acme",
            vendor_uei="ABC123DEF456",
            start_date=date(2023, 9, 1),
            amount=500000,
            description="Services",
            naics_code="541715",
        )

        mock_record = TransitionMocks.vendor_record()
        mock_record.name = "Vendor"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_uei.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(
            config=default_config,
            vendor_resolver=mock_vendor_resolver,
            scorer=mock_scorer,
            evidence_generator=mock_evidence_generator,
        )

        detector.detect_for_award(award=sample_award, candidate_contracts=[sample_contract])

        assert detector.metrics["total_awards_processed"] == 1
        assert detector.metrics["total_detections"] == 1

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

        mock_record = TransitionMocks.vendor_record()
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

    def test_contract_with_partial_vendor_ids(self, default_config, mock_vendor_resolver):
        """Test vendor matching handles contracts with partial vendor identifiers."""
        contract = FederalContract(
            contract_id="CTR001",
            agency="DOD",
            vendor_name="Acme Corp",
            vendor_uei=None,
            vendor_cage="1A2B3",
            vendor_duns=None,
            start_date=date(2023, 9, 1),
            amount=100000,
            description="Services",
            naics_code="541715",
        )

        mock_record = TransitionMocks.vendor_record()
        mock_record.name = "Acme"
        mock_record.metadata = {"vendor_id": "V001"}
        mock_vendor_resolver.resolve_by_cage.return_value = Mock(record=mock_record, score=1.0)

        detector = TransitionDetector(config=default_config, vendor_resolver=mock_vendor_resolver)

        vendor_match = detector.match_vendor(contract)

        assert vendor_match is not None
        assert vendor_match.method == "cage"
