"""Shared fixtures for transition detection tests."""

from datetime import date, datetime, timedelta
from unittest.mock import Mock

import pytest

from src.models.transition_models import (
    ConfidenceLevel,
    EvidenceBundle,
    TransitionSignals,
)
from tests.utils.fixtures import (
    create_sample_award_dict,
    create_sample_transition_detector_config,
)


@pytest.fixture
def default_transition_config():
    """Default transition detector configuration for tests."""
    return create_sample_transition_detector_config()


@pytest.fixture
def mock_vendor_resolver():
    """Mock VendorResolver for testing."""
    resolver = Mock()
    resolver.resolve_by_uei = Mock(return_value=Mock(record=None, score=0.0))
    resolver.resolve_by_cage = Mock(return_value=Mock(record=None, score=0.0))
    resolver.resolve_by_duns = Mock(return_value=Mock(record=None, score=0.0))
    resolver.resolve_by_name = Mock(return_value=Mock(record=None, score=0.0))
    return resolver


@pytest.fixture
def mock_scorer():
    """Mock TransitionScorer for testing."""
    scorer = Mock()
    signals = TransitionSignals(
        agency_signal=Mock(agency_score=0.0625),
        timing_signal=Mock(timing_score=0.20),
        competition_signal=Mock(competition_score=0.02),
        patent_signal=None,
        cet_signal=None,
    )
    scorer.score_and_classify = Mock(return_value=(signals, 0.75, ConfidenceLevel.LIKELY))
    return scorer


@pytest.fixture
def mock_evidence_generator():
    """Mock EvidenceGenerator for testing."""
    generator = Mock()
    bundle = EvidenceBundle(evidence_items=[], generated_at=datetime.utcnow())
    generator.generate_bundle = Mock(return_value=bundle)
    return generator


@pytest.fixture
def sample_award():
    """Sample SBIR award for testing."""
    return create_sample_award_dict(
        award_id="AWD001",
        company_name="Acme Corp",
        agency="DOD",
        completion_date=date(2023, 6, 1),
        award_amount=1000000,
    )


@pytest.fixture
def sample_contract():
    """Sample federal contract for testing."""
    return {
        "contract_id": "CONTRACT-001",
        "piid": "PIID-001",
        "recipient_name": "Acme Corp",
        "recipient_uei": "ABC123DEF456",  # pragma: allowlist secret
        "awarding_agency_name": "DOD",
        "federal_action_obligation": 500000.0,
        "action_date": date(2023, 8, 1),  # 2 months after award completion
        "period_of_performance_start_date": date(2023, 8, 1),
        "period_of_performance_current_end_date": date(2024, 8, 1),
    }


@pytest.fixture
def sample_contracts_df(sample_contract):
    """Sample contracts DataFrame for testing."""
    import pandas as pd

    return pd.DataFrame([sample_contract])


@pytest.fixture
def recent_award():
    """Award that completed recently (within detection window)."""
    return create_sample_award_dict(
        award_id="AWD-RECENT",
        company_name="Recent Corp",
        agency="NSF",
        completion_date=date.today() - timedelta(days=90),  # 3 months ago
    )


@pytest.fixture
def old_award():
    """Award that completed outside detection window."""
    return create_sample_award_dict(
        award_id="AWD-OLD",
        company_name="Old Corp",
        agency="NIH",
        completion_date=date.today() - timedelta(days=800),  # > 2 years ago
    )

