"""Tests for TransitionLoader initialization and index creation.

Split from test_transitions.py for better organization.
"""

import pytest

from src.loaders.neo4j.transitions import TransitionLoader
from tests.mocks import Neo4jMocks
from tests.unit.loaders.conftest import create_mock_client_with_session

pytestmark = pytest.mark.fast


class TestTransitionLoaderInitialization:
    """Tests for TransitionLoader initialization."""

    def test_initialization_with_default_batch_size(self):
        """Test TransitionLoader initialization with default batch size."""
        mock_client = Neo4jMocks.driver()
        mock_client.config.batch_size = 1000
        loader = TransitionLoader(mock_client)

        assert loader.client == mock_client
        assert loader.client.config.batch_size == 1000
        assert loader.metrics.nodes_created == {}
        assert loader.metrics.nodes_updated == {}
        assert loader.metrics.relationships_created == {}
        assert loader.metrics.errors == 0

    def test_initialization_with_custom_batch_size(self):
        """Test TransitionLoader initialization with custom batch size."""
        mock_client = Neo4jMocks.driver()
        mock_client.config.batch_size = 500
        loader = TransitionLoader(mock_client)

        assert loader.client == mock_client
        assert loader.client.config.batch_size == 500

    def test_stats_structure(self):
        """Test that metrics structure has expected attributes."""
        mock_client = Neo4jMocks.driver()
        loader = TransitionLoader(mock_client)

        assert hasattr(loader.metrics, "nodes_created")
        assert hasattr(loader.metrics, "nodes_updated")
        assert hasattr(loader.metrics, "relationships_created")
        assert hasattr(loader.metrics, "errors")

    def test_get_stats_returns_copy(self):
        """Test get_stats returns a copy of stats."""
        mock_client = Neo4jMocks.driver()
        loader = TransitionLoader(mock_client)

        stats1 = loader.metrics
        stats2 = loader.metrics

        assert stats1 is stats2


class TestTransitionLoaderIndexes:
    """Tests for index creation methods."""

    def test_ensure_indexes_creates_all(self):
        """Test ensure_indexes creates all expected indexes."""
        mock_client = Neo4jMocks.driver()
        mock_session = Neo4jMocks.session()
        mock_client = create_mock_client_with_session(mock_session)

        loader = TransitionLoader(mock_client)
        loader.ensure_indexes()

        # Should have called run multiple times for different indexes
        assert mock_session.run.call_count >= 3

    def test_ensure_indexes_handles_existing(self):
        """Test ensure_indexes handles already existing indexes gracefully."""
        mock_client = Neo4jMocks.driver()
        mock_session = Neo4jMocks.session()
        mock_client = create_mock_client_with_session(mock_session)

        # Simulate index already exists error
        from neo4j.exceptions import ClientError

        mock_session.run.side_effect = ClientError("Index already exists")

        loader = TransitionLoader(mock_client)
        # Should not raise
        loader.ensure_indexes()
