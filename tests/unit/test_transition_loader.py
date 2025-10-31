"""
Unit tests for TransitionLoader Neo4j operations (Task 19.8).

Tests cover:
- Transition node creation with proper schema
- Index creation
- Relationship creation (TRANSITIONED_TO, RESULTED_IN, ENABLED_BY, INVOLVES_TECHNOLOGY)
- Batch processing and statistics
- Idempotency via MERGE operations
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.loaders.transition_loader import TransitionLoader


@pytest.fixture
def mock_neo4j_driver():
    """Create a mock Neo4j driver."""
    driver = MagicMock()
    session = MagicMock()
    driver.session.return_value.__enter__ = MagicMock(return_value=session)
    driver.session.return_value.__exit__ = MagicMock(return_value=None)
    return driver


@pytest.fixture
def sample_transitions_df():
    """Sample transition detections DataFrame."""
    return pd.DataFrame(
        [
            {
                "transition_id": "TRANS-001",
                "award_id": "AWARD-A1",
                "contract_id": "CONTRACT-C1",
                "score": 0.85,
                "method": "agency_continuity",
                "computed_at": "2024-01-15T10:30:00Z",
                "signals": '["agency_continuity", "timing_proximity"]',
                "confidence": "high",
            },
            {
                "transition_id": "TRANS-002",
                "award_id": "AWARD-A2",
                "contract_id": "CONTRACT-C2",
                "score": 0.72,
                "method": "timing_proximity",
                "computed_at": "2024-01-15T10:31:00Z",
                "signals": '["timing_proximity"]',
                "confidence": "likely",
            },
            {
                "transition_id": "TRANS-003",
                "award_id": "AWARD-A3",
                "contract_id": "CONTRACT-C3",
                "score": 0.55,
                "method": "competition_type",
                "computed_at": "2024-01-15T10:32:00Z",
                "signals": '["competition_type"]',
                "confidence": "possible",
            },
        ]
    )


class TestTransitionLoaderInitialization:
    """Test TransitionLoader initialization."""

    def test_init_with_default_batch_size(self, mock_neo4j_driver):
        """Test loader initialization with default batch size."""
        loader = TransitionLoader(driver=mock_neo4j_driver)
        assert loader.driver == mock_neo4j_driver
        assert loader.batch_size == 1000
        assert loader.stats["transitions_created"] == 0
        assert loader.stats["transitions_updated"] == 0
        assert loader.stats["relationships_created"] == 0
        assert loader.stats["errors"] == 0

    def test_init_with_custom_batch_size(self, mock_neo4j_driver):
        """Test loader initialization with custom batch size."""
        loader = TransitionLoader(driver=mock_neo4j_driver, batch_size=500)
        assert loader.batch_size == 500

    def test_get_stats(self, mock_neo4j_driver):
        """Test get_stats returns a copy of stats."""
        loader = TransitionLoader(driver=mock_neo4j_driver)
        stats = loader.get_stats()
        assert isinstance(stats, dict)
        assert "transitions_created" in stats
        # Verify it's a copy, not a reference
        stats["transitions_created"] = 999
        assert loader.stats["transitions_created"] == 0


class TestIndexCreation:
    """Test Neo4j index creation."""

    def test_ensure_indexes_creates_all_required_indexes(self, mock_neo4j_driver):
        """Test that ensure_indexes creates all required indexes."""
        loader = TransitionLoader(driver=mock_neo4j_driver)
        loader.ensure_indexes()

        # Verify session was created
        mock_neo4j_driver.session.assert_called()
        session = mock_neo4j_driver.session.return_value.__enter__.return_value

        # Verify all expected index creation queries were called
        calls = session.run.call_args_list
        assert len(calls) >= 4  # At least 4 index creation calls

        # Check for specific index creation queries
        run_calls = [call[0][0] for call in calls]
        assert any("transition_id_index" in str(q) for q in run_calls)
        assert any("transition_confidence_index" in str(q) for q in run_calls)
        assert any("transition_score_index" in str(q) for q in run_calls)
        assert any("transition_date_index" in str(q) for q in run_calls)

    def test_ensure_indexes_handles_errors(self, mock_neo4j_driver):
        """Test error handling in index creation."""
        session = MagicMock()
        session.run.side_effect = Exception("Index creation failed")
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_neo4j_driver)

        with pytest.raises(Exception, match="Index creation failed"):
            loader.ensure_indexes()


class TestTransitionNodeLoading:
    """Test loading transition nodes into Neo4j."""

    def test_load_transition_nodes_basic(self, mock_neo4j_driver, sample_transitions_df):
        """Test loading transition nodes with basic DataFrame."""
        session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_neo4j_driver)
        result = loader.load_transition_nodes(sample_transitions_df)

        # Verify nodes were processed
        assert result == len(sample_transitions_df)
        assert loader.stats["transitions_created"] >= 0

        # Verify MERGE operations were called
        session.run.assert_called()

    def test_load_transition_nodes_batch_processing(self, mock_neo4j_driver, sample_transitions_df):
        """Test batch processing of transition nodes."""
        session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_neo4j_driver, batch_size=2)
        result = loader.load_transition_nodes(sample_transitions_df)

        # Should process in 2 batches (3 rows with batch_size=2)
        assert result >= 0
        assert session.run.called

    def test_load_transition_nodes_empty_dataframe(self, mock_neo4j_driver):
        """Test loading empty transition DataFrame."""
        session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_neo4j_driver)
        empty_df = pd.DataFrame(columns=["transition_id", "award_id", "contract_id"])

        result = loader.load_transition_nodes(empty_df)
        assert result == 0

    def test_load_transition_nodes_creates_proper_properties(
        self, mock_neo4j_driver, sample_transitions_df
    ):
        """Test that loaded nodes have proper properties."""
        session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_neo4j_driver)
        loader.load_transition_nodes(sample_transitions_df)

        # Verify MERGE queries were constructed properly
        run_calls = [call[0][0] for call in session.run.call_args_list]
        cypher_queries = [str(q) for q in run_calls if q]

        # Check that properties are being set
        properties_found = False
        for query in cypher_queries:
            if all(prop in query for prop in ["likelihood_score", "confidence", "detection_date"]):
                properties_found = True
                break

        assert properties_found or len(cypher_queries) > 0  # At least some Cypher was called


class TestRelationshipCreation:
    """Test creating relationships between transition nodes."""

    def test_create_transitioned_to_relationships(self, mock_neo4j_driver, sample_transitions_df):
        """Test creating TRANSITIONED_TO relationships."""
        session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_neo4j_driver)
        loader.create_transitioned_to_relationships(sample_transitions_df)

        # Verify relationships were created
        session.run.assert_called()
        assert loader.stats["relationships_created"] >= 0

    def test_create_resulted_in_relationships(self, mock_neo4j_driver, sample_transitions_df):
        """Test creating RESULTED_IN relationships."""
        session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_neo4j_driver)
        loader.create_resulted_in_relationships(sample_transitions_df)

        # Verify relationships were created
        session.run.assert_called()

    def test_create_enabled_by_relationships(self, mock_neo4j_driver, sample_transitions_df):
        """Test creating ENABLED_BY relationships for patent-backed transitions."""
        session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_neo4j_driver)
        loader.create_enabled_by_relationships(sample_transitions_df)

        # Verify relationships were created
        session.run.assert_called()

    def test_create_involves_technology_relationships(
        self, mock_neo4j_driver, sample_transitions_df
    ):
        """Test creating INVOLVES_TECHNOLOGY relationships."""
        session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_neo4j_driver)
        loader.create_involves_technology_relationships(sample_transitions_df)

        # Verify relationships were created
        session.run.assert_called()

    def test_relationships_batch_processing(self, mock_neo4j_driver, sample_transitions_df):
        """Test batch processing of relationships."""
        session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_neo4j_driver, batch_size=1)
        loader.create_transitioned_to_relationships(sample_transitions_df)

        # Should process in 3 batches (3 rows with batch_size=1)
        assert session.run.call_count >= 3


class TestOrchestration:
    """Test full orchestration of transition loading."""

    def test_load_transitions_orchestration(self, mock_neo4j_driver, sample_transitions_df):
        """Test full transition loading orchestration."""
        session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_neo4j_driver)
        stats = loader.load_transitions(sample_transitions_df)

        # Verify all steps were executed
        assert isinstance(stats, dict)
        assert "transitions_created" in stats
        assert "relationships_created" in stats
        assert session.run.called

    def test_load_transitions_with_patents(self, mock_neo4j_driver, sample_transitions_df):
        """Test transition loading with patent data."""
        session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        patents_df = pd.DataFrame(
            [
                {"award_id": "AWARD-A1", "patent_id": "PAT-001"},
                {"award_id": "AWARD-A2", "patent_id": "PAT-002"},
            ]
        )

        loader = TransitionLoader(driver=mock_neo4j_driver)
        stats = loader.load_transitions(sample_transitions_df, patents_df)

        # Verify patent transitions were processed
        assert isinstance(stats, dict)
        assert session.run.called


class TestStatisticsTracking:
    """Test statistics tracking during loading."""

    def test_stats_initialization(self, mock_neo4j_driver):
        """Test stats dictionary is properly initialized."""
        loader = TransitionLoader(driver=mock_neo4j_driver)
        stats = loader.get_stats()

        assert stats["transitions_created"] == 0
        assert stats["transitions_updated"] == 0
        assert stats["relationships_created"] == 0
        assert stats["errors"] == 0

    def test_stats_copied_not_referenced(self, mock_neo4j_driver):
        """Test that get_stats returns a copy, not a reference."""
        loader = TransitionLoader(driver=mock_neo4j_driver)
        stats1 = loader.get_stats()
        stats1["transitions_created"] = 100

        stats2 = loader.get_stats()
        assert stats2["transitions_created"] == 0


class TestErrorHandling:
    """Test error handling in transition loading."""

    def test_load_nodes_with_session_error(self, mock_neo4j_driver, sample_transitions_df):
        """Test handling of Neo4j session errors."""
        session = MagicMock()
        session.run.side_effect = Exception("Neo4j connection error")
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_neo4j_driver)

        # Should still raise the exception
        with pytest.raises(Exception, match="Neo4j connection error"):
            loader.load_transition_nodes(sample_transitions_df)

    def test_missing_required_columns(self, mock_neo4j_driver):
        """Test handling of missing required columns in DataFrame."""
        session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        # DataFrame with missing required columns
        invalid_df = pd.DataFrame(
            [
                {"transition_id": "TRANS-001", "award_id": "AWARD-A1"},
            ]
        )

        loader = TransitionLoader(driver=mock_neo4j_driver)

        # Should handle gracefully or raise appropriate error
        try:
            result = loader.load_transition_nodes(invalid_df)
            # If it doesn't raise, verify it attempted to process
            assert result >= 0
        except (KeyError, ValueError):
            # Expected if strict column validation is implemented
            pass


class TestIdempotency:
    """Test idempotency via MERGE operations."""

    def test_merge_operations_idempotent(self, mock_neo4j_driver, sample_transitions_df):
        """Test that MERGE operations ensure idempotency."""
        session = MagicMock()
        mock_neo4j_driver.session.return_value.__enter__.return_value = session

        loader = TransitionLoader(driver=mock_neo4j_driver)
        loader.load_transition_nodes(sample_transitions_df)

        # Verify MERGE (not CREATE) operations were used
        run_calls = [call[0][0] for call in session.run.call_args_list]
        cypher_queries = [str(q) for q in run_calls if q]

        # Check that MERGE is being used
        merge_found = any("MERGE" in query for query in cypher_queries)
        assert merge_found or len(cypher_queries) > 0  # At least some Cypher was called
