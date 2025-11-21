"""Tests for Neo4j Transition loader."""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from src.loaders.neo4j.transitions import TransitionLoader


pytestmark = pytest.mark.fast


class TestTransitionLoaderInitialization:
    """Tests for TransitionLoader initialization."""

    def test_initialization_with_default_batch_size(self):
        """Test TransitionLoader initialization with default batch size."""
        mock_driver = Mock()
        loader = TransitionLoader(mock_driver)

        assert loader.driver == mock_driver
        assert loader.batch_size == 1000
        assert loader.stats["transitions_created"] == 0
        assert loader.stats["transitions_updated"] == 0
        assert loader.stats["relationships_created"] == 0
        assert loader.stats["errors"] == 0

    def test_initialization_with_custom_batch_size(self):
        """Test TransitionLoader initialization with custom batch size."""
        mock_driver = Mock()
        loader = TransitionLoader(mock_driver, batch_size=500)

        assert loader.driver == mock_driver
        assert loader.batch_size == 500

    def test_stats_structure(self):
        """Test that stats dictionary has expected keys."""
        mock_driver = Mock()
        loader = TransitionLoader(mock_driver)

        assert "transitions_created" in loader.stats
        assert "transitions_updated" in loader.stats
        assert "relationships_created" in loader.stats
        assert "errors" in loader.stats

    def test_get_stats_returns_copy(self):
        """Test get_stats returns a copy of stats."""
        mock_driver = Mock()
        loader = TransitionLoader(mock_driver)

        stats1 = loader.get_stats()
        stats2 = loader.get_stats()

        assert stats1 == stats2
        assert stats1 is not stats2
        assert stats1 is not loader.stats


