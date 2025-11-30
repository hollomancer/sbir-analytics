"""Tests for TransitionDetector initialization and timing window filtering.

Split from test_detector.py for better organization.
"""

from datetime import date, timedelta

import pytest

from src.models.transition_models import FederalContract
from src.transition.detection.detector import TransitionDetector

pytestmark = pytest.mark.fast


@pytest.fixture
def sample_contract():
    """Sample federal contract for testing."""
    return FederalContract(
        contract_id="CTR001",
        agency="DOD",
        vendor_name="Acme Corporation",
        vendor_uei="ABC123DEF456",
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
            start_date=None,
            amount=100000,
            description="Services",
            naics_code="541715",
        )

        filtered = detector.filter_by_timing_window(completion_date, [contract])

        assert len(filtered) == 0
