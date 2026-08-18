"""Tests for Neo4j company categorization loader."""

from unittest.mock import MagicMock

import pytest

from sbir_graph.loaders.neo4j.categorization import (
    CompanyCategorizationLoader,
    CompanyCategorizationLoaderConfig,
    _as_float,
    _as_int,
    _as_str,
)
from sbir_graph.loaders.neo4j.client import LoadMetrics
from tests.mocks import Neo4jMocks


pytestmark = pytest.mark.fast


def _create_mock_client_with_session(mock_session: MagicMock = None) -> MagicMock:
    """Mock Neo4jClient with a session context manager, matching the sibling
    loader test convention (see tests/unit/loaders/neo4j/test_cet.py)."""
    if mock_session is None:
        mock_session = Neo4jMocks.session()

    mock_client = MagicMock()
    mock_client.config.batch_size = 1000
    mock_context = Neo4jMocks.session()
    mock_context.__enter__.return_value = mock_session
    mock_context.__exit__.return_value = None
    mock_client.session.return_value = mock_context
    return mock_client


def _create_mock_client_with_capture():
    """Mock Neo4jClient capturing batch_set_existing_node_properties calls,
    matching the CETLoader test convention (tests/unit/test_cet_loader.py)."""
    captured: dict = {}
    mock_client = MagicMock()
    mock_client.config.batch_size = 1000

    def _fake_batch_set_existing_node_properties(label, key_property, nodes, metrics=None):
        captured["label"] = label
        captured["key_property"] = key_property
        captured["nodes"] = nodes
        m = metrics or LoadMetrics()
        m.nodes_updated[label] = m.nodes_updated.get(label, 0) + len(nodes)
        return m

    mock_client.batch_set_existing_node_properties.side_effect = (
        _fake_batch_set_existing_node_properties
    )
    return mock_client, captured


class TestHelperFunctions:
    """Tests for the module-level coercion helpers."""

    @pytest.mark.parametrize(
        "value,expected",
        [(None, None), ("", None), ("abc", "abc"), (123, "123")],
    )
    def test_as_str(self, value, expected):
        assert _as_str(value) == expected

    @pytest.mark.parametrize(
        "value,expected",
        [(None, None), ("", None), ("42", 42), (42, 42), ("not-a-number", None)],
    )
    def test_as_int(self, value, expected):
        assert _as_int(value) == expected

    @pytest.mark.parametrize(
        "value,expected",
        [(None, None), ("", None), ("3.5", 3.5), (3.5, 3.5), ("not-a-number", None)],
    )
    def test_as_float(self, value, expected):
        assert _as_float(value) == expected


class TestCompanyCategorizationLoaderConfig:
    def test_default_config(self):
        config = CompanyCategorizationLoaderConfig()
        assert config.batch_size == 1000
        assert config.create_indexes is True
        assert config.create_constraints is True

    def test_custom_config(self):
        config = CompanyCategorizationLoaderConfig(batch_size=250)
        assert config.batch_size == 250


class TestCompanyCategorizationLoaderInit:
    def test_initialization_with_default_config(self):
        mock_client = _create_mock_client_with_session()
        loader = CompanyCategorizationLoader(mock_client)

        assert loader.client == mock_client
        assert isinstance(loader.config, CompanyCategorizationLoaderConfig)
        assert loader.config.batch_size == 1000

    def test_initialization_with_custom_config(self):
        mock_client = _create_mock_client_with_session()
        config = CompanyCategorizationLoaderConfig(batch_size=50)
        loader = CompanyCategorizationLoader(mock_client, config)

        assert loader.config.batch_size == 50


class TestCompanyCategorizationLoaderIndexes:
    def test_create_indexes_executes_all(self):
        mock_session = Neo4jMocks.session()
        mock_client = _create_mock_client_with_session(mock_session)

        loader = CompanyCategorizationLoader(mock_client)
        loader.create_indexes()

        # 3 indexes: classification, confidence, composite
        assert mock_session.run.call_count == 3

    def test_create_indexes_cover_classification_and_confidence(self):
        mock_session = Neo4jMocks.session()
        mock_client = _create_mock_client_with_session(mock_session)

        loader = CompanyCategorizationLoader(mock_client)
        loader.create_indexes()

        all_queries = " ".join(call[0][0] for call in mock_session.run.call_args_list)
        assert "o.classification" in all_queries
        assert "o.categorization_confidence" in all_queries

    def test_create_indexes_custom_list(self):
        mock_session = Neo4jMocks.session()
        mock_client = _create_mock_client_with_session(mock_session)

        loader = CompanyCategorizationLoader(mock_client)
        loader.create_indexes(["CREATE INDEX foo IF NOT EXISTS FOR (o:Organization) ON (o.foo)"])

        assert mock_session.run.call_count == 1


