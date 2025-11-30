"""Integration tests for Neo4j client.

These tests require a running Neo4j instance.
Run with: docker-compose up -d neo4j
"""

import pytest
from tests.conftest import neo4j_running as neo4j_available

from src.loaders.neo4j.client import LoadMetrics, Neo4jClient

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not neo4j_available(), reason="Neo4j not running - see INTEGRATION_TEST_ANALYSIS.md"
    ),
]


@pytest.mark.integration
class TestNeo4jClientConnection:
    """Test Neo4j client connection management."""

    def test_create_client(self, neo4j_config):
        """Test creating Neo4j client."""
        client = Neo4jClient(neo4j_config)
        assert client.config == neo4j_config
        assert client._driver is None  # Lazy initialization
        client.close()

    def test_driver_property(self, neo4j_client):
        """Test driver property creates connection."""
        driver = neo4j_client.driver
        assert driver is not None

    def test_session_context_manager(self, neo4j_client):
        """Test session context manager."""
        with neo4j_client.session() as session:
            result = session.run("RETURN 1 as num")
            record = result.single()
            assert record["num"] == 1

    def test_client_context_manager(self, neo4j_config):
        """Test client as context manager."""
        with Neo4jClient(neo4j_config) as client:
            with client.session() as session:
                result = session.run("RETURN 2 as num")
                record = result.single()
                assert record["num"] == 2


@pytest.mark.integration
class TestNeo4jConstraintsAndIndexes:
    """Test constraint and index creation."""

    def test_create_constraints(self, neo4j_client):
        """Test creating unique constraints."""
        neo4j_client.create_constraints()

        # Verify constraints exist
        with neo4j_client.session() as session:
            result = session.run("SHOW CONSTRAINTS")
            constraints = [record["name"] for record in result]

            assert any("company_uei" in c for c in constraints)
            assert any("award_id" in c for c in constraints)

    def test_create_indexes(self, neo4j_client):
        """Test creating indexes."""
        neo4j_client.create_indexes()

        # Verify indexes exist
        with neo4j_client.session() as session:
            result = session.run("SHOW INDEXES")
            indexes = [record["name"] for record in result]

            assert any("company_name" in idx for idx in indexes)
            assert any("award_date" in idx for idx in indexes)


@pytest.mark.integration
class TestNeo4jNodeUpsert:
    """Test node upsert operations."""

    def test_upsert_single_node_create(self, neo4j_client):
        """Test upserting a single node (create)."""
        with neo4j_client.session() as session:
            with session.begin_transaction() as tx:
                result = neo4j_client.upsert_node(
                    tx,
                    "TestCompany",
                    "uei",
                    "UEI001",
                    {"uei": "UEI001", "name": "Test Company"},
                )

                assert result["operation"] == "created"
                tx.commit()

        # Verify node exists
        with neo4j_client.session() as session:
            result = session.run(
                "MATCH (c:TestCompany {uei: $uei}) RETURN c",
                uei="UEI001",
            )
            record = result.single()
            assert record is not None
            assert record["c"]["name"] == "Test Company"

    def test_upsert_single_node_update(self, neo4j_client, neo4j_helper):
        """Test upserting a single node (update)."""
        # Create initial node using helper
        neo4j_helper.create_company(uei="UEI002", name="Original Name")

        # Update node
        with neo4j_client.session() as session:
            with session.begin_transaction() as tx:
                result = neo4j_client.upsert_node(
                    tx,
                    "TestCompany",
                    "uei",
                    "UEI002",
                    {"uei": "UEI002", "name": "Updated Name", "city": "Boston"},
                )

                assert result["operation"] == "updated"
                tx.commit()

        # Verify node was updated
        with neo4j_client.session() as session:
            result = session.run(
                "MATCH (c:TestCompany {uei: $uei}) RETURN c",
                uei="UEI002",
            )
            record = result.single()
            assert record["c"]["name"] == "Updated Name"
            assert record["c"]["city"] == "Boston"

    def test_batch_upsert_nodes(self, neo4j_client):
        """Test batch upserting nodes."""
        nodes = [{"uei": f"UEI{i:03d}", "name": f"Company {i}"} for i in range(1, 21)]

        metrics = neo4j_client.batch_upsert_nodes("TestCompany", "uei", nodes)

        assert isinstance(metrics, LoadMetrics)
        assert metrics.nodes_created.get("TestCompany", 0) == 20
        assert metrics.errors == 0

        # Verify all nodes exist
        with neo4j_client.session() as session:
            result = session.run("MATCH (c:TestCompany) RETURN count(c) as count")
            record = result.single()
            assert record["count"] == 20

    def test_batch_upsert_mixed_create_update(self, neo4j_client, neo4j_helper):
        """Test batch upsert with both creates and updates."""
        # Create some initial nodes using helper
        for i in range(1, 6):
            neo4j_helper.create_company(uei=f"UEI{i:03d}", name=f"Old Company {i}")

        # Batch upsert with overlapping and new nodes
        nodes = [{"uei": f"UEI{i:03d}", "name": f"Company {i}"} for i in range(1, 11)]

        metrics = neo4j_client.batch_upsert_nodes("TestCompany", "uei", nodes)

        assert metrics.nodes_created.get("TestCompany", 0) == 5  # New nodes
        assert metrics.nodes_updated.get("TestCompany", 0) == 5  # Updated nodes
        assert metrics.errors == 0

    def test_batch_upsert_with_error(self, neo4j_client):
        """Test batch upsert handles nodes with missing keys."""
        nodes = [
            {"uei": "UEI001", "name": "Company 1"},
            {"name": "Company 2"},  # Missing uei key
            {"uei": "UEI003", "name": "Company 3"},
        ]

        metrics = neo4j_client.batch_upsert_nodes("TestCompany", "uei", nodes)

        assert metrics.nodes_created.get("TestCompany", 0) == 2
        assert metrics.errors == 1


