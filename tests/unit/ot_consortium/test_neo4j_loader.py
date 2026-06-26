"""Neo4j OT consortium loader: PERFORMED_BY must exist ONLY for T1.

Uses a recording fake client so the test needs no live Neo4j.
"""

import pandas as pd
import pytest

pytestmark = pytest.mark.fast

# sbir-graph is an optional workspace package; skip cleanly if unavailable.
sbir_graph = pytest.importorskip("sbir_graph.loaders.neo4j.ot_consortium")
OTConsortiumLoader = sbir_graph.OTConsortiumLoader


class _Config:
    batch_size = 1000


class _FakeMetrics:
    def __init__(self):
        self.nodes_created: dict = {}
        self.nodes_updated: dict = {}
        self.relationships_created: dict = {}
        self.errors = 0


class _FakeClient:
    """Records node/relationship calls instead of talking to Neo4j."""

    def __init__(self):
        self.config = _Config()
        self.nodes: dict[str, list] = {}
        self.rels: dict[str, list] = {}

    def batch_upsert_nodes(self, label, key_property, nodes, metrics):
        self.nodes.setdefault(label, []).extend(nodes)
        return metrics

    def batch_create_relationships(self, relationships, metrics):
        for full in relationships:
            rel_type = full[6]
            self.rels.setdefault(rel_type, []).append(full)
        return metrics


@pytest.fixture
def loaded():
    client = _FakeClient()
    loader = OTConsortiumLoader(client)
    df = pd.DataFrame(
        [
            {
                "award_id": "ORDER-T1",
                "tier": "T1_member_confirmed",
                "piid": "P1",
                "parent_piid": "BASE-1",
                "cmf_name": "Advanced Technology International",
                "firm_uei": "FIRMUEI000001",
                "obligation_amount": 100.0,
                "agency": "Navy",
                "fiscal_year": 2023,
                "confidence_note": "ok",
            },
            {
                "award_id": "ORDER-T2",
                "tier": "T2_rollup_only",
                "piid": None,
                "parent_piid": "BASE-1",
                "cmf_name": "NSTXL",
                "firm_uei": "SHOULDNOTLINK",  # T2 must NOT get a PERFORMED_BY edge
                "obligation_amount": 9000.0,
                "agency": "Navy",
                "fiscal_year": 2023,
                "confidence_note": "rollup",
            },
        ]
    )
    count = loader.load_tier_assignments(df)
    return client, count


def test_loads_all_project_nodes(loaded):
    client, count = loaded
    assert count == 2
    award_ids = {n["award_id"] for n in client.nodes["ProjectOT"]}
    assert award_ids == {"ORDER-T1", "ORDER-T2"}


def test_performed_by_only_for_t1(loaded):
    client, _ = loaded
    performed_by = client.rels.get("PERFORMED_BY", [])
    # Exactly one edge, and it is the T1 order → its firm.
    assert len(performed_by) == 1
    full = performed_by[0]
    source_value, target_value = full[2], full[5]
    assert source_value == "ORDER-T1"
    assert target_value == "FIRMUEI000001"


def test_chain_relationships_present(loaded):
    client, _ = loaded
    assert "MANAGES" in client.rels  # CMF → BaseOT
    assert "HAS_ORDER" in client.rels  # BaseOT → ProjectOT


def test_empty_df_loads_nothing():
    client = _FakeClient()
    loader = OTConsortiumLoader(client)
    assert loader.load_tier_assignments(pd.DataFrame()) == 0
