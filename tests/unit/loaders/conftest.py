"""Shared fixtures for Neo4j loader tests."""

from unittest.mock import MagicMock, Mock

import pytest

from src.loaders.neo4j.client import LoadMetrics, Neo4jConfig
from tests.utils.config_mocks import create_mock_neo4j_config


@pytest.fixture
def neo4j_config():
    """Sample Neo4j configuration using consolidated utility."""
    config_dict = create_mock_neo4j_config(
        uri="bolt://localhost:7687",
        database="test_db",
        username="neo4j",
        password="test_password",  # pragma: allowlist secret
    )
    return Neo4jConfig(**config_dict)


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