@pytest.mark.integration
class TestNeo4jRelationships:
    """Test relationship creation."""

    def test_create_relationship_success(self, neo4j_client, neo4j_helper):
        """Test creating a relationship between two nodes."""
        # Create source and target nodes using helper
        neo4j_helper.create_company(uei="UEI001")
        neo4j_helper.create_award(award_id="AWARD001")

        # Create relationship
        with neo4j_client.session() as session:
            with session.begin_transaction() as tx:
                result = neo4j_client.create_relationship(
                    tx,
                    "TestCompany",
                    "uei",
                    "UEI001",
                    "TestAward",
                    "award_id",
                    "AWARD001",
                    "RECEIVED",
                    {"award_date": "2023-01-15"},
                )

                assert result["status"] == "created"
                tx.commit()

        # Verify relationship
        with neo4j_client.session() as session:
            result = session.run(
                """
                MATCH (c:TestCompany {uei: $uei})-[r:RECEIVED]->(a:TestAward {award_id: $award_id})
                RETURN r
                """,
                uei="UEI001",
                award_id="AWARD001",
            )
            record = result.single()
            assert record is not None
            assert record["r"]["award_date"] == "2023-01-15"

    def test_create_relationship_missing_source(self, neo4j_client, neo4j_helper):
        """Test creating relationship with missing source node."""
        # Create only target node using helper
        neo4j_helper.create_award(award_id="AWARD001")

        # Attempt to create relationship
        with neo4j_client.session() as session:
            with session.begin_transaction() as tx:
                result = neo4j_client.create_relationship(
                    tx,
                    "TestCompany",
                    "uei",
                    "NONEXISTENT",
                    "TestAward",
                    "award_id",
                    "AWARD001",
                    "RECEIVED",
                )

                assert result["status"] == "failed"
                assert "not found" in result["reason"]

    def test_batch_create_relationships(self, neo4j_client, neo4j_helper):
        """Test batch creating relationships."""
        # Create nodes using helper
        for i in range(1, 6):
            neo4j_helper.create_company(uei=f"UEI{i:03d}")
            neo4j_helper.create_award(award_id=f"AWARD{i:03d}")

        # Create relationships
        relationships = [
            (
                "TestCompany",
                "uei",
                f"UEI{i:03d}",
                "TestAward",
                "award_id",
                f"AWARD{i:03d}",
                "RECEIVED",
                {"year": 2023},
            )
            for i in range(1, 6)
        ]

        metrics = neo4j_client.batch_create_relationships(relationships)

        assert metrics.relationships_created.get("RECEIVED", 0) == 5
        assert metrics.errors == 0

        # Verify relationships
        with neo4j_client.session() as session:
            result = session.run("MATCH ()-[r:RECEIVED]->() RETURN count(r) as count")
            record = result.single()
            assert record["count"] == 5


@pytest.mark.integration
class TestNeo4jTransactions:
    """Test transaction management."""

    def test_transaction_commit(self, neo4j_client):
        """Test transaction commit persists data."""
        with neo4j_client.session() as session:
            with session.begin_transaction() as tx:
                tx.run(
                    "CREATE (c:TestCompany {uei: $uei, name: $name})",
                    uei="UEI001",
                    name="Test Company",
                )
                tx.commit()

        # Verify data persisted
        with neo4j_client.session() as session:
            result = session.run("MATCH (c:TestCompany) RETURN count(c) as count")
            assert result.single()["count"] == 1

    def test_transaction_rollback(self, neo4j_client):
        """Test transaction rollback discards data."""
        with neo4j_client.session() as session:
            with session.begin_transaction() as tx:
                tx.run(
                    "CREATE (c:TestCompany {uei: $uei, name: $name})",
                    uei="UEI001",
                    name="Test Company",
                )
                tx.rollback()

        # Verify data was not persisted
        with neo4j_client.session() as session:
            result = session.run("MATCH (c:TestCompany) RETURN count(c) as count")
            assert result.single()["count"] == 0
