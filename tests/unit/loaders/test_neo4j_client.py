"""Unit tests for Neo4jClient.

Tests cover:
- Initialization and configuration
- Driver lazy initialization and cleanup
- Session management
- Node operations (upsert, batch upsert)
- Relationship operations (create, batch create)
- Constraint and index creation
- Metrics tracking
- Error handling
- Context manager protocol

All tests use mocks to avoid requiring a real Neo4j instance.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from src.loaders.neo4j.client import LoadMetrics, Neo4jClient, Neo4jConfig


pytestmark = pytest.mark.fast
# Note: Fixtures (neo4j_config, mock_driver, mock_session, mock_transaction)
# are now in tests/unit/loaders/conftest.py and automatically available


class TestNeo4jConfig:
    """Tests for Neo4jConfig model."""

    def test_config_initialization(self):
        """Test Neo4jConfig initialization with all fields."""
        config = Neo4jConfig(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="secret",  # pragma: allowlist secret
            database="mydb",
            batch_size=500,
        )

        assert config.uri == "bolt://localhost:7687"
        assert config.username == "neo4j"
        assert config.password == "secret"
        assert config.database == "mydb"
        assert config.batch_size == 500

    def test_config_defaults(self):
        """Test Neo4jConfig default values."""
        config = Neo4jConfig(
            uri="bolt://localhost:7687",
            username="neo4j",
            password="secret",
        )

        assert config.database == "neo4j"  # Default
        assert config.batch_size == 5000  # Default


class TestLoadMetrics:
    """Tests for LoadMetrics model."""

    def test_load_metrics_initialization(self):
        """Test LoadMetrics initialization with defaults."""
        metrics = LoadMetrics()

        assert metrics.nodes_created == {}
        assert metrics.nodes_updated == {}
        assert metrics.relationships_created == {}
        assert metrics.errors == 0
        assert metrics.duration_seconds == 0.0

    def test_load_metrics_with_data(self):
        """Test LoadMetrics with populated data."""
        metrics = LoadMetrics(
            nodes_created={"Company": 10, "Award": 5},
            nodes_updated={"Company": 3},
            relationships_created={"HAS_AWARD": 5},
            errors=2,
            duration_seconds=12.5,
        )

        assert metrics.nodes_created["Company"] == 10
        assert metrics.nodes_updated["Company"] == 3
        assert metrics.relationships_created["HAS_AWARD"] == 5
        assert metrics.errors == 2
        assert metrics.duration_seconds == 12.5

    def test_load_metrics_independent_instances(self):
        """Test that LoadMetrics instances don't share mutable defaults."""
        metrics1 = LoadMetrics()
        metrics2 = LoadMetrics()

        metrics1.nodes_created["Company"] = 5
        metrics1.errors = 1

        # metrics2 should be independent
        assert "Company" not in metrics2.nodes_created
        assert metrics2.errors == 0


class TestNeo4jClientInitialization:
    """Tests for Neo4jClient initialization and driver management."""

    def test_init_creates_config(self, neo4j_config):
        """Test client initialization stores config."""
        neo4j_config.auto_migrate = False  # Disable auto-migration for lazy init test
        client = Neo4jClient(neo4j_config)

        assert client.config == neo4j_config
        assert client._driver is None  # Lazy initialization

    @patch("src.loaders.neo4j.client.GraphDatabase.driver")
    def test_driver_lazy_initialization(self, mock_graph_database, neo4j_config, mock_driver):
        """Test driver is created lazily on first access."""
        neo4j_config.auto_migrate = False  # Disable auto-migration for lazy init test
        mock_graph_database.return_value = mock_driver

        client = Neo4jClient(neo4j_config)
        assert client._driver is None  # Not yet created

        # Access driver property
        driver = client.driver

        assert driver == mock_driver
        mock_graph_database.assert_called_once_with(
            neo4j_config.uri, auth=(neo4j_config.username, neo4j_config.password)
        )

    @patch("src.loaders.neo4j.client.GraphDatabase.driver")
    def test_driver_cached_after_first_access(self, mock_graph_database, neo4j_config, mock_driver):
        """Test driver is cached and not recreated on subsequent access."""
        mock_graph_database.return_value = mock_driver

        client = Neo4jClient(neo4j_config)

        # Access driver multiple times
        driver1 = client.driver
        driver2 = client.driver

        assert driver1 is driver2
        mock_graph_database.assert_called_once()  # Only called once

    def test_close_without_driver(self, neo4j_config):
        """Test close() when driver was never created."""
        client = Neo4jClient(neo4j_config)
        client.close()  # Should not raise

        assert client._driver is None

    @patch("src.loaders.neo4j.client.GraphDatabase.driver")
    def test_close_closes_driver(self, mock_graph_database, neo4j_config, mock_driver):
        """Test close() closes the driver and resets to None."""
        mock_graph_database.return_value = mock_driver

        client = Neo4jClient(neo4j_config)
        _ = client.driver  # Create driver

        client.close()

        mock_driver.close.assert_called_once()
        assert client._driver is None


