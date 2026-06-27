"""Tests for Neo4j Transition loader - orchestration and edge cases."""

from datetime import datetime
from unittest.mock import patch

import pandas as pd
import pytest

from sbir_graph.loaders.neo4j.transitions import TransitionLoader
from tests.mocks import Neo4jMocks
from tests.unit.loaders.conftest import create_mock_client_with_session

pytestmark = pytest.mark.fast


class TestTransitionLoaderOrchestration:
    """Tests for load_transitions orchestration method."""

    def test_load_transitions_calls_all_methods(self):
        """Test load_transitions calls all required methods."""
        mock_session = Neo4jMocks.session()
        mock_result = Neo4jMocks.result()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_client = create_mock_client_with_session(mock_session)

        loader = TransitionLoader(mock_client)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "award_id": ["a1"],
                "contract_id": ["c1"],
                "likelihood_score": [0.85],
                "confidence": ["high"],
                "signals": ["[]"],
                "evidence": ["{}"],
                "detected_at": [datetime.now()],
                "vendor_match_score": [0.9],
                "cet_area": [None],
            }
        )

        with (
            patch.object(loader, "ensure_indexes") as mock_ensure_indexes,
            patch.object(loader, "load_transition_nodes") as mock_load_nodes,
            patch.object(loader, "create_transitioned_to_relationships") as mock_transitioned,
            patch.object(loader, "create_resulted_in_relationships") as mock_resulted,
            patch.object(loader, "create_enabled_by_relationships") as mock_enabled,
            patch.object(loader, "create_involves_technology_relationships") as mock_involves,
        ):
            loader.load_transitions(df)

            mock_ensure_indexes.assert_called_once()
            mock_load_nodes.assert_called_once()
            mock_transitioned.assert_called_once()
            mock_resulted.assert_called_once()
            mock_enabled.assert_called_once()
            mock_involves.assert_called_once()

    def test_load_transitions_with_patent_transitions(self):
        """Test load_transitions passes patent_transitions_df."""
        mock_client = Neo4jMocks.driver()
        loader = TransitionLoader(mock_client)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "award_id": ["a1"],
                "contract_id": ["c1"],
                "likelihood_score": [0.85],
                "confidence": ["high"],
                "signals": ["[]"],
                "evidence": ["{}"],
                "detected_at": [datetime.now()],
                "vendor_match_score": [0.9],
                "cet_area": [None],
            }
        )

        patent_df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "patent_id": ["p1"],
            }
        )

        with (
            patch.object(loader, "ensure_indexes"),
            patch.object(loader, "load_transition_nodes"),
            patch.object(loader, "create_transitioned_to_relationships"),
            patch.object(loader, "create_resulted_in_relationships"),
            patch.object(loader, "create_enabled_by_relationships") as mock_enabled,
            patch.object(loader, "create_involves_technology_relationships"),
        ):
            loader.load_transitions(df, patent_df)

            # Verify patent_df was passed
            mock_enabled.assert_called_once_with(df, patent_df)

    def test_load_transitions_returns_stats(self):
        """Test load_transitions returns stats dictionary."""
        mock_session = Neo4jMocks.session()
        mock_result = Neo4jMocks.result()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_client = create_mock_client_with_session(mock_session)

        loader = TransitionLoader(mock_client)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "award_id": ["a1"],
                "contract_id": ["c1"],
                "likelihood_score": [0.85],
                "confidence": ["high"],
                "signals": ["[]"],
                "evidence": ["{}"],
                "detected_at": [datetime.now()],
                "vendor_match_score": [0.9],
                "cet_area": [None],
            }
        )

        with (
            patch.object(loader, "ensure_indexes"),
            patch.object(loader, "load_transition_nodes"),
            patch.object(loader, "create_transitioned_to_relationships"),
            patch.object(loader, "create_resulted_in_relationships"),
            patch.object(loader, "create_enabled_by_relationships"),
            patch.object(loader, "create_involves_technology_relationships"),
        ):
            result = loader.load_transitions(df)

            assert isinstance(result, dict)
            assert "transitions_created" in result
            assert "relationships_created" in result


