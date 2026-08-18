"""Tests for Neo4j SEC EDGAR enrichment loader."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from sbir_graph.loaders.neo4j.client import LoadMetrics
from sbir_graph.loaders.neo4j.sec_edgar import SecEdgarLoader, SecEdgarLoaderConfig
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


class TestSecEdgarLoaderConfig:
    def test_default_config(self):
        config = SecEdgarLoaderConfig()
        assert config.batch_size == 1000
        assert config.create_indexes is True

    def test_custom_config(self):
        config = SecEdgarLoaderConfig(batch_size=200)
        assert config.batch_size == 200


class TestSecEdgarLoaderInit:
    def test_initialization_with_default_config(self):
        mock_client = _create_mock_client_with_session()
        loader = SecEdgarLoader(mock_client)

        assert loader.client == mock_client
        assert isinstance(loader.config, SecEdgarLoaderConfig)
        assert loader.config.batch_size == 1000

    def test_initialization_with_custom_config(self):
        mock_client = _create_mock_client_with_session()
        config = SecEdgarLoaderConfig(batch_size=77)
        loader = SecEdgarLoader(mock_client, config)

        assert loader.config.batch_size == 77


class TestSecEdgarLoaderIndexes:
    def test_create_indexes_executes_all(self):
        mock_session = Neo4jMocks.session()
        mock_client = _create_mock_client_with_session(mock_session)

        loader = SecEdgarLoader(mock_client)
        loader.create_indexes()

        # 3 indexes: cik, publicly_traded, ticker
        assert mock_session.run.call_count == 3

    def test_create_indexes_cover_key_properties(self):
        mock_session = Neo4jMocks.session()
        mock_client = _create_mock_client_with_session(mock_session)

        loader = SecEdgarLoader(mock_client)
        loader.create_indexes()

        all_queries = " ".join(call[0][0] for call in mock_session.run.call_args_list)
        assert "sec_cik" in all_queries
        assert "sec_is_publicly_traded" in all_queries
        assert "sec_ticker" in all_queries

    def test_create_indexes_custom_list(self):
        mock_session = Neo4jMocks.session()
        mock_client = _create_mock_client_with_session(mock_session)

        loader = SecEdgarLoader(mock_client)
        loader.create_indexes(["CREATE INDEX foo IF NOT EXISTS FOR (o:Organization) ON (o.foo)"])

        assert mock_session.run.call_count == 1


class TestLoadSecEdgarData:
    def test_publicly_traded_record_loaded(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        records = [
            {
                "company_uei": "ABC123",
                "sec_cik": "0001234567",
                "sec_is_publicly_traded": True,
                "sec_ticker": "ACME",
                "sec_match_confidence": 0.95,
                "sec_latest_revenue": 1_000_000.0,
            }
        ]

        metrics = loader.load_sec_edgar_data(records)

        assert isinstance(metrics, LoadMetrics)
        node = captured["nodes"][0]
        assert node["uei"] == "ABC123"
        assert node["sec_cik"] == "0001234567"
        assert node["sec_is_publicly_traded"] is True
        assert node["sec_ticker"] == "ACME"
        assert "sec_enriched_at" in node

    def test_record_matched_by_uei_fallback_key(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        loader.load_sec_edgar_data([{"uei": "XYZ999", "sec_cik": "0009999999"}])

        assert captured["nodes"][0]["uei"] == "XYZ999"

    def test_date_fields_converted_to_isoformat(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        loader.load_sec_edgar_data(
            [
                {
                    "company_uei": "ABC123",
                    "sec_cik": "0001234567",
                    "sec_financials_as_of": date(2025, 1, 1),
                }
            ]
        )

        node = captured["nodes"][0]
        assert node["sec_financials_as_of"] == "2025-01-01"

    def test_non_sec_prefixed_fields_are_not_copied(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        loader.load_sec_edgar_data(
            [{"company_uei": "ABC123", "sec_cik": "0001234567", "irrelevant_field": "ignored"}]
        )

        node = captured["nodes"][0]
        assert "irrelevant_field" not in node

    def test_none_valued_sec_fields_omitted(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        loader.load_sec_edgar_data(
            [{"company_uei": "ABC123", "sec_cik": "0001234567", "sec_ticker": None}]
        )

        node = captured["nodes"][0]
        assert "sec_ticker" not in node

    def test_record_missing_uei_counts_as_error_and_is_skipped(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        metrics = loader.load_sec_edgar_data([{"sec_cik": "0001234567"}])

        assert metrics.errors == 1
        assert "nodes" not in captured

    def test_empty_input_returns_metrics_without_client_call(self):
        mock_client, _captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        metrics = loader.load_sec_edgar_data([])

        assert isinstance(metrics, LoadMetrics)
        mock_client.batch_set_existing_node_properties.assert_not_called()

    def test_batch_size_applied_to_client_config(self):
        mock_client, _captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client, SecEdgarLoaderConfig(batch_size=17))

        loader.load_sec_edgar_data([{"company_uei": "ABC123", "sec_cik": "0001234567"}])

        assert mock_client.config.batch_size == 17

    def test_metrics_argument_replaces_loader_metrics(self):
        mock_client, _captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)
        existing_metrics = LoadMetrics(errors=3)

        metrics = loader.load_sec_edgar_data(
            [{"company_uei": "ABC123", "sec_cik": "0001234567"}],
            metrics=existing_metrics,
        )

        assert metrics is existing_metrics
        assert loader.metrics is existing_metrics
        assert metrics.errors == 3
        assert metrics.nodes_updated["Organization"] == 1


class TestHasSecSignalFiltering:
    """Tests for the `_has_sec_signal` inner-function filtering logic, exercised
    indirectly through load_sec_edgar_data since the helper is not exported."""

    def test_publicly_traded_flag_included(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        loader.load_sec_edgar_data([{"company_uei": "A1", "sec_is_publicly_traded": True}])

        assert len(captured["nodes"]) == 1

    def test_cik_present_included(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        loader.load_sec_edgar_data([{"company_uei": "A1", "sec_cik": "0001111111"}])

        assert len(captured["nodes"]) == 1

    def test_form_d_present_included(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        loader.load_sec_edgar_data([{"company_uei": "A1", "sec_has_form_d": True}])

        assert len(captured["nodes"]) == 1

    def test_mention_with_low_noise_included(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        loader.load_sec_edgar_data(
            [
                {
                    "company_uei": "A1",
                    "sec_mention_count": 3,
                    "sec_mention_noise_score": 1,
                }
            ]
        )

        assert len(captured["nodes"]) == 1

    def test_mention_with_high_noise_excluded(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        metrics = loader.load_sec_edgar_data(
            [
                {
                    "company_uei": "A1",
                    "sec_mention_count": 3,
                    "sec_mention_noise_score": 2,
                }
            ]
        )

        # Record filtered out before the uei/node-building step, so the batch
        # is empty and the client is never called (no error is recorded either
        # -- this is a "no signal" record, not an invalid one).
        assert "nodes" not in captured
        assert metrics.errors == 0

    def test_zero_mention_count_excluded(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        loader.load_sec_edgar_data([{"company_uei": "A1", "sec_mention_count": 0}])

        assert "nodes" not in captured

    def test_no_signal_at_all_excluded(self):
        mock_client, captured = _create_mock_client_with_capture()
        loader = SecEdgarLoader(mock_client)

        loader.load_sec_edgar_data([{"company_uei": "A1"}])

        assert "nodes" not in captured