class TestNeo4jClientSessionManagement:
    """Tests for Neo4j session context manager."""

    @patch("src.loaders.neo4j.client.GraphDatabase.driver")
    def test_session_context_manager(
        self, mock_graph_database, neo4j_config, mock_driver, mock_session
    ):
        """Test session context manager creates and closes session."""
        neo4j_config.auto_migrate = False  # Disable auto-migration
        mock_graph_database.return_value = mock_driver
        mock_driver.session.return_value = mock_session

        client = Neo4jClient(neo4j_config)

        with client.session() as session:
            assert session == mock_session

        mock_driver.session.assert_called_once_with(database=neo4j_config.database)
        mock_session.close.assert_called_once()

    @patch("src.loaders.neo4j.client.GraphDatabase.driver")
    def test_session_closes_on_exception(
        self, mock_graph_database, neo4j_config, mock_driver, mock_session
    ):
        """Test session is closed even if exception occurs."""
        mock_graph_database.return_value = mock_driver
        mock_driver.session.return_value = mock_session

        client = Neo4jClient(neo4j_config)

        with pytest.raises(ValueError):
            with client.session():
                raise ValueError("Test error")

        mock_session.close.assert_called_once()


class TestNeo4jClientNodeOperations:
    """Tests for node upsert operations."""

    def test_upsert_node_creates_new(self, mock_transaction):
        """Test upsert_node creates new node."""
        mock_result = Mock()
        mock_record = {"operation": "created"}
        mock_result.single.return_value = mock_record
        mock_transaction.run.return_value = mock_result

        client = Neo4jClient(Neo4jConfig(uri="bolt://localhost", username="neo4j", password="test"))

        result = client.upsert_node(
            mock_transaction, "Company", "uei", "ABC123", {"name": "Test Company"}
        )

        assert result["operation"] == "created"
        assert mock_transaction.run.call_count == 2  # Main query + cleanup

    def test_upsert_node_updates_existing(self, mock_transaction):
        """Test upsert_node updates existing node."""
        mock_result = Mock()
        mock_record = {"operation": "updated"}
        mock_result.single.return_value = mock_record
        mock_transaction.run.return_value = mock_result

        client = Neo4jClient(Neo4jConfig(uri="bolt://localhost", username="neo4j", password="test"))

        result = client.upsert_node(
            mock_transaction, "Company", "uei", "ABC123", {"name": "Updated Company"}
        )

        assert result["operation"] == "updated"

    def test_upsert_node_query_format(self, mock_transaction):
        """Test upsert_node generates correct Cypher query."""
        mock_result = Mock()
        mock_result.single.return_value = {"operation": "created"}
        mock_transaction.run.return_value = mock_result

        client = Neo4jClient(Neo4jConfig(uri="bolt://localhost", username="neo4j", password="test"))

        client.upsert_node(
            mock_transaction, "Company", "uei", "ABC123", {"name": "Test", "uei": "ABC123"}
        )

        # Check query structure
        call_args = mock_transaction.run.call_args_list[0]
        query = call_args[0][0]

        assert "MERGE (n:Company {uei: $key_value})" in query
        assert "ON CREATE SET n += $properties" in query
        assert "ON MATCH SET n += $properties" in query


