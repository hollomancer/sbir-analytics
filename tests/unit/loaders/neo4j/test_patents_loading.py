"""Tests for the data-loading methods of the Neo4j PatentLoader.

Schema-management methods (create_constraints/create_indexes) are already
covered in tests/unit/loaders/neo4j/test_patents.py; this file focuses on the
node/relationship batch-loading logic (Phases 1-5).
"""

from datetime import date
from unittest.mock import MagicMock

import pytest

from sbir_graph.loaders.neo4j.client import LoadMetrics
from sbir_graph.loaders.neo4j.patents import PatentLoader


pytestmark = pytest.mark.fast


def _mock_client_with_node_capture():
    """Mock Neo4jClient capturing batch_upsert_nodes calls, matching the
    CETLoader test convention (tests/unit/test_cet_loader.py)."""
    captured: dict = {}
    mock_client = MagicMock()

    def _fake_batch_upsert_nodes(label, key_property, nodes, metrics=None):
        captured.setdefault("calls", []).append(
            {"label": label, "key_property": key_property, "nodes": nodes}
        )
        m = metrics or LoadMetrics()
        m.nodes_created[label] = m.nodes_created.get(label, 0) + len(nodes)
        return m

    mock_client.batch_upsert_nodes.side_effect = _fake_batch_upsert_nodes
    return mock_client, captured


def _mock_client_with_rel_capture():
    """Mock Neo4jClient capturing batch_create_relationships calls."""
    captured: dict = {}
    mock_client = MagicMock()

    def _fake_batch_create_relationships(relationships, metrics=None):
        captured["relationships"] = relationships
        m = metrics or LoadMetrics()
        for rel in relationships:
            rel_type = rel[6]
            m.relationships_created[rel_type] = m.relationships_created.get(rel_type, 0) + 1
        return m

    mock_client.batch_create_relationships.side_effect = _fake_batch_create_relationships
    return mock_client, captured


class TestLoadPatents:
    def test_valid_patent_builds_node_with_iso_dates(self):
        mock_client, captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.load_patents(
            [
                {
                    "grant_doc_num": "US1234567",
                    "title": "Widget",
                    "abstract": "An abstract.",
                    "language": "en",
                    "appno_date": date(2020, 1, 1),
                    "grant_date": "2022-01-01",  # already a string, passed through
                }
            ]
        )

        call = captured["calls"][0]
        assert call["label"] == "Patent"
        assert call["key_property"] == "grant_doc_num"
        node = call["nodes"][0]
        assert node["grant_doc_num"] == "US1234567"
        assert node["appno_date"] == "2020-01-01"
        assert node["grant_date"] == "2022-01-01"
        assert isinstance(metrics, LoadMetrics)
        assert metrics.nodes_created["Patent"] == 1

    def test_missing_grant_doc_num_skipped_as_error(self):
        mock_client, captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.load_patents([{"title": "No key"}])

        assert metrics.errors == 1
        # Unlike the categorization/organizations loaders, load_patents calls
        # batch_upsert_nodes unconditionally (even with an empty node list).
        assert captured["calls"][0]["nodes"] == []

    def test_empty_input_returns_without_client_call(self):
        mock_client, _captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.load_patents([])

        assert isinstance(metrics, LoadMetrics)
        mock_client.batch_upsert_nodes.assert_not_called()

    def test_language_defaults_to_en(self):
        mock_client, captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        loader.load_patents([{"grant_doc_num": "US1"}])

        assert captured["calls"][0]["nodes"][0]["language"] == "en"


class TestLoadPatentAssignments:
    def test_valid_assignment_builds_node(self):
        mock_client, captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.load_patent_assignments(
            [
                {
                    "rf_id": "RF001",
                    "file_id": "F1",
                    "conveyance_type": "assignment",
                    "employer_assign": True,
                    "grant_doc_num": "US1234567",
                    "execution_date": date(2021, 6, 1),
                }
            ]
        )

        call = captured["calls"][0]
        assert call["label"] == "PatentAssignment"
        assert call["key_property"] == "rf_id"
        node = call["nodes"][0]
        assert node["rf_id"] == "RF001"
        assert node["employer_assign"] is True
        assert node["execution_date"] == "2021-06-01"
        assert metrics.nodes_created["PatentAssignment"] == 1

    def test_missing_rf_id_skipped_as_error(self):
        mock_client, captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.load_patent_assignments([{"file_id": "F1"}])

        assert metrics.errors == 1
        # batch_upsert_nodes is called unconditionally, even with no nodes.
        assert captured["calls"][0]["nodes"] == []

    def test_empty_input_returns_without_client_call(self):
        mock_client, _captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.load_patent_assignments([])

        assert isinstance(metrics, LoadMetrics)
        mock_client.batch_upsert_nodes.assert_not_called()

    def test_conveyance_type_defaults_and_employer_assign_coerced(self):
        mock_client, captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        loader.load_patent_assignments([{"rf_id": "RF002"}])

        node = captured["calls"][0]["nodes"][0]
        assert node["conveyance_type"] == "assignment"
        assert node["employer_assign"] is False