class TestTransitionLoaderEdgeCases:
    """Tests for edge cases in TransitionLoader."""

    def test_very_large_batch_size(self):
        """Test loader with very large batch size."""
        mock_client = Neo4jMocks.driver()
        mock_client.config.batch_size = 1000000
        loader = TransitionLoader(mock_client)

        assert loader.client.config.batch_size == 1000000

    def test_small_batch_size(self):
        """Test loader with small batch size."""
        mock_client = Neo4jMocks.driver()
        mock_client.config.batch_size = 1
        loader = TransitionLoader(mock_client)

        assert loader.client.config.batch_size == 1

    def test_stats_accumulate_across_calls(self):
        """Test stats accumulate across multiple calls."""
        mock_session = Neo4jMocks.session()
        mock_result = Neo4jMocks.result()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_client = create_mock_client_with_session(mock_session)

        loader = TransitionLoader(mock_client)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "award_id": ["a1"],
                "contract_id": ["c1"],
                "likelihood_score": [0.85],
                "confidence": ["high"],
                "signals": ["[]"],
                "evidence": ["{}"],
                "detected_at": [datetime.now()],
                "vendor_match_score": [0.9],
            }
        )

        # Load twice
        loader.load_transition_nodes(df)
        loader.load_transition_nodes(df)

        # Metrics should accumulate
        assert loader.metrics.nodes_created.get("Transition", 0) > 0

    def test_session_context_manager_used(self):
        """Test that session context manager is properly used."""
        mock_session = Neo4jMocks.session()
        mock_context = Neo4jMocks.session()
        mock_context.__enter__.return_value = mock_session
        mock_context.__exit__.return_value = None
        mock_client = Neo4jMocks.driver()
        mock_client.session.return_value = mock_context

        loader = TransitionLoader(mock_client)
        loader.ensure_indexes()

        # Should enter and exit context
        mock_context.__enter__.assert_called()
        mock_context.__exit__.assert_called()

    def test_multiple_index_creation_calls(self):
        """Test calling ensure_indexes multiple times."""
        mock_session = Neo4jMocks.session()
        mock_client = create_mock_client_with_session(mock_session)

        loader = TransitionLoader(mock_client)

        # Call multiple times
        loader.ensure_indexes()
        loader.ensure_indexes()

        # Should execute statements each time (idempotent with IF NOT EXISTS)
        assert mock_session.run.call_count == 8  # 4 indexes × 2 calls


class TestResultedInInlineContractNode:
    """RESULTED_IN must create the CONTRACT FinancialTransaction node inline."""

    def _loader_with_capture(self):
        mock_session = Neo4jMocks.session()
        mock_result = Neo4jMocks.result()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_client = create_mock_client_with_session(mock_session)
        return TransitionLoader(mock_client), mock_session

    def test_merges_contract_node_on_primary_key(self):
        """The writer MERGEs the CONTRACT node on its PK, never MATCHes contract_id."""
        loader, mock_session = self._loader_with_capture()

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "contract_id": ["c1"],
                "confidence": ["high"],
            }
        )

        created = loader.create_resulted_in_relationships(df)
        assert created == 1

        query = mock_session.run.call_args.args[0]
        # CONTRACT node is created inline, keyed on the transaction_id PK.
        assert "MERGE (ft:FinancialTransaction" in query
        assert "'txn_contract_' + t.contract_id" in query
        assert "ON CREATE SET ft.transaction_type = 'CONTRACT'" in query
        assert "MERGE (trans)-[r:RESULTED_IN]->(ft)" in query
        # Must NOT MATCH on the non-key contract_id (the old split-brain pattern).
        assert "MATCH (ft:FinancialTransaction {contract_id" not in query

    def test_skips_rows_without_contract_id(self):
        """Rows with a missing contract_id are skipped (no node minted for them)."""
        loader, mock_session = self._loader_with_capture()

        # contract_id is a PIID string in practice; one row has none.
        df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2"],
                "contract_id": ["W911NF20C0001", None],
                "confidence": ["high", "low"],
            }
        )

        loader.create_resulted_in_relationships(df)

        rows = mock_session.run.call_args.kwargs["transitions"]
        assert len(rows) == 1  # the None-contract_id row is dropped
        assert rows[0]["transition_id"] == "t1"
        assert rows[0]["contract_id"] == "W911NF20C0001"

    def test_strips_whitespace_from_contract_id(self):
        """The sent contract_id is stripped so the MERGE PK matches the filter."""
        loader, mock_session = self._loader_with_capture()

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "contract_id": ["  W911NF20C0001  "],
                "confidence": ["high"],
            }
        )

        loader.create_resulted_in_relationships(df)

        rows = mock_session.run.call_args.kwargs["transitions"]
        # Stripped value → stable txn_contract_<id> PK (no whitespace-duplicated nodes).
        assert rows[0]["contract_id"] == "W911NF20C0001"