class TestNeo4jClientBatchOperations:
    """Tests for batch node operations."""

    @patch.object(Neo4jClient, "session")
    def test_batch_upsert_single_batch(self, mock_session_cm, neo4j_config):
        """Test batch upsert with nodes fitting in single batch."""
        neo4j_config.auto_migrate = False  # Disable auto-migration
        # Setup mocks
        mock_session = MagicMock()
        mock_session_cm.return_value.__enter__.return_value = mock_session

        # Mock session.run() to return result with created_count and updated_count
        mock_result = MagicMock()
        mock_record = MagicMock()
        mock_record.__getitem__.side_effect = lambda key: {"created_count": 2, "updated_count": 0}[
            key
        ]
        mock_result.single.return_value = mock_record
        mock_session.run.return_value = mock_result

        client = Neo4jClient(neo4j_config)
        nodes = [
            {"uei": "ABC123", "name": "Company A"},
            {"uei": "XYZ789", "name": "Company B"},
        ]

        metrics = client.batch_upsert_nodes("Company", "uei", nodes)

        assert metrics.nodes_created["Company"] == 2
        # No explicit commit in implementation - uses auto-commit transactions

    @patch.object(Neo4jClient, "session")
    def test_batch_upsert_multiple_batches(self, mock_session_cm, neo4j_config):
        """Test batch upsert with nodes spanning multiple batches."""
        neo4j_config.auto_migrate = False  # Disable auto-migration
        # Setup for small batch size
        neo4j_config.batch_size = 2

        mock_session = MagicMock()
        mock_session_cm.return_value.__enter__.return_value = mock_session

        # Mock session.run() to return different counts per batch
        def mock_run_side_effect(query, **kwargs):
            mock_result = MagicMock()
            mock_record = MagicMock()
            # First two batches: 2 created each, last batch: 1 created
            batch_size = len(kwargs.get("batch", []))
            mock_record.__getitem__.side_effect = lambda key: {
                "created_count": batch_size,
                "updated_count": 0,
            }[key]
            mock_result.single.return_value = mock_record
            return mock_result

        mock_session.run.side_effect = mock_run_side_effect

        client = Neo4jClient(neo4j_config)
        nodes = [{"uei": f"UEI{i}", "name": f"Company {i}"} for i in range(5)]  # 5 nodes, 3 batches

        metrics = client.batch_upsert_nodes("Company", "uei", nodes)

        assert metrics.nodes_created["Company"] == 5
        # No explicit commit in implementation - uses auto-commit transactions

    @patch.object(Neo4jClient, "session")
    def test_batch_upsert_tracks_creates_and_updates(self, mock_session_cm, neo4j_config):
        """Test batch upsert correctly tracks creates vs updates."""
        mock_session = MagicMock()
        mock_tx = MagicMock()
        mock_session.begin_transaction.return_value.__enter__.return_value = mock_tx
        mock_session_cm.return_value.__enter__.return_value = mock_session

        # Mock session.run() to return 2 created, 1 updated
        mock_result = MagicMock()
        mock_record = MagicMock()
        mock_record.__getitem__.side_effect = lambda key: {"created_count": 2, "updated_count": 1}[
            key
        ]
        mock_result.single.return_value = mock_record
        mock_session.run.return_value = mock_result

        client = Neo4jClient(neo4j_config)
        nodes = [{"uei": f"UEI{i}"} for i in range(3)]

        metrics = client.batch_upsert_nodes("Company", "uei", nodes)

        assert metrics.nodes_created["Company"] == 2
        assert metrics.nodes_updated["Company"] == 1
        assert metrics.errors == 0

    @patch.object(Neo4jClient, "session")
    def test_batch_upsert_handles_missing_key(self, mock_session_cm, neo4j_config):
        """Test batch upsert handles nodes missing key property."""
        mock_session = MagicMock()
        mock_tx = MagicMock()
        mock_session.begin_transaction.return_value.__enter__.return_value = mock_tx
        mock_session_cm.return_value.__enter__.return_value = mock_session

        client = Neo4jClient(neo4j_config)
        nodes = [
            {"uei": "ABC123", "name": "Valid"},
            {"name": "Missing UEI"},  # Missing key property
            {"uei": "XYZ789", "name": "Also Valid"},
        ]

        metrics = client.batch_upsert_nodes("Company", "uei", nodes)

        assert metrics.errors == 1  # One node had missing key

    @patch.object(Neo4jClient, "session")
    def test_batch_upsert_handles_transaction_error(self, mock_session_cm, neo4j_config):
        """Test batch upsert handles transaction errors gracefully."""
        mock_session = MagicMock()
        mock_tx = MagicMock()
        mock_session.begin_transaction.return_value.__enter__.return_value = mock_tx
        mock_session_cm.return_value.__enter__.return_value = mock_session

        # Make session.run() raise exception
        mock_session.run.side_effect = Exception("Database error")

        client = Neo4jClient(neo4j_config)
        nodes = [{"uei": f"UEI{i}"} for i in range(2)]

        metrics = client.batch_upsert_nodes("Company", "uei", nodes)

        # First batch should fail, second shouldn't be attempted
        assert metrics.errors >= 1


