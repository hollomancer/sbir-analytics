"""Tests for Neo4j Organization-to-Organization relationship loader."""

from unittest.mock import MagicMock

import pytest

from sbir_graph.loaders.neo4j.client import LoadMetrics
from sbir_graph.loaders.neo4j.organizations import OrganizationLoader


pytestmark = pytest.mark.fast


def _create_mock_client_with_capture():
    """Mock Neo4jClient capturing batch_create_relationships calls, matching
    the CETLoader test convention (tests/unit/test_cet_loader.py)."""
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


class TestCreateSubsidiaryRelationships:
    def test_creates_relationship_for_valid_pair(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = OrganizationLoader(mock_client)

        metrics = loader.create_subsidiary_relationships(
            [("uei", "CHILD-UEI", "uei", "PARENT-UEI")],
            source="CONTRACT_PARENT_UEI",
        )

        assert isinstance(metrics, LoadMetrics)
        assert metrics.relationships_created["SUBSIDIARY_OF"] == 1

        rels = captured["relationships"]
        assert len(rels) == 1
        (
            source_label,
            source_key,
            source_val,
            target_label,
            target_key,
            target_val,
            rel_type,
            props,
        ) = rels[0]
        assert source_label == "Organization"
        assert source_key == "uei"
        assert source_val == "CHILD-UEI"
        assert target_label == "Organization"
        assert target_key == "uei"
        assert target_val == "PARENT-UEI"
        assert rel_type == "SUBSIDIARY_OF"
        assert props["source"] == "CONTRACT_PARENT_UEI"
        assert "created_at" in props

    def test_different_keys_for_child_and_parent(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = OrganizationLoader(mock_client)

        loader.create_subsidiary_relationships(
            [("organization_id", "ORG-001", "uei", "PARENT-UEI")],
        )

        rels = captured["relationships"]
        assert rels[0][1] == "organization_id"
        assert rels[0][2] == "ORG-001"
        assert rels[0][4] == "uei"
        assert rels[0][5] == "PARENT-UEI"

    def test_default_source_is_unknown(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = OrganizationLoader(mock_client)

        loader.create_subsidiary_relationships([("uei", "CHILD", "uei", "PARENT")])

        assert captured["relationships"][0][7]["source"] == "UNKNOWN"

    def test_values_are_stripped(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = OrganizationLoader(mock_client)

        loader.create_subsidiary_relationships([("uei", "  CHILD  ", "uei", "  PARENT  ")])

        rels = captured["relationships"]
        assert rels[0][2] == "CHILD"
        assert rels[0][5] == "PARENT"

    def test_missing_child_value_skipped_as_error(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = OrganizationLoader(mock_client)

        metrics = loader.create_subsidiary_relationships([("uei", "", "uei", "PARENT")])

        assert metrics.errors == 1
        assert "relationships" not in captured

    def test_missing_parent_value_skipped_as_error(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = OrganizationLoader(mock_client)

        metrics = loader.create_subsidiary_relationships([("uei", "CHILD", "uei", None)])

        assert metrics.errors == 1
        assert "relationships" not in captured

    def test_mixed_valid_and_invalid_pairs(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = OrganizationLoader(mock_client)

        metrics = loader.create_subsidiary_relationships(
            [
                ("uei", "CHILD-1", "uei", "PARENT-1"),
                ("uei", "", "uei", "PARENT-2"),  # invalid, missing child
                ("uei", "CHILD-3", "uei", "PARENT-3"),
            ]
        )

        assert metrics.errors == 1
        rels = captured["relationships"]
        assert len(rels) == 2
        assert rels[0][2] == "CHILD-1"
        assert rels[0][5] == "PARENT-1"
        assert rels[1][2] == "CHILD-3"
        assert rels[1][5] == "PARENT-3"

    def test_empty_input_returns_metrics_without_client_call(self):
        mock_client, _captured = _create_mock_client_with_capture()
        loader = OrganizationLoader(mock_client)

        metrics = loader.create_subsidiary_relationships([])

        assert isinstance(metrics, LoadMetrics)
        assert metrics.errors == 0
        mock_client.batch_create_relationships.assert_not_called()

    def test_all_invalid_pairs_returns_without_client_call(self):
        mock_client, _captured = _create_mock_client_with_capture()
        loader = OrganizationLoader(mock_client)

        metrics = loader.create_subsidiary_relationships([("uei", None, "uei", None)])

        assert metrics.errors == 1
        mock_client.batch_create_relationships.assert_not_called()