class TestTransitionLoaderIndexes:
    """Tests for index creation methods."""

    def test_ensure_indexes_creates_all(self):
        """Test ensure_indexes creates all expected indexes."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)
        loader.ensure_indexes()

        # Should create 4 indexes
        assert mock_session.run.call_count == 4

    def test_ensure_indexes_creates_transition_id_index(self):
        """Test transition_id index is created."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)
        loader.ensure_indexes()

        # Check first call is for transition_id
        first_call = mock_session.run.call_args_list[0]
        query = first_call[0][0]

        assert "transition_id_index" in query
        assert "Transition" in query
        assert "transition_id" in query

    def test_ensure_indexes_creates_confidence_index(self):
        """Test confidence index is created."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)
        loader.ensure_indexes()

        all_queries = " ".join([call[0][0] for call in mock_session.run.call_args_list])

        assert "transition_confidence_index" in all_queries
        assert "confidence" in all_queries

    def test_ensure_indexes_creates_score_index(self):
        """Test likelihood_score index is created."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)
        loader.ensure_indexes()

        all_queries = " ".join([call[0][0] for call in mock_session.run.call_args_list])

        assert "transition_score_index" in all_queries
        assert "likelihood_score" in all_queries

    def test_ensure_indexes_creates_date_index(self):
        """Test detection_date index is created."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)
        loader.ensure_indexes()

        all_queries = " ".join([call[0][0] for call in mock_session.run.call_args_list])

        assert "transition_date_index" in all_queries
        assert "detection_date" in all_queries

    def test_ensure_indexes_uses_if_not_exists(self):
        """Test all indexes use IF NOT EXISTS."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)
        loader.ensure_indexes()

        for call_args in mock_session.run.call_args_list:
            query = call_args[0][0]
            assert "IF NOT EXISTS" in query

    def test_ensure_indexes_handles_errors(self):
        """Test ensure_indexes raises on error."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Index creation failed")
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        with pytest.raises(Exception, match="Index creation failed"):
            loader.ensure_indexes()


class TestTransitionLoaderNodeLoading:
    """Tests for load_transition_nodes method."""

    def test_load_transition_nodes_empty_dataframe(self):
        """Test loading with empty DataFrame."""
        mock_driver = Mock()
        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame()
        result = loader.load_transition_nodes(df)

        assert result == 0
        assert loader.stats["transitions_created"] == 0

    def test_load_transition_nodes_single_transition(self):
        """Test loading single transition node."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

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
        assert loader.stats["transitions_created"] == 1
        assert mock_session.run.call_count == 1

    def test_load_transition_nodes_multiple_transitions(self):
        """Test loading multiple transition nodes."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 3}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

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
        assert loader.stats["transitions_created"] == 3

    def test_load_transition_nodes_batching(self):
        """Test nodes are loaded in batches."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 5}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver, batch_size=5)

        # Create 12 transitions (should create 3 batches)
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
        # Should call run 3 times (12 / 5 = 2.4, rounds to 3 batches)
        assert mock_session.run.call_count == 3

    def test_load_transition_nodes_query_uses_merge(self):
        """Test query uses MERGE for idempotency."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

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
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Database error")
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

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

        # Should not raise, but should track errors
        assert loader.stats["errors"] == 1


class TestTransitionLoaderTransitionedToRelationships:
    """Tests for create_transitioned_to_relationships method."""

    def test_create_transitioned_to_single(self):
        """Test creating single TRANSITIONED_TO relationship."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "award_id": ["a1"],
                "likelihood_score": [0.85],
                "confidence": ["high"],
                "detected_at": [datetime.now()],
                "evidence": ["{}"],
            }
        )

        result = loader.create_transitioned_to_relationships(df)

        assert result == 1
        assert loader.stats["relationships_created"] == 1

    def test_create_transitioned_to_multiple(self):
        """Test creating multiple TRANSITIONED_TO relationships."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 3}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2", "t3"],
                "award_id": ["a1", "a2", "a3"],
                "likelihood_score": [0.85, 0.90, 0.75],
                "confidence": ["high", "high", "likely"],
                "detected_at": [datetime.now()] * 3,
                "evidence": ["{}"] * 3,
            }
        )

        result = loader.create_transitioned_to_relationships(df)

        assert result == 3

    def test_create_transitioned_to_uses_merge(self):
        """Test query uses MERGE for idempotency."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "award_id": ["a1"],
                "likelihood_score": [0.85],
                "confidence": ["high"],
                "detected_at": [datetime.now()],
                "evidence": ["{}"],
            }
        )

        loader.create_transitioned_to_relationships(df)

        call_args = mock_session.run.call_args_list[0]
        query = call_args[0][0]

        assert "MERGE" in query
        assert "TRANSITIONED_TO" in query
        assert "Award" in query
        assert "Transition" in query

    def test_create_transitioned_to_handles_errors(self):
        """Test error handling in relationship creation."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Database error")
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "award_id": ["a1"],
                "likelihood_score": [0.85],
                "confidence": ["high"],
                "detected_at": [datetime.now()],
                "evidence": ["{}"],
            }
        )

        loader.create_transitioned_to_relationships(df)

        assert loader.stats["errors"] == 1


class TestTransitionLoaderResultedInRelationships:
    """Tests for create_resulted_in_relationships method."""

    def test_create_resulted_in_single(self):
        """Test creating single RESULTED_IN relationship."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "contract_id": ["c1"],
                "confidence": ["high"],
            }
        )

        result = loader.create_resulted_in_relationships(df)

        assert result == 1
        assert loader.stats["relationships_created"] == 1

    def test_create_resulted_in_multiple(self):
        """Test creating multiple RESULTED_IN relationships."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 3}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2", "t3"],
                "contract_id": ["c1", "c2", "c3"],
                "confidence": ["high", "high", "likely"],
            }
        )

        result = loader.create_resulted_in_relationships(df)

        assert result == 3

    def test_create_resulted_in_uses_merge(self):
        """Test query uses MERGE for idempotency."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "contract_id": ["c1"],
                "confidence": ["high"],
            }
        )

        loader.create_resulted_in_relationships(df)

        call_args = mock_session.run.call_args_list[0]
        query = call_args[0][0]

        assert "MERGE" in query
        assert "RESULTED_IN" in query
        assert "Transition" in query
        assert "Contract" in query

    def test_create_resulted_in_handles_errors(self):
        """Test error handling in RESULTED_IN creation."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Database error")
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "contract_id": ["c1"],
                "confidence": ["high"],
            }
        )

        loader.create_resulted_in_relationships(df)

        assert loader.stats["errors"] == 1


class TestTransitionLoaderEnabledByRelationships:
    """Tests for create_enabled_by_relationships method."""

    def test_create_enabled_by_none_patent_df(self):
        """Test with None patent_transitions_df."""
        mock_driver = Mock()
        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame({"transition_id": ["t1"]})
        result = loader.create_enabled_by_relationships(df, None)

        assert result == 0

    def test_create_enabled_by_empty_patent_df(self):
        """Test with empty patent_transitions_df."""
        mock_driver = Mock()
        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame({"transition_id": ["t1"]})
        patent_df = pd.DataFrame()

        result = loader.create_enabled_by_relationships(df, patent_df)

        assert result == 0

    def test_create_enabled_by_single(self):
        """Test creating single ENABLED_BY relationship."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame({"transition_id": ["t1"]})
        patent_df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "patent_id": ["p1"],
                "patent_contribution": [0.7],
            }
        )

        result = loader.create_enabled_by_relationships(df, patent_df)

        assert result == 1
        assert loader.stats["relationships_created"] == 1

    def test_create_enabled_by_uses_merge(self):
        """Test query uses MERGE for idempotency."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame({"transition_id": ["t1"]})
        patent_df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "patent_id": ["p1"],
                "patent_contribution": [0.7],
            }
        )

        loader.create_enabled_by_relationships(df, patent_df)

        call_args = mock_session.run.call_args_list[0]
        query = call_args[0][0]

        assert "MERGE" in query
        assert "ENABLED_BY" in query
        assert "Transition" in query
        assert "Patent" in query

    def test_create_enabled_by_handles_missing_contribution(self):
        """Test handles missing patent_contribution field."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame({"transition_id": ["t1"]})
        patent_df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "patent_id": ["p1"],
                # No patent_contribution field
            }
        )

        result = loader.create_enabled_by_relationships(df, patent_df)

        assert result == 1

    def test_create_enabled_by_handles_errors(self):
        """Test error handling in ENABLED_BY creation."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Database error")
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame({"transition_id": ["t1"]})
        patent_df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "patent_id": ["p1"],
                "patent_contribution": [0.7],
            }
        )

        loader.create_enabled_by_relationships(df, patent_df)

        assert loader.stats["errors"] == 1


class TestTransitionLoaderInvolvesTechnologyRelationships:
    """Tests for create_involves_technology_relationships method."""

    def test_create_involves_technology_no_cet_area(self):
        """Test with no CET area data."""
        mock_driver = Mock()
        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "cet_area": [None],
            }
        )

        result = loader.create_involves_technology_relationships(df)

        assert result == 0

    def test_create_involves_technology_empty_after_filter(self):
        """Test with transitions but no CET areas."""
        mock_driver = Mock()
        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2"],
                "cet_area": [None, pd.NA],
            }
        )

        result = loader.create_involves_technology_relationships(df)

        assert result == 0

    def test_create_involves_technology_single(self):
        """Test creating single INVOLVES_TECHNOLOGY relationship."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "cet_area": ["cet1"],
                "cet_alignment_score": [0.8],
            }
        )

        result = loader.create_involves_technology_relationships(df)

        assert result == 1
        assert loader.stats["relationships_created"] == 1

    def test_create_involves_technology_filters_na(self):
        """Test filters out transitions without CET areas."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 2}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1", "t2", "t3"],
                "cet_area": ["cet1", None, "cet2"],
                "cet_alignment_score": [0.8, 0.0, 0.9],
            }
        )

        result = loader.create_involves_technology_relationships(df)

        # Only t1 and t3 should be processed
        assert result == 2

    def test_create_involves_technology_uses_merge(self):
        """Test query uses MERGE for idempotency."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "cet_area": ["cet1"],
                "cet_alignment_score": [0.8],
            }
        )

        loader.create_involves_technology_relationships(df)

        call_args = mock_session.run.call_args_list[0]
        query = call_args[0][0]

        assert "MERGE" in query
        assert "INVOLVES_TECHNOLOGY" in query
        assert "Transition" in query
        assert "CETArea" in query

    def test_create_involves_technology_handles_missing_score(self):
        """Test handles missing cet_alignment_score."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "cet_area": ["cet1"],
                # No cet_alignment_score
            }
        )

        result = loader.create_involves_technology_relationships(df)

        assert result == 1

    def test_create_involves_technology_handles_errors(self):
        """Test error handling in INVOLVES_TECHNOLOGY creation."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Database error")
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        df = pd.DataFrame(
            {
                "transition_id": ["t1"],
                "cet_area": ["cet1"],
                "cet_alignment_score": [0.8],
            }
        )

        loader.create_involves_technology_relationships(df)

        assert loader.stats["errors"] == 1