class TestLoadPatentEntities:
    def test_company_entity_becomes_organization_node(self):
        mock_client, captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.load_patent_entities(
            [
                {
                    "entity_id": "E1",
                    "name": "Acme Corp",
                    "entity_category": "COMPANY",
                    "uei": "ABC123",
                    "city": "Boston",
                }
            ],
            entity_type="ASSIGNEE",
        )

        org_call = next(c for c in captured["calls"] if c["label"] == "Organization")
        node = org_call["nodes"][0]
        assert node["organization_id"] == "org_patent_E1"
        assert node["organization_type"] == "COMPANY"
        assert node["entity_id"] == "E1"
        assert node["uei"] == "ABC123"
        assert node["name"] == "Acme Corp"
        assert metrics.nodes_created["Organization"] == 1

    def test_individual_entity_becomes_individual_node(self):
        mock_client, captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        loader.load_patent_entities(
            [
                {
                    "entity_id": "E2",
                    "name": "Jane Doe",
                    "entity_category": "INDIVIDUAL",
                }
            ],
            entity_type="ASSIGNOR",
        )

        ind_call = next(c for c in captured["calls"] if c["label"] == "Individual")
        node = ind_call["nodes"][0]
        assert node["individual_id"] == "ind_patent_E2"
        assert node["individual_type"] == "PATENT_ASSIGNOR"
        assert node["entity_id"] == "E2"
        assert "Organization" not in [c["label"] for c in captured["calls"]]

    def test_mixed_entities_produce_both_labels(self):
        mock_client, captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        loader.load_patent_entities(
            [
                {"entity_id": "E1", "name": "Acme Corp", "entity_category": "COMPANY"},
                {"entity_id": "E2", "name": "Jane Doe", "entity_category": "INDIVIDUAL"},
            ],
            entity_type="ASSIGNEE",
        )

        labels = {c["label"] for c in captured["calls"]}
        assert labels == {"Organization", "Individual"}

    def test_missing_entity_id_or_name_skipped_as_error(self):
        mock_client, captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.load_patent_entities(
            [{"entity_id": "E1"}, {"name": "No ID"}],
            entity_type="ASSIGNEE",
        )

        assert metrics.errors == 2
        assert "calls" not in captured

    def test_unrecognized_entity_category_defaults_to_company(self):
        mock_client, captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        loader.load_patent_entities(
            [{"entity_id": "E1", "name": "Weird Org", "entity_category": "WEIRD"}],
            entity_type="ASSIGNEE",
        )

        node = captured["calls"][0]["nodes"][0]
        assert node["organization_type"] == "COMPANY"

    def test_none_valued_optional_props_stripped(self):
        mock_client, captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        loader.load_patent_entities(
            [{"entity_id": "E1", "name": "Acme Corp", "entity_category": "COMPANY"}],
            entity_type="ASSIGNEE",
        )

        node = captured["calls"][0]["nodes"][0]
        assert "uei" not in node
        assert "cage" not in node

    def test_empty_input_returns_without_client_call(self):
        mock_client, _captured = _mock_client_with_node_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.load_patent_entities([], entity_type="ASSIGNEE")

        assert isinstance(metrics, LoadMetrics)
        mock_client.batch_upsert_nodes.assert_not_called()


class TestCreateAssignedViaRelationships:
    def test_valid_pair_creates_relationship(self):
        mock_client, captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_assigned_via_relationships(
            [{"grant_doc_num": "US1", "rf_id": "RF1"}]
        )

        rel = captured["relationships"][0]
        assert rel[0] == "Patent"
        assert rel[3] == "PatentAssignment"
        assert rel[6] == "ASSIGNED_VIA"
        assert metrics.relationships_created["ASSIGNED_VIA"] == 1

    def test_missing_keys_skipped_as_error(self):
        mock_client, captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_assigned_via_relationships([{"grant_doc_num": "US1"}])

        assert metrics.errors == 1
        # batch_create_relationships is called unconditionally, even with an
        # empty relationship list.
        assert captured["relationships"] == []

    def test_empty_input_returns_without_client_call(self):
        mock_client, _captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_assigned_via_relationships([])

        assert isinstance(metrics, LoadMetrics)
        mock_client.batch_create_relationships.assert_not_called()


