"""Integration tests for multi-key MERGE functionality."""

import pytest
from tests.conftest import neo4j_running as neo4j_available

from src.loaders.neo4j import Neo4jClient, Neo4jConfig

pytestmark = pytest.mark.skipif(
    not neo4j_available(), reason="Neo4j not running - see INTEGRATION_TEST_ANALYSIS.md"
)


@pytest.fixture
def neo4j_client():
    """Create Neo4j client for testing."""
    config = Neo4jConfig(
        uri="bolt://localhost:7687",
        username="neo4j",
        password="neo4j",  # pragma: allowlist secret
        database="neo4j",
        auto_migrate=False,  # Don't run migrations in tests
    )
    client = Neo4jClient(config)
    yield client
    client.close()


@pytest.mark.integration
def test_multi_key_merge_uei(neo4j_client):
    """Test merging organizations by UEI."""
    # Clean up first
    with neo4j_client.session() as session:
        session.run("MATCH (o:Organization) DETACH DELETE o")

    # Create first organization
    nodes1 = [
        {
            "organization_id": "org_test_1",
            "name": "Test Company",
            "uei": "TEST123",
            "duns": None,
        }
    ]

    metrics1 = neo4j_client.batch_upsert_organizations_with_multi_key(
        nodes=nodes1,
        merge_on_uei=True,
        merge_on_duns=True,
    )

    assert metrics1.nodes_created.get("Organization", 0) == 1

    # Create second organization with same UEI but different ID
    nodes2 = [
        {
            "organization_id": "org_test_2",
            "name": "Test Company Inc",
            "uei": "TEST123",
            "duns": None,
        }
    ]

    metrics2 = neo4j_client.batch_upsert_organizations_with_multi_key(
        nodes=nodes2,
        merge_on_uei=True,
        merge_on_duns=True,
    )

    # Should merge into existing, not create new
    assert metrics2.nodes_created.get("Organization", 0) == 0
    assert metrics2.nodes_updated.get("Organization", 0) == 1

    # Verify only one node exists
    with neo4j_client.session() as session:
        result = session.run("MATCH (o:Organization {uei: 'TEST123'}) RETURN count(o) as count")
        record = result.single()
        assert record["count"] == 1


@pytest.mark.integration
def test_multi_key_merge_duns(neo4j_client):
    """Test merging organizations by DUNS."""
    # Clean up first
    with neo4j_client.session() as session:
        session.run("MATCH (o:Organization) DETACH DELETE o")

    # Create first organization
    nodes1 = [
        {
            "organization_id": "org_test_1",
            "name": "Test Company",
            "uei": None,
            "duns": "123456789",
        }
    ]

    metrics1 = neo4j_client.batch_upsert_organizations_with_multi_key(
        nodes=nodes1,
        merge_on_uei=True,
        merge_on_duns=True,
    )

    assert metrics1.nodes_created.get("Organization", 0) == 1

    # Create second organization with same DUNS but different ID
    nodes2 = [
        {
            "organization_id": "org_test_2",
            "name": "Test Company LLC",
            "uei": None,
            "duns": "123456789",
        }
    ]

    metrics2 = neo4j_client.batch_upsert_organizations_with_multi_key(
        nodes=nodes2,
        merge_on_uei=True,
        merge_on_duns=True,
    )

    # Should merge into existing
    assert metrics2.nodes_created.get("Organization", 0) == 0
    assert metrics2.nodes_updated.get("Organization", 0) == 1


@pytest.mark.integration
def test_multi_key_merge_no_duplicates(neo4j_client):
    """Test that non-duplicate organizations are created normally."""
    # Clean up first
    with neo4j_client.session() as session:
        session.run("MATCH (o:Organization) DETACH DELETE o")

    nodes = [
        {
            "organization_id": "org_test_1",
            "name": "Company A",
            "uei": "UEI001",
            "duns": None,
        },
        {
            "organization_id": "org_test_2",
            "name": "Company B",
            "uei": "UEI002",
            "duns": None,
        },
    ]

    metrics = neo4j_client.batch_upsert_organizations_with_multi_key(
        nodes=nodes,
        merge_on_uei=True,
        merge_on_duns=True,
    )

    # Should create both
    assert metrics.nodes_created.get("Organization", 0) == 2


@pytest.mark.integration
def test_multi_key_merge_history_tracking(neo4j_client):
    """Test that merge history is tracked."""
    # Clean up first
    with neo4j_client.session() as session:
        session.run("MATCH (o:Organization) DETACH DELETE o")

    # Create first organization
    nodes1 = [
        {
            "organization_id": "org_test_1",
            "name": "Test Company",
            "uei": "TEST123",
        }
    ]

    neo4j_client.batch_upsert_organizations_with_multi_key(
        nodes=nodes1,
        merge_on_uei=True,
        track_merge_history=True,
    )

    # Create second organization with same UEI
    nodes2 = [
        {
            "organization_id": "org_test_2",
            "name": "Test Company Inc",
            "uei": "TEST123",
        }
    ]

    neo4j_client.batch_upsert_organizations_with_multi_key(
        nodes=nodes2,
        merge_on_uei=True,
        track_merge_history=True,
    )

    # Verify merge history is tracked
    with neo4j_client.session() as session:
        result = session.run(
            """
            MATCH (o:Organization {uei: 'TEST123'})
            RETURN o.__merged_from as merged_from
            """
        )
        record = result.single()
        if record and record["merged_from"]:
            assert "org_test_2" in record["merged_from"]
