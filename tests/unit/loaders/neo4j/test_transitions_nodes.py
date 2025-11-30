"""Tests for TransitionLoader node loading methods.

Split from test_transitions.py for better organization.
"""

from datetime import datetime

import pandas as pd
import pytest

from src.loaders.neo4j.transitions import TransitionLoader
from tests.mocks import Neo4jMocks
from tests.unit.loaders.conftest import create_mock_client_with_session

pytestmark = pytest.mark.fast


class TestTransitionLoaderNodeLoading:
    """Tests for load_transition_nodes method."""

    def test_load_transition_nodes_empty_dataframe(self):
        """Test loading with empty DataFrame."""
        mock_client = Neo4jMocks.driver()
        loader = TransitionLoader(mock_client)

        df = pd.DataFrame()
        result = loader.load_transition_nodes(df)

        assert result == 0

    def test_load_transition_nodes_single_transition(self):
        """Test loading single transition node."""
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

        result = loader.load_transition_nodes(df)

        assert result == 1
        assert mock_session.run.call_count == 1

    def test_load_transition_nodes_multiple_transitions(self):
        """Test loading multiple transition nodes."""
        mock_session = Neo4jMocks.session()
        mock_result = Neo4jMocks.result()
        mock_result.single.return_value = {"created": 3}
        mock_session.run.return_value = mock_result
        mock_client = create_mock_client_with_session(mock_session)

        loader = TransitionLoader(mock_client)

        df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2", "t3"],
                "award_id": ["a1", "a2", "a3"],
                "contract_id": ["c1", "c2", "c3"],
                "likelihood_score": [0.85, 0.90, 0.75],
                "confidence": ["high", "high", "likely"],
                "signals": ["[]"] * 3,
                "evidence": ["{}"] * 3,
                "detected_at": [datetime.now()] * 3,
                "vendor_match_score": [0.9, 0.95, 0.8],
            }
        )

        result = loader.load_transition_nodes(df)

        assert result == 3

    def test_load_transition_nodes_batching(self):
        """Test nodes are loaded in batches."""
        mock_session = Neo4jMocks.session()
        mock_result = Neo4jMocks.result()
        mock_result.single.return_value = {"created": 5}
        mock_session.run.return_value = mock_result
        mock_client = create_mock_client_with_session(mock_session)
        mock_client.config.batch_size = 5

        loader = TransitionLoader(mock_client)

        df = pd.DataFrame(
            {
                "transition_id": [f"t{i}" for i in range(12)],
                "award_id": [f"a{i}" for i in range(12)],
                "contract_id": [f"c{i}" for i in range(12)],
                "likelihood_score": [0.85] * 12,
                "confidence": ["high"] * 12,
                "signals": ["[]"] * 12,
                "evidence": ["{}"] * 12,
                "detected_at": [datetime.now()] * 12,
                "vendor_match_score": [0.9] * 12,
            }
        )

        result = loader.load_transition_nodes(df)

        assert result == 12
        assert mock_session.run.call_count == 3

    def test_load_transition_nodes_query_uses_merge(self):
        """Test query uses MERGE for idempotency."""
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

        loader.load_transition_nodes(df)

        call_args = mock_session.run.call_args_list[0]
        query = call_args[0][0]

        assert "MERGE" in query
        assert "Transition" in query
        assert "transition_id" in query

    def test_load_transition_nodes_handles_errors(self):
        """Test error handling in node loading."""
        mock_session = Neo4jMocks.session()
        mock_session.run.side_effect = Exception("Database error")
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

        loader.load_transition_nodes(df)

        assert loader.metrics.errors > 0
