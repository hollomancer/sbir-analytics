"""Shared domain fixtures for the test suite.

This module contains fixtures for specific domains that require explicit imports.
Import these in subdirectory conftest.py files as needed:

    from tests.conftest_shared import (
        neo4j_config, neo4j_client, neo4j_helper,
        sample_sbir_df, sample_recipient_df,
        sample_award, sample_contract,
        default_config, default_transition_config,
    )

Fixture Categories:
- Neo4j: neo4j_config, neo4j_client, neo4j_helper
- Mocks: mock_driver, mock_session, mock_transaction
- Enrichment: mock_enrichment_config, sample_sbir_df, sample_recipient_df
- Transition: default_transition_config, sample_award, sample_contract, mock_scorer
- DataFrame Builders: builder_awards_df, builder_contracts_df, builder_companies_df
"""

import os
from datetime import date, datetime
from unittest.mock import Mock

import pandas as pd
import pytest

# Neo4j fixtures (optional - skip if neo4j not installed)
try:
    from sbir_graph.loaders.neo4j.client import LoadMetrics, Neo4jClient, Neo4jConfig
except ImportError:
    LoadMetrics = None  # type: ignore[assignment, misc]
    Neo4jClient = None  # type: ignore[assignment, misc]
    Neo4jConfig = None  # type: ignore[assignment, misc]
from tests.factories import DataFrameBuilder
from tests.mocks import Neo4jMocks
from tests.utils.config_mocks import create_mock_neo4j_config
from tests.utils.fixtures import (
    create_sample_award_dict,
    create_sample_sbir_data,
    create_sample_transition_detector_config,
)


# ============================================================================
# Neo4j Fixtures
# ============================================================================


@pytest.fixture(scope="module")
def neo4j_config():
    """Create Neo4j configuration for testing."""
    config = create_mock_neo4j_config(
        uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        username=os.getenv("NEO4J_USERNAME", "neo4j"),
        password=os.getenv("NEO4J_PASSWORD", "password"),
        database=os.getenv("NEO4J_DATABASE", "neo4j"),
    )
    # Don't eagerly connect/migrate on construction: it breaks the lazy-init
    # contract (test_create_client) and adds auth attempts that can trip Neo4j's
    # auth rate limiter during startup.
    config["auto_migrate"] = False
    return Neo4jConfig(**config)


@pytest.fixture(scope="module")
def neo4j_client(neo4j_config):
    """Create Neo4j client for testing."""
    client = Neo4jClient(neo4j_config)
    yield client
    client.close()


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
    return Neo4jMocks.driver()


@pytest.fixture
def mock_session():
    """Mock Neo4j session."""
    return Neo4jMocks.session()


@pytest.fixture
def mock_transaction():
    """Mock Neo4j transaction."""
    return Neo4jMocks.transaction()


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
    from sbir_etl.models.transition_models import ConfidenceLevel, TransitionSignals

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
    from sbir_etl.models.transition_models import EvidenceBundle

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
        "timing_window": {
            "min_days_after_completion": 0,
            "max_days_after_completion": 730,
        },
        "vendor_matching": {
            "require_match": True,
            "min_confidence": 0.7,
        },
        "confidence_thresholds": {
            "high": 0.85,
            "likely": 0.65,
        },
    }


# ============================================================================
# DataFrame Builder Fixtures
# ============================================================================


@pytest.fixture
def builder_awards_df():
    """Sample awards DataFrame using builder (5 awards)."""
    return DataFrameBuilder.awards(5).build()


@pytest.fixture
def builder_contracts_df():
    """Sample contracts DataFrame using builder (5 contracts)."""
    return DataFrameBuilder.contracts(5).build()


@pytest.fixture
def builder_companies_df():
    """Sample companies DataFrame using builder (5 companies)."""
    return DataFrameBuilder.companies(5).build()