class TestNeo4jClientRelationshipOperations:
    """Tests for relationship creation operations."""

    def test_create_relationship_success(self, mock_transaction):
        """Test creating relationship between existing nodes."""
        mock_result = Mock()
        mock_record = {"r": "relationship", "source": "node1", "target": "node2"}
        mock_result.single.return_value = mock_record
        mock_transaction.run.return_value = mock_result

        client = Neo4jClient(Neo4jConfig(uri="bolt://localhost", username="neo4j", password="test"))

        result = client.create_relationship(
            mock_transaction,
            "Company",
            "uei",
            "ABC123",
            "Award",
            "award_id",
            "AWD001",
            "HAS_AWARD",
            {"year": 2023},
        )

        assert result["status"] == "created"
        mock_transaction.run.assert_called_once()

    def test_create_relationship_missing_source(self, mock_transaction):
        """Test creating relationship when source node doesn't exist."""
        mock_result = Mock()
        mock_result.single.return_value = None  # No match found
        mock_transaction.run.return_value = mock_result

        client = Neo4jClient(Neo4jConfig(uri="bolt://localhost", username="neo4j", password="test"))

        result = client.create_relationship(
            mock_transaction,
            "Company",
            "uei",
            "NOTFOUND",
            "Award",
            "award_id",
            "AWD001",
            "HAS_AWARD",
        )

        assert result["status"] == "failed"
        assert "not found" in result["reason"]

    def test_create_relationship_query_format(self, mock_transaction):
        """Test relationship creation generates correct Cypher query."""
        mock_result = Mock()
        mock_result.single.return_value = {"r": "rel"}
        mock_transaction.run.return_value = mock_result

        client = Neo4jClient(Neo4jConfig(uri="bolt://localhost", username="neo4j", password="test"))

        client.create_relationship(
            mock_transaction,
            "Company",
            "uei",
            "ABC123",
            "Award",
            "award_id",
            "AWD001",
            "HAS_AWARD",
            {"amount": 100000},
        )

        call_args = mock_transaction.run.call_args
        query = call_args[0][0]

        assert "MATCH (source:Company {uei: $source_value})" in query
        assert "MATCH (target:Award {award_id: $target_value})" in query
        assert "MERGE (source)-[r:HAS_AWARD]->(target)" in query
        assert "SET r += $properties" in query


