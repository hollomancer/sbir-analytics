# Shared fixtures for the test suite

import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, Mock

import pandas as pd
import pytest

# Neo4j fixtures
from src.loaders.neo4j.client import LoadMetrics, Neo4jClient, Neo4jConfig
from tests.utils.config_mocks import create_mock_neo4j_config
from tests.utils.fixtures import (
    create_sample_award_dict,
    create_sample_enriched_awards_df,
    create_sample_sbir_data,
    create_sample_transition_detector_config,
)


# ============================================================================
# Neo4j Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def neo4j_config():
    """Create Neo4j configuration for testing."""
    return Neo4jConfig(
        **create_mock_neo4j_config(
            uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            username=os.getenv("NEO4J_USERNAME", "neo4j"),
            password=os.getenv("NEO4J_PASSWORD", "password"),
            database=os.getenv("NEO4J_DATABASE", "neo4j"),
        )
    )


@pytest.fixture(scope="module")
def neo4j_client(neo4j_config):
    """Create Neo4j client for testing."""
    client = Neo4jClient(neo4j_config)
    yield client
    client.close()


@pytest.fixture
def cleanup_test_data(neo4j_client):
    """Clean up test data before and after each test.

    Note: This is NOT autouse by default. Tests that need cleanup
    should explicitly request this fixture, or use the integration
    conftest which provides an autouse version.
    """
    # Clean before test
    try:
        with neo4j_client.session() as session:
            session.run("MATCH (n:TestCompany) DETACH DELETE n")
            session.run("MATCH (n:TestAward) DETACH DELETE n")
    except Exception:
        pass  # Skip cleanup if Neo4j not available

    yield

    # Clean after test
    try:
        with neo4j_client.session() as session:
            session.run("MATCH (n:TestCompany) DETACH DELETE n")
            session.run("MATCH (n:TestAward) DETACH DELETE n")
    except Exception:
        pass  # Skip cleanup if Neo4j not available


class Neo4jTestHelper:
    """Helper class for Neo4j integration tests."""

    def __init__(self, client: Neo4jClient):
        self.client = client

    def create_company(self, uei: str, name: str = "Test Company", **kwargs):
        """Create a TestCompany node."""
        props = {"uei": uei, "name": name, **kwargs}
        query = "CREATE (c:TestCompany $props)"
        with self.client.session() as session:
            session.run(query, props=props)

    def create_award(self, award_id: str, **kwargs):
        """Create a TestAward node."""
        props = {"award_id": award_id, **kwargs}
        query = "CREATE (a:TestAward $props)"
        with self.client.session() as session:
            session.run(query, props=props)

    def create_relationship(
        self,
        source_label: str,
        source_key: str,
        source_val: str,
        target_label: str,
        target_key: str,
        target_val: str,
        rel_type: str,
        props: dict | None = None,
    ):
        """Create a relationship between two nodes."""
        props = props or {}
        query = f"""
        MATCH (s:{source_label} {{{source_key}: $source_val}})
        MATCH (t:{target_label} {{{target_key}: $target_val}})
        CREATE (s)-[r:{rel_type} $props]->(t)
        RETURN r
        """
        with self.client.session() as session:
            session.run(
                query,
                source_val=source_val,
                target_val=target_val,
                props=props,
            )


@pytest.fixture
def neo4j_helper(neo4j_client):
    """Fixture providing Neo4jTestHelper."""
    return Neo4jTestHelper(neo4j_client)


@pytest.fixture
def mock_driver():
    """Mock Neo4j driver."""
    driver = MagicMock()
    driver.close = Mock()
    return driver


@pytest.fixture
def mock_session():
    """Mock Neo4j session."""
    session = MagicMock()
    session.close = Mock()
    return session


@pytest.fixture
def mock_transaction():
    """Mock Neo4j transaction."""
    tx = MagicMock()
    tx.run = Mock()
    tx.commit = Mock()
    return tx


@pytest.fixture
def empty_load_metrics():
    """Empty LoadMetrics instance."""
    return LoadMetrics()


# ============================================================================
# Enrichment Fixtures
# ============================================================================


@pytest.fixture
def mock_enrichment_config():
    """Mock enrichment configuration for testing."""
    config = create_mock_neo4j_config()  # placeholder, adjust as needed
    return config


@pytest.fixture
def sample_sbir_df():
    """Sample SBIR awards DataFrame for testing."""
    return create_sample_sbir_data(num_records=5)


@pytest.fixture
def sample_recipient_df():
    """Sample recipient DataFrame for testing."""
    return pd.DataFrame(
        {
            "recipient_name": ["Acme Corp", "TechStart Inc", "DataPro LLC", "BioMed Co"],
            "recipient_uei": ["UEI001", "UEI002", "UEI003", "UEI004"],
            "recipient_duns": ["123456789", "987654321", "111222333", "444555666"],
            "total_amount": [5000000, 3000000, 2000000, 1000000],
        }
    )


# ============================================================================
# Fiscal Fixtures
# ============================================================================


@pytest.fixture
def sample_fiscal_awards_df():
    """Sample enriched awards DataFrame for fiscal analysis."""
    return create_sample_enriched_awards_df(num_awards=20)


@pytest.fixture
def sample_fiscal_impacts_df():
    """Sample fiscal impact data for testing."""
    return pd.DataFrame(
        [
            {
                "state": "CA",
                "bea_sector": "11",
                "fiscal_year": 2023,
                "wage_impact": Decimal("100000.00"),
                "consumption_impact": Decimal("50000.00"),
                "investment_impact": Decimal("25000.00"),
            },
            {
                "state": "TX",
                "bea_sector": "11",
                "fiscal_year": 2023,
                "wage_impact": Decimal("150000.00"),
                "consumption_impact": Decimal("75000.00"),
                "investment_impact": Decimal("35000.00"),
            },
        ]
    )


@pytest.fixture
def sample_tax_parameters():
    """Sample tax parameter configuration."""
    return {
        "payroll_tax_rate": 0.15,
        "income_tax_rate": 0.25,
        "excise_tax_rate": 0.05,
        "corporate_tax_rate": 0.21,
    }


@pytest.fixture
def sample_sbir_investment():
    """Sample SBIR investment amount."""
    return Decimal("1000000.00")


@pytest.fixture
def sample_discount_rate():
    """Sample discount rate for ROI calculations."""
    return Decimal("0.03")  # 3%


@pytest.fixture
def sample_fiscal_summary():
    """Sample fiscal return summary."""
    return {
        "total_tax_receipts": Decimal("250000.00"),
        "net_fiscal_return": Decimal("150000.00"),
        "roi_ratio": Decimal("0.25"),
        "payback_period_years": Decimal("4.0"),
    }


# ============================================================================
# Transition Fixtures
# ============================================================================


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
    from src.models.transition_models import ConfidenceLevel, TransitionSignals

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
    from src.models.transition_models import EvidenceBundle

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


@pytest.fixture
def default_config():
    """Default scoring configuration for tests (alias for backward compatibility)."""
    return {
        "base_score": 0.15,
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
                    {"range": [91, 180], "score": 0.7},
                    {"range": [181, 365], "score": 0.4},
                ],
                "beyond_window_penalty": 0.1,
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
            "text_similarity": {
                "enabled": False,
                "weight": 0.10,
            },
        },
        "confidence_thresholds": {
            "high": 0.85,
            "likely": 0.65,
        },
    }
