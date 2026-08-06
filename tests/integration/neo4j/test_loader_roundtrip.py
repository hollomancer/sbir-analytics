"""Round-trip contract for the standardized Neo4j loader path.

Loads fixture awards and organizations through BaseNeo4jLoader's batch APIs,
reads them back with Cypher, and re-runs the identical batch to prove MERGE
idempotency — the property the loaders' pipelines-tier claim rests on. Uses
dedicated RoundTrip* labels so it cannot interfere with real schema data.

Requires a running Neo4j; skips otherwise, like the sibling integration tests.
"""

from __future__ import annotations

import pytest

from sbir_graph.loaders.neo4j.base import BaseNeo4jLoader


pytestmark = [
    pytest.mark.integration,
    # Resolve Neo4j when a test executes, not while pytest imports this module.
    pytest.mark.usefixtures("neo4j_driver"),
    # Shares one xdist worker with the other Neo4j integration tests so they
    # never race each other against the shared container.
    pytest.mark.xdist_group("neo4j_integration"),
    pytest.mark.timeout(120),
]

AWARD_LABEL = "RoundTripAward"
ORG_LABEL = "RoundTripOrganization"
REL_TYPE = "RT_AWARDED_TO"


class RoundTripLoader(BaseNeo4jLoader):
    """Minimal concrete loader exercising the shared batch APIs."""


@pytest.fixture
def loader(neo4j_client):
    loader = RoundTripLoader(neo4j_client)
    yield loader
    with neo4j_client.session() as session:
        session.run(f"MATCH (n:{AWARD_LABEL}) DETACH DELETE n")
        session.run(f"MATCH (n:{ORG_LABEL}) DETACH DELETE n")


def _awards(count: int = 12) -> list[dict]:
    return [
        {"award_id": f"RT-AWD-{i:03d}", "title": f"Round trip {i}", "amount": 100000 + i}
        for i in range(count)
    ]


def _orgs(count: int = 6) -> list[dict]:
    return [{"org_key": f"RT-ORG-{i:03d}", "name": f"Round Trip Org {i}"} for i in range(count)]


def _node_count(client, label: str) -> int:
    # Cypher cannot parameterize labels; constrain interpolation to this
    # module's dedicated test labels.
    assert label in {AWARD_LABEL, ORG_LABEL}
    with client.session() as session:
        return session.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()["c"]


def _rel_count(client) -> int:
    with client.session() as session:
        query = f"MATCH (:{AWARD_LABEL})-[r:{REL_TYPE}]->(:{ORG_LABEL}) RETURN count(r) AS c"
        return session.run(query).single()["c"]


def test_load_query_reload_is_idempotent(neo4j_client, loader):
    awards, orgs = _awards(), _orgs()
    relationships = [
        (award["award_id"], orgs[i % len(orgs)]["org_key"], {"amount": award["amount"]})
        for i, award in enumerate(awards)
    ]

    def load_once():
        loader.batch_upsert_nodes(AWARD_LABEL, "award_id", awards)
        loader.batch_upsert_nodes(ORG_LABEL, "org_key", orgs)
        loader.batch_create_relationships(
            source_label=AWARD_LABEL,
            source_key="award_id",
            target_label=ORG_LABEL,
            target_key="org_key",
            rel_type=REL_TYPE,
            relationships=relationships,
        )

    load_once()
    assert _node_count(neo4j_client, AWARD_LABEL) == len(awards)
    assert _node_count(neo4j_client, ORG_LABEL) == len(orgs)
    assert _rel_count(neo4j_client) == len(awards)

    # The identical batch again: MERGE semantics mean nothing multiplies.
    load_once()
    assert _node_count(neo4j_client, AWARD_LABEL) == len(awards)
    assert _node_count(neo4j_client, ORG_LABEL) == len(orgs)
    assert _rel_count(neo4j_client) == len(awards)

    # Every loaded row is readable back with its properties intact.
    with neo4j_client.session() as session:
        rows = session.run(
            f"MATCH (a:{AWARD_LABEL}) RETURN a.award_id AS id, a.amount AS amount ORDER BY id"
        ).data()
    assert [row["id"] for row in rows] == [award["award_id"] for award in awards]
    assert rows[0]["amount"] == awards[0]["amount"]


def test_reupsert_updates_properties_in_place(neo4j_client, loader):
    award = {"award_id": "RT-AWD-UPD", "title": "Before", "amount": 1}
    loader.batch_upsert_nodes(AWARD_LABEL, "award_id", [award])

    updated = dict(award, title="After", amount=2)
    loader.batch_upsert_nodes(AWARD_LABEL, "award_id", [updated])

    assert _node_count(neo4j_client, AWARD_LABEL) == 1
    with neo4j_client.session() as session:
        row = session.run(
            f"MATCH (a:{AWARD_LABEL} {{award_id: 'RT-AWD-UPD'}}) "
            "RETURN a.title AS title, a.amount AS amount"
        ).single()
    assert row["title"] == "After"
    assert row["amount"] == 2