class TestLoadCategorizations:
    def test_valid_categorization_updates_organization(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = CompanyCategorizationLoader(mock_client, CompanyCategorizationLoaderConfig())

        categorizations = [
            {
                "company_uei": "ABC123",
                "classification": "Product-leaning",
                "product_pct": 80.5,
                "service_pct": 19.5,
                "confidence": "High",
                "award_count": 10,
                "psc_family_count": 3,
                "total_dollars": 500000,
                "product_dollars": 400000,
                "service_dollars": 100000,
                "agency_breakdown": {"DoD": 0.6, "NASA": 0.4},
                "override_reason": "Manual review",
            }
        ]

        metrics = loader.load_categorizations(categorizations)

        assert captured["label"] == "Organization"
        assert captured["key_property"] == "uei"
        node = captured["nodes"][0]
        assert node["uei"] == "ABC123"
        assert node["classification"] == "Product-leaning"
        assert node["product_pct"] == 80.5
        assert node["categorization_confidence"] == "High"
        assert node["categorization_award_count"] == 10
        assert node["categorization_psc_family_count"] == 3
        assert node["categorization_total_dollars"] == 500000.0
        assert node["categorization_product_dollars"] == 400000.0
        assert node["categorization_service_dollars"] == 100000.0
        assert node["categorization_agency_breakdown"] == {"DoD": 0.6, "NASA": 0.4}
        assert node["categorization_override_reason"] == "Manual review"
        assert "categorization_updated_at" in node
        assert isinstance(metrics, LoadMetrics)
        assert metrics.nodes_updated["Organization"] == 1

    def test_missing_uei_skipped_as_error(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = CompanyCategorizationLoader(mock_client)

        metrics = loader.load_categorizations([{"classification": "Mixed", "confidence": "Low"}])

        assert metrics.errors == 1
        assert "nodes" not in captured  # client never called

    def test_missing_classification_or_confidence_skipped(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = CompanyCategorizationLoader(mock_client)

        metrics = loader.load_categorizations(
            [
                {"company_uei": "ABC123", "classification": "Mixed"},  # missing confidence
                {"company_uei": "DEF456", "confidence": "Low"},  # missing classification
            ]
        )

        assert metrics.errors == 2
        assert "nodes" not in captured

    def test_optional_fields_omitted_when_absent(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = CompanyCategorizationLoader(mock_client)

        loader.load_categorizations(
            [
                {
                    "company_uei": "ABC123",
                    "classification": "Uncertain",
                    "confidence": "Low",
                    "award_count": 1,
                }
            ]
        )

        node = captured["nodes"][0]
        assert "categorization_psc_family_count" not in node
        assert "categorization_total_dollars" not in node
        assert "categorization_agency_breakdown" not in node
        assert "categorization_override_reason" not in node

    def test_agency_breakdown_non_dict_ignored(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = CompanyCategorizationLoader(mock_client)

        loader.load_categorizations(
            [
                {
                    "company_uei": "ABC123",
                    "classification": "Mixed",
                    "confidence": "Medium",
                    "agency_breakdown": "not-a-dict",
                }
            ]
        )

        node = captured["nodes"][0]
        assert "categorization_agency_breakdown" not in node

    def test_empty_input_returns_metrics_without_client_call(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = CompanyCategorizationLoader(mock_client)

        metrics = loader.load_categorizations([])

        assert isinstance(metrics, LoadMetrics)
        assert metrics.errors == 0
        mock_client.batch_set_existing_node_properties.assert_not_called()

    def test_all_invalid_records_returns_without_client_call(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = CompanyCategorizationLoader(mock_client)

        metrics = loader.load_categorizations([{"foo": "bar"}])

        assert metrics.errors == 1
        mock_client.batch_set_existing_node_properties.assert_not_called()

    def test_batch_size_applied_to_client_config(self):
        mock_client, _captured = _create_mock_client_with_capture()
        loader = CompanyCategorizationLoader(
            mock_client, CompanyCategorizationLoaderConfig(batch_size=42)
        )

        loader.load_categorizations(
            [{"company_uei": "ABC123", "classification": "Mixed", "confidence": "Low"}]
        )

        assert mock_client.config.batch_size == 42

    def test_accumulates_into_provided_metrics(self):
        mock_client, _captured = _create_mock_client_with_capture()
        loader = CompanyCategorizationLoader(mock_client)
        existing_metrics = LoadMetrics(errors=5)

        metrics = loader.load_categorizations(
            [{"company_uei": "ABC123", "classification": "Mixed", "confidence": "Low"}],
            metrics=existing_metrics,
        )

        assert metrics is existing_metrics
        assert metrics.errors == 5
        assert metrics.nodes_updated["Organization"] == 1
