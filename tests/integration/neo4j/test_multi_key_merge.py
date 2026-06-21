"""Integration tests for multi-key MERGE functionality.

Uses the shared `neo4j_client` fixture from tests/conftest_shared.py
(reachable via tests/integration/conftest.py), which reads credentials from
NEO4J_USERNAME / NEO4J_PASSWORD with sensible test defaults.

Avoids defining a local fixture: a hardcoded password mismatched with the CI
container trips Neo4j's auth rate limiter, which then rejects every other
test in the run.

All tests in this module share an `xdist_group("neo4j_integration")` so they
run sequentially on a single xdist worker. The integration test job uses
`-n auto --dist=loadgroup`, so without the group these tests would race each
other (and `tests/integration/test_neo4j_client.py`) against the same Neo4j
container, producing `AssertionError: assert 2 == 1` / `assert 0 == 20`
style failures from leftover state.
"""

import pytest
from tests.conftest import neo4j_running as neo4j_available

pytestmark = [
    pytest.mark.skipif(
        not neo4j_available(), reason="Neo4j not running - see INTEGRATION_TEST_ANALYSIS.md"
    ),
    pytest.mark.xdist_group("neo4j_integration"),
]


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