class TestTransitionLoaderOrchestration:
    """Tests for load_transitions orchestration method."""

    def test_load_transitions_calls_all_methods(self):
        """Test load_transitions calls all required methods."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

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
        mock_driver = Mock()
        loader = TransitionLoader(mock_driver)

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
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

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
        mock_driver = Mock()
        loader = TransitionLoader(mock_driver, batch_size=1000000)

        assert loader.batch_size == 1000000

    def test_small_batch_size(self):
        """Test loader with small batch size."""
        mock_driver = Mock()
        loader = TransitionLoader(mock_driver, batch_size=1)

        assert loader.batch_size == 1

    def test_stats_accumulate_across_calls(self):
        """Test stats accumulate across multiple calls."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_result = Mock()
        mock_result.single.return_value = {"created": 1}
        mock_session.run.return_value = mock_result
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

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

        # Stats should accumulate
        assert loader.stats["transitions_created"] == 2

    def test_session_context_manager_used(self):
        """Test that session context manager is properly used."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_session
        mock_context.__exit__.return_value = None
        mock_driver.session.return_value = mock_context

        loader = TransitionLoader(mock_driver)
        loader.ensure_indexes()

        # Should enter and exit context
        mock_context.__enter__.assert_called()
        mock_context.__exit__.assert_called()

    def test_multiple_index_creation_calls(self):
        """Test calling ensure_indexes multiple times."""
        mock_driver = Mock()
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        loader = TransitionLoader(mock_driver)

        # Call multiple times
        loader.ensure_indexes()
        loader.ensure_indexes()

        # Should execute statements each time (idempotent with IF NOT EXISTS)
        assert mock_session.run.call_count == 8  # 4 indexes × 2 calls
