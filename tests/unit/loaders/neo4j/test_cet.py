"""Tests for Neo4j CET loader."""

from unittest.mock import MagicMock, Mock

import pytest

from src.loaders.neo4j.cet import CETLoader, CETLoaderConfig
from src.loaders.neo4j.client import Neo4jClient


pytestmark = pytest.mark.fast


class TestCETLoaderConfig:
    """Tests for CETLoaderConfig dataclass."""

    def test_default_config(self):
        """Test default CETLoaderConfig values."""
        config = CETLoaderConfig()

        assert config.batch_size == 1000
        assert config.create_indexes is True
        assert config.create_constraints is True

    def test_custom_config(self):
        """Test custom CETLoaderConfig values."""
        config = CETLoaderConfig(
            batch_size=500,
            create_indexes=False,
            create_constraints=False,
        )

        assert config.batch_size == 500
        assert config.create_indexes is False
        assert config.create_constraints is False

    def test_partial_custom_config(self):
        """Test partially custom CETLoaderConfig."""
        config = CETLoaderConfig(batch_size=2000)

        assert config.batch_size == 2000
        assert config.create_indexes is True
        assert config.create_constraints is True


class TestCETLoaderInitialization:
    """Tests for CETLoader initialization."""

    def test_initialization_with_default_config(self):
        """Test CETLoader initialization with default config."""
        mock_client = Mock(spec=Neo4jClient)
        loader = CETLoader(mock_client)

        assert loader.client == mock_client
        assert isinstance(loader.config, CETLoaderConfig)
        assert loader.config.batch_size == 1000

    def test_initialization_with_custom_config(self):
        """Test CETLoader initialization with custom config."""
        mock_client = Mock(spec=Neo4jClient)
        config = CETLoaderConfig(batch_size=500, create_indexes=False)

        loader = CETLoader(mock_client, config)

        assert loader.client == mock_client
        assert loader.config.batch_size == 500
        assert loader.config.create_indexes is False

    def test_initialization_with_none_config(self):
        """Test initialization with None uses defaults."""
        mock_client = Mock(spec=Neo4jClient)
        loader = CETLoader(mock_client, None)

        assert isinstance(loader.config, CETLoaderConfig)
        assert loader.config.batch_size == 1000


class TestCETLoaderConstraints:
    """Tests for constraint creation methods."""

    def test_create_constraints_executes_all(self):
        """Test create_constraints executes all constraint statements."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = CETLoader(mock_client)
        loader.create_constraints()

        # Should run 3 constraint statements (CETArea, Award, Company)
        assert mock_session.run.call_count == 3

    def test_create_constraints_handles_existing(self):
        """Test create_constraints handles already existing constraints."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Constraint already exists")
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_session
        mock_context.__exit__.return_value = None
        mock_client.session.return_value = mock_context

        loader = CETLoader(mock_client)

        # Should not raise exception
        loader.create_constraints()

        # Should have attempted all constraints
        assert mock_session.run.call_count == 3

    def test_create_constraints_cetarea_uniqueness(self):
        """Test CETArea constraint is for cet_id uniqueness."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = CETLoader(mock_client)
        loader.create_constraints()

        # First call should be for CETArea
        first_call = mock_session.run.call_args_list[0]
        constraint_query = first_call[0][0]

        assert "CETArea" in constraint_query
        assert "cet_id" in constraint_query
        assert "UNIQUE" in constraint_query

    def test_create_constraints_includes_entity_constraints(self):
        """Test constraints include Award and Company."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = CETLoader(mock_client)
        loader.create_constraints()

        # Collect all queries
        all_queries = " ".join([call[0][0] for call in mock_session.run.call_args_list])

        assert "Award" in all_queries
        assert "Company" in all_queries