class TestCreateAssignedFromRelationships:
    def test_creates_two_candidate_relationships_per_pair(self):
        mock_client, captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_assigned_from_relationships(
            [{"rf_id": "RF1", "assignor_entity_id": "E1", "execution_date": date(2021, 1, 1)}]
        )

        rels = captured["relationships"]
        # One candidate targets Organization, one targets Individual; only
        # the one matching an existing node is materialized by Neo4j.
        assert len(rels) == 2
        targets = {rel[3] for rel in rels}
        assert targets == {"Organization", "Individual"}
        assert rels[0][7]["execution_date"] == "2021-01-01"
        assert metrics.relationships_created["ASSIGNED_FROM"] == 2

    def test_missing_keys_skipped_as_error(self):
        mock_client, captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_assigned_from_relationships([{"rf_id": "RF1"}])

        assert metrics.errors == 1
        assert captured["relationships"] == []

    def test_no_execution_date_omits_props(self):
        mock_client, captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        loader.create_assigned_from_relationships([{"rf_id": "RF1", "assignor_entity_id": "E1"}])

        assert captured["relationships"][0][7] == {}


class TestCreateAssignedToRelationships:
    def test_creates_two_candidate_relationships_per_pair(self):
        mock_client, captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_assigned_to_relationships(
            [{"rf_id": "RF1", "assignee_entity_id": "E1", "recorded_date": "2022-05-05"}]
        )

        rels = captured["relationships"]
        assert len(rels) == 2
        assert rels[0][7]["recorded_date"] == "2022-05-05"
        assert metrics.relationships_created["ASSIGNED_TO"] == 2

    def test_missing_keys_skipped_as_error(self):
        mock_client, captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_assigned_to_relationships([{"rf_id": "RF1"}])

        assert metrics.errors == 1
        assert captured["relationships"] == []


class TestCreateGeneratedFromRelationships:
    def test_valid_pair_creates_relationship(self):
        mock_client, captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_generated_from_relationships(
            [{"grant_doc_num": "US1", "award_id": "AWARD-1"}]
        )

        rel = captured["relationships"][0]
        assert rel[3] == "FinancialTransaction"
        assert rel[6] == "GENERATED_FROM"
        assert metrics.relationships_created["GENERATED_FROM"] == 1

    def test_missing_keys_skipped_as_error(self):
        mock_client, captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_generated_from_relationships([{"grant_doc_num": "US1"}])

        assert metrics.errors == 1
        assert captured["relationships"] == []

    def test_empty_input_returns_without_client_call(self):
        mock_client, _captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_generated_from_relationships([])

        assert isinstance(metrics, LoadMetrics)
        mock_client.batch_create_relationships.assert_not_called()


class TestCreateOwnsRelationships:
    def test_valid_pair_creates_relationship(self):
        mock_client, captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_owns_relationships([{"uei": "ABC123", "grant_doc_num": "US1"}])

        rel = captured["relationships"][0]
        assert rel[0] == "Organization"
        assert rel[3] == "Patent"
        assert rel[6] == "OWNS"
        assert metrics.relationships_created["OWNS"] == 1

    def test_missing_keys_skipped_as_error(self):
        mock_client, captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_owns_relationships([{"uei": "ABC123"}])

        assert metrics.errors == 1
        assert captured["relationships"] == []


class TestCreateChainOfRelationships:
    def test_valid_pair_creates_relationship(self):
        mock_client, captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_chain_of_relationships(
            [{"current_rf_id": "RF2", "previous_rf_id": "RF1"}]
        )

        rel = captured["relationships"][0]
        assert rel[0] == "PatentAssignment"
        assert rel[2] == "RF2"
        assert rel[5] == "RF1"
        assert rel[6] == "CHAIN_OF"
        assert metrics.relationships_created["CHAIN_OF"] == 1

    def test_missing_keys_skipped_as_error(self):
        mock_client, captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_chain_of_relationships([{"current_rf_id": "RF2"}])

        assert metrics.errors == 1
        assert captured["relationships"] == []

    def test_empty_input_returns_without_client_call(self):
        mock_client, _captured = _mock_client_with_rel_capture()
        loader = PatentLoader(mock_client)

        metrics = loader.create_chain_of_relationships([])

        assert isinstance(metrics, LoadMetrics)
        mock_client.batch_create_relationships.assert_not_called()