class TestNeo4jClientBatchRelationships:
    """Tests for batch relationship creation."""

    @patch.object(Neo4jClient, "session")
    def test_batch_create_relationships(self, mock_session_cm, neo4j_config):
        """Test batch relationship creation."""
        mock_session = MagicMock()
        mock_tx = MagicMock()
        mock_session.begin_transaction.return_value.__enter__.return_value = mock_tx
        mock_session_cm.return_value.__enter__.return_value = mock_session

        # Mock tx.run() to return result with created_count
        mock_result = MagicMock()
        mock_record = MagicMock()
        mock_record.__getitem__.side_effect = lambda key: {"created_count": 2}[key]
        mock_result.single.return_value = mock_record
        mock_tx.run.return_value = mock_result

        client = Neo4jClient(neo4j_config)
        relationships = [
            ("Company", "uei", "ABC123", "Award", "award_id", "AWD001", "HAS_AWARD", None),
            ("Company", "uei", "XYZ789", "Award", "award_id", "AWD002", "HAS_AWARD", None),
        ]

        metrics = client.batch_create_relationships(relationships)

        assert metrics.relationships_created["HAS_AWARD"] == 2

    @patch.object(Neo4jClient, "session")
    def test_batch_create_relationships_with_failures(self, mock_session_cm, neo4j_config):
        """Test batch relationship creation with some failures."""
        mock_session = MagicMock()
        mock_tx = MagicMock()
        mock_session.begin_transaction.return_value.__enter__.return_value = mock_tx
        mock_session_cm.return_value.__enter__.return_value = mock_session

        # Mock tx.run() to return result with created_count
        mock_result = MagicMock()
        mock_record = MagicMock()
        mock_record.__getitem__.side_effect = lambda key: {"created_count": 2}[key]
        mock_result.single.return_value = mock_record
        mock_tx.run.return_value = mock_result

        client = Neo4jClient(neo4j_config)
        relationships = [
            ("Company", "uei", "ABC123", "Award", "award_id", "AWD001", "HAS_AWARD", None),
            ("Company", "uei", "NOTFOUND", "Award", "award_id", "AWD002", "HAS_AWARD", None),
            ("Company", "uei", "XYZ789", "Award", "award_id", "AWD003", "HAS_AWARD", None),
        ]

        metrics = client.batch_create_relationships(relationships)

        assert metrics.relationships_created["HAS_AWARD"] == 2


class TestNeo4jClientConstraintsAndIndexes:
    """Tests for constraint and index creation."""

    @patch.object(Neo4jClient, "session")
    def test_create_constraints(self, mock_session_cm, neo4j_config):
        """Test creating uniqueness constraints."""
        mock_session = MagicMock()
        mock_session_cm.return_value.__enter__.return_value = mock_session

        client = Neo4jClient(neo4j_config)
        client.create_constraints()

        # Should run multiple constraint creation queries
        assert mock_session.run.call_count >= 4  # Company, Award, Researcher, Patent

    @patch.object(Neo4jClient, "session")
    def test_create_constraints_handles_existing(self, mock_session_cm, neo4j_config):
        """Test creating constraints when they already exist."""
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Constraint already exists")
        mock_session_cm.return_value.__enter__.return_value = mock_session

        client = Neo4jClient(neo4j_config)
        # Should not raise, just log warning
        client.create_constraints()

    @patch.object(Neo4jClient, "session")
    def test_create_indexes(self, mock_session_cm, neo4j_config):
        """Test creating property indexes."""
        mock_session = MagicMock()
        mock_session_cm.return_value.__enter__.return_value = mock_session

        client = Neo4jClient(neo4j_config)
        client.create_indexes()

        # Should run multiple index creation queries
        assert mock_session.run.call_count >= 4  # company_name, award_date, etc.

    @patch.object(Neo4jClient, "session")
    def test_create_indexes_handles_existing(self, mock_session_cm, neo4j_config):
        """Test creating indexes when they already exist."""
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Index already exists")
        mock_session_cm.return_value.__enter__.return_value = mock_session

        client = Neo4jClient(neo4j_config)
        # Should not raise, just log warning
        client.create_indexes()


class TestNeo4jClientContextManager:
    """Tests for context manager protocol."""

    def test_context_manager_enter(self, neo4j_config):
        """Test context manager __enter__ returns client."""
        client = Neo4jClient(neo4j_config)

        with client as ctx_client:
            assert ctx_client is client

    @patch.object(Neo4jClient, "close")
    def test_context_manager_exit_closes(self, mock_close, neo4j_config):
        """Test context manager __exit__ closes driver."""
        client = Neo4jClient(neo4j_config)

        with client:
            pass

        mock_close.assert_called_once()

    @patch.object(Neo4jClient, "close")
    def test_context_manager_exit_on_exception(self, mock_close, neo4j_config):
        """Test context manager closes even on exception."""
        client = Neo4jClient(neo4j_config)

        with pytest.raises(ValueError):
            with client:
                raise ValueError("Test error")

        mock_close.assert_called_once()