class TestCETLoaderIndexes:
    """Tests for index creation methods."""

    def test_create_indexes_executes_multiple(self):
        """Test create_indexes executes multiple index statements."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = CETLoader(mock_client)
        loader.create_indexes()

        # Should create multiple indexes
        assert mock_session.run.call_count >= 3

    def test_create_indexes_handles_existing(self):
        """Test create_indexes handles already existing indexes."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Index already exists")
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = CETLoader(mock_client)

        # Should not raise exception
        loader.create_indexes()

        assert mock_session.run.call_count >= 3

    def test_create_indexes_covers_cet_properties(self):
        """Test indexes cover CET-related properties."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = CETLoader(mock_client)
        loader.create_indexes()

        # Collect all index queries
        all_queries = " ".join([call[0][0] for call in mock_session.run.call_args_list])

        # Should include CET-related indexes
        assert "CETArea" in all_queries or "cet" in all_queries.lower()


class TestCETLoaderConfiguration:
    """Tests for loader configuration options."""

    def test_indexes_disabled_in_config(self):
        """Test loader respects disabled indexes config."""
        mock_client = Mock(spec=Neo4jClient)
        config = CETLoaderConfig(create_indexes=False)

        loader = CETLoader(mock_client, config)

        assert loader.config.create_indexes is False

    def test_constraints_disabled_in_config(self):
        """Test loader respects disabled constraints config."""
        mock_client = Mock(spec=Neo4jClient)
        config = CETLoaderConfig(create_constraints=False)

        loader = CETLoader(mock_client, config)

        assert loader.config.create_constraints is False

    def test_batch_size_configuration(self):
        """Test batch size configuration is respected."""
        mock_client = Mock(spec=Neo4jClient)

        for batch_size in [100, 500, 1000, 5000]:
            config = CETLoaderConfig(batch_size=batch_size)
            loader = CETLoader(mock_client, config)
            assert loader.config.batch_size == batch_size


class TestCETLoaderEdgeCases:
    """Tests for edge cases in CETLoader."""

    def test_zero_batch_size(self):
        """Test loader handles zero batch size."""
        mock_client = Mock(spec=Neo4jClient)
        config = CETLoaderConfig(batch_size=0)

        loader = CETLoader(mock_client, config)

        assert loader.config.batch_size == 0

    def test_very_large_batch_size(self):
        """Test loader handles very large batch size."""
        mock_client = Mock(spec=Neo4jClient)
        config = CETLoaderConfig(batch_size=1000000)

        loader = CETLoader(mock_client, config)

        assert loader.config.batch_size == 1000000

    def test_multiple_constraint_creation_calls(self):
        """Test calling create_constraints multiple times."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = CETLoader(mock_client)

        # Call multiple times
        loader.create_constraints()
        loader.create_constraints()

        # Should execute statements each time (idempotent with IF NOT EXISTS)
        assert mock_session.run.call_count == 6  # 3 constraints × 2 calls

    def test_multiple_index_creation_calls(self):
        """Test calling create_indexes multiple times."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = CETLoader(mock_client)

        # Call multiple times
        loader.create_indexes()
        loader.create_indexes()

        # Should execute statements each time (idempotent with IF NOT EXISTS)
        first_call_count = mock_session.run.call_count
        assert first_call_count >= 6  # At least 3 indexes × 2 calls


class TestCETLoaderIntegration:
    """Integration-style tests for CETLoader."""

    def test_session_context_manager_used(self):
        """Test that session context manager is properly used."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_session
        mock_context.__exit__.return_value = None
        mock_client.session.return_value = mock_context

        loader = CETLoader(mock_client)
        loader.create_constraints()

        # Should enter and exit context
        mock_context.__enter__.assert_called()
        mock_context.__exit__.assert_called()

    def test_session_cleanup_on_error(self):
        """Test session is cleaned up even on error."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Database error")
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_session
        mock_client.session.return_value = mock_context

        loader = CETLoader(mock_client)

        # Should handle error and exit context
        loader.create_constraints()

        # Context should still be exited
        mock_context.__exit__.assert_called()

    def test_all_constraints_use_if_not_exists(self):
        """Test all constraints use IF NOT EXISTS for idempotency."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = CETLoader(mock_client)
        loader.create_constraints()

        # All constraint queries should use IF NOT EXISTS
        for call_args in mock_session.run.call_args_list:
            query = call_args[0][0]
            assert "IF NOT EXISTS" in query

    def test_all_indexes_use_if_not_exists(self):
        """Test all indexes use IF NOT EXISTS for idempotency."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = CETLoader(mock_client)
        loader.create_indexes()

        # All index queries should use IF NOT EXISTS
        for call_args in mock_session.run.call_args_list:
            query = call_args[0][0]
            assert "IF NOT EXISTS" in query


class TestCETLoaderConstraintQueries:
    """Tests for specific constraint query generation."""

    def test_cetarea_cet_id_constraint(self):
        """Test CETArea cet_id constraint is correct."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = CETLoader(mock_client)
        loader.create_constraints()

        # First constraint should be for CETArea cet_id
        first_call = mock_session.run.call_args_list[0]
        query = first_call[0][0]

        assert "cetarea_cet_id" in query.lower() or "CETArea" in query
        assert "cet_id" in query
        assert "UNIQUE" in query

    def test_award_constraint_included(self):
        """Test Award constraint is included."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = CETLoader(mock_client)
        loader.create_constraints()

        # One of the constraints should be for Award
        all_queries = [call[0][0] for call in mock_session.run.call_args_list]
        award_queries = [q for q in all_queries if "Award" in q]

        assert len(award_queries) > 0
        assert "award_id" in award_queries[0]

    def test_company_constraint_included(self):
        """Test Company constraint is included."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_session
        mock_context.__exit__.return_value = None
        mock_client.session.return_value = mock_context

        loader = CETLoader(mock_client)
        loader.create_constraints()

        # One of the constraints should be for Company
        all_queries = [call[0][0] for call in mock_session.run.call_args_list]
        company_queries = [q for q in all_queries if "Company" in q]

        assert len(company_queries) > 0
        assert "uei" in company_queries[0]


class TestCETLoaderBatchOperations:
    """Tests for batch operation configuration."""

    def test_small_batch_size(self):
        """Test loader with small batch size."""
        mock_client = Mock(spec=Neo4jClient)
        config = CETLoaderConfig(batch_size=10)

        loader = CETLoader(mock_client, config)

        assert loader.config.batch_size == 10

    def test_default_batch_size(self):
        """Test default batch size is 1000."""
        mock_client = Mock(spec=Neo4jClient)
        loader = CETLoader(mock_client)

        assert loader.config.batch_size == 1000

    def test_large_batch_size(self):
        """Test loader with large batch size."""
        mock_client = Mock(spec=Neo4jClient)
        config = CETLoaderConfig(batch_size=10000)

        loader = CETLoader(mock_client, config)

        assert loader.config.batch_size == 10000

    def test_batch_size_preserved_across_operations(self):
        """Test batch size is preserved across multiple operations."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_session
        mock_context.__exit__.return_value = None
        mock_client.session.return_value = mock_context

        config = CETLoaderConfig(batch_size=250)
        loader = CETLoader(mock_client, config)

        # Perform multiple operations
        loader.create_constraints()
        loader.create_indexes()

        # Batch size should remain unchanged
        assert loader.config.batch_size == 250
