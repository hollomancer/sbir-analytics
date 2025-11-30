"""Unit tests for Neo4j client using mocks (no real Neo4j required)."""

from unittest.mock import MagicMock, patch

import pytest

from src.loaders.neo4j.client import Neo4jClient, Neo4jConfig


@pytest.fixture
def neo4j_config():
    """Create test Neo4j config."""
    return Neo4jConfig(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="test",
        database="neo4j",
        auto_migrate=False,
    )


class TestNeo4jClientMock:
    """Unit tests for Neo4jClient with mocked driver."""

    @patch("src.loaders.neo4j.client.GraphDatabase")
    def test_client_initialization(self, mock_gdb, neo4j_config):
        """Test client initializes without connecting."""
        client = Neo4jClient(neo4j_config)
        assert client.config == neo4j_config
        assert client._driver is None  # Lazy connection

    @patch("src.loaders.neo4j.client.GraphDatabase")
    def test_driver_lazy_creation(self, mock_gdb, neo4j_config):
        """Test driver is created lazily on first access."""
        mock_gdb.driver.return_value = MagicMock()
        client = Neo4jClient(neo4j_config)

        # Driver not created yet
        assert client._driver is None

        # Access driver property
        _ = client.driver

        # Now driver is created
        mock_gdb.driver.assert_called_once_with(
            neo4j_config.uri,
            auth=(neo4j_config.username, neo4j_config.password),
        )

    @patch("src.loaders.neo4j.client.GraphDatabase")
    def test_close_driver(self, mock_gdb, neo4j_config):
        """Test driver close."""
        mock_driver = MagicMock()
        mock_gdb.driver.return_value = mock_driver

        client = Neo4jClient(neo4j_config)
        _ = client.driver  # Create driver
        client.close()

        mock_driver.close.assert_called_once()
        assert client._driver is None

    @patch("src.loaders.neo4j.client.GraphDatabase")
    def test_batch_upsert_empty_nodes_returns_empty_metrics(self, mock_gdb, neo4j_config):
        """Test batch_upsert with empty nodes returns metrics with no operations."""
        client = Neo4jClient(neo4j_config)
        metrics = client.batch_upsert_nodes(
            label="TestNode",
            key_property="id",
            nodes=[],
        )

        # Empty input should return metrics with empty dicts (no labels processed)
        assert metrics.errors == 0
        assert metrics.duration_seconds >= 0


class TestNeo4jConfigValidation:
    """Test Neo4j configuration validation."""

    def test_config_defaults(self):
        """Test config uses defaults."""
        config = Neo4jConfig(
            uri="bolt://test:7687",
            username="testuser",
            password="testpass",
        )

        assert config.uri == "bolt://test:7687"
        assert config.username == "testuser"
        assert config.database == "neo4j"  # default
        assert config.auto_migrate is True  # default

    def test_config_custom_values(self):
        """Test config accepts custom values."""
        config = Neo4jConfig(
            uri="bolt://custom:7687",
            username="admin",
            password="secret",
            database="testdb",
            auto_migrate=False,
        )

        assert config.uri == "bolt://custom:7687"
        assert config.database == "testdb"
        assert config.auto_migrate is False

    def test_config_batch_size_default(self):
        """Test batch_size has sensible default."""
        config = Neo4jConfig(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="password",
        )
        assert config.batch_size > 0
