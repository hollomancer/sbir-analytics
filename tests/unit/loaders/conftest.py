"""Shared fixtures for Neo4j loader tests."""

from unittest.mock import MagicMock

import pytest

# Import shared fixtures
from tests.conftest_shared import (
    empty_load_metrics,
    mock_driver,
    mock_session,
    mock_transaction,
    neo4j_config,
)
from tests.mocks import Neo4jMocks


def create_mock_client_with_session(mock_session: MagicMock) -> MagicMock:
    """Helper to create a mock Neo4jClient with a properly configured session context manager.

    This is a shared helper for Neo4j loader tests to avoid duplication.
    """
    mock_client = Neo4jMocks.driver()
    mock_client.config.batch_size = 1000
    mock_context = Neo4jMocks.session()
    mock_context.__enter__.return_value = mock_session
    mock_context.__exit__.return_value = None
    mock_client.session.return_value = mock_context
    return mock_client


@pytest.fixture
def mock_client_factory():
    """Fixture that returns the create_mock_client_with_session helper."""
    return create_mock_client_with_session


# Re-export for pytest discovery
__all__ = [
    "neo4j_config",
    "mock_driver",
    "mock_session",
    "mock_transaction",
    "empty_load_metrics",
    "create_mock_client_with_session",
    "mock_client_factory",
]
