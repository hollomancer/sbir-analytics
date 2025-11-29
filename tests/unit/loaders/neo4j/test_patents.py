"""Tests for Neo4j patents loader."""

from unittest.mock import MagicMock, Mock

import pytest

from src.loaders.neo4j.client import Neo4jClient
from src.loaders.neo4j.patents import PatentLoader, PatentLoaderConfig


pytestmark = pytest.mark.fast


class TestPatentLoaderConfig:
    """Tests for PatentLoaderConfig dataclass."""

    def test_default_config(self):
        """Test default PatentLoaderConfig values."""
        config = PatentLoaderConfig()

        assert config.batch_size == 1000
        assert config.create_indexes is True
        assert config.create_constraints is True
        assert config.link_to_sbir is True

    def test_custom_config(self):
        """Test custom PatentLoaderConfig values."""
        config = PatentLoaderConfig(
            batch_size=500,
            create_indexes=False,
            create_constraints=False,
            link_to_sbir=False,
        )

        assert config.batch_size == 500
        assert config.create_indexes is False
        assert config.create_constraints is False
        assert config.link_to_sbir is False

    def test_partial_custom_config(self):
        """Test partially custom PatentLoaderConfig."""
        config = PatentLoaderConfig(batch_size=2000)

        assert config.batch_size == 2000
        # Other values should use defaults
        assert config.create_indexes is True
        assert config.create_constraints is True


class TestPatentLoaderInitialization:
    """Tests for PatentLoader initialization."""

    def test_initialization_with_default_config(self):
        """Test PatentLoader initialization with default config."""
        mock_client = Mock(spec=Neo4jClient)
        loader = PatentLoader(mock_client)

        assert loader.client == mock_client
        assert isinstance(loader.config, PatentLoaderConfig)
        assert loader.config.batch_size == 1000

    def test_initialization_with_custom_config(self):
        """Test PatentLoader initialization with custom config."""
        mock_client = Mock(spec=Neo4jClient)
        config = PatentLoaderConfig(batch_size=500, create_indexes=False)

        loader = PatentLoader(mock_client, config)

        assert loader.client == mock_client
        assert loader.config.batch_size == 500
        assert loader.config.create_indexes is False

    def test_initialization_stores_client_reference(self):
        """Test that client reference is stored correctly."""
        mock_client = Mock(spec=Neo4jClient)
        loader = PatentLoader(mock_client)

        assert loader.client is mock_client


class TestPatentLoaderConstraints:
    """Tests for constraint creation methods."""

    def test_create_constraints_executes_all(self):
        """Test create_constraints executes all constraint statements."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)
        loader.create_constraints()

        # Should run 4 constraint statements (Patent, PatentAssignment, PatentEntity, Organization)
        assert mock_session.run.call_count == 4

    def test_create_constraints_handles_existing_constraints(self):
        """Test create_constraints handles already existing constraints."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Constraint already exists")
        mock_client.session.return_value = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)

        # Should not raise exception
        loader.create_constraints()

        # Should have attempted all 4 constraints
        assert mock_session.run.call_count == 4

    def test_create_constraints_patent_uniqueness(self):
        """Test Patent constraint is for grant_doc_num uniqueness."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)
        loader.create_constraints()

        # First call should be for Patent
        first_call = mock_session.run.call_args_list[0]
        constraint_query = first_call[0][0]

        assert "Patent" in constraint_query
        assert "grant_doc_num" in constraint_query
        assert "UNIQUE" in constraint_query


class TestPatentLoaderIndexes:
    """Tests for index creation methods."""

    def test_create_indexes_executes_multiple(self):
        """Test create_indexes executes multiple index statements."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)
        loader.create_indexes()

        # Should create multiple indexes (at least 6 based on code)
        assert mock_session.run.call_count >= 6

    def test_create_indexes_handles_existing_indexes(self):
        """Test create_indexes handles already existing indexes."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_session.run.side_effect = Exception("Index already exists")
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)

        # Should not raise exception
        loader.create_indexes()

        # Should have attempted all indexes
        assert mock_session.run.call_count >= 6

    def test_create_indexes_covers_key_properties(self):
        """Test indexes cover key properties."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)
        loader.create_indexes()

        # Collect all index queries
        all_queries = " ".join([call[0][0] for call in mock_session.run.call_args_list])

        # Should include indexes for key properties
        assert "grant_doc_num" in all_queries
        assert "rf_id" in all_queries
        assert "normalized_name" in all_queries
        assert "entity_type" in all_queries


class TestPatentLoaderBatchOperations:
    """Tests for batch operation methods."""

    def test_batch_size_respected_in_config(self):
        """Test batch size configuration is respected."""
        mock_client = Mock(spec=Neo4jClient)
        config = PatentLoaderConfig(batch_size=100)

        loader = PatentLoader(mock_client, config)

        assert loader.config.batch_size == 100

    def test_different_batch_sizes(self):
        """Test loader handles different batch sizes."""
        mock_client = Mock(spec=Neo4jClient)

        for batch_size in [100, 500, 1000, 5000]:
            config = PatentLoaderConfig(batch_size=batch_size)
            loader = PatentLoader(mock_client, config)
            assert loader.config.batch_size == batch_size


class TestPatentLoaderConfiguration:
    """Tests for loader configuration options."""

    def test_indexes_disabled_in_config(self):
        """Test loader respects disabled indexes config."""
        mock_client = Mock(spec=Neo4jClient)
        config = PatentLoaderConfig(create_indexes=False)

        loader = PatentLoader(mock_client, config)

        assert loader.config.create_indexes is False

    def test_constraints_disabled_in_config(self):
        """Test loader respects disabled constraints config."""
        mock_client = Mock(spec=Neo4jClient)
        config = PatentLoaderConfig(create_constraints=False)

        loader = PatentLoader(mock_client, config)

        assert loader.config.create_constraints is False

    def test_sbir_linking_disabled_in_config(self):
        """Test loader respects disabled SBIR linking."""
        mock_client = Mock(spec=Neo4jClient)
        config = PatentLoaderConfig(link_to_sbir=False)

        loader = PatentLoader(mock_client, config)

        assert loader.config.link_to_sbir is False

    def test_all_features_disabled(self):
        """Test loader with all optional features disabled."""
        mock_client = Mock(spec=Neo4jClient)
        config = PatentLoaderConfig(
            create_indexes=False,
            create_constraints=False,
            link_to_sbir=False,
        )

        loader = PatentLoader(mock_client, config)

        assert loader.config.create_indexes is False
        assert loader.config.create_constraints is False
        assert loader.config.link_to_sbir is False


class TestPatentLoaderEdgeCases:
    """Tests for edge cases in PatentLoader."""

    def test_zero_batch_size(self):
        """Test loader handles zero batch size."""
        mock_client = Mock(spec=Neo4jClient)
        config = PatentLoaderConfig(batch_size=0)

        loader = PatentLoader(mock_client, config)

        # Should accept the value (validation happens at runtime)
        assert loader.config.batch_size == 0

    def test_very_large_batch_size(self):
        """Test loader handles very large batch size."""
        mock_client = Mock(spec=Neo4jClient)
        config = PatentLoaderConfig(batch_size=1000000)

        loader = PatentLoader(mock_client, config)

        assert loader.config.batch_size == 1000000

    def test_negative_batch_size(self):
        """Test loader with negative batch size."""
        mock_client = Mock(spec=Neo4jClient)
        config = PatentLoaderConfig(batch_size=-100)

        loader = PatentLoader(mock_client, config)

        # Should accept (validation is runtime concern)
        assert loader.config.batch_size == -100

    def test_multiple_constraint_creation_calls(self):
        """Test calling create_constraints multiple times."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)

        # Call multiple times
        loader.create_constraints()
        loader.create_constraints()

        # Should execute statements each time (idempotent with IF NOT EXISTS)
        assert mock_session.run.call_count == 6  # 3 constraints × 2 calls

    def test_multiple_index_creation_calls(self):
        """Test calling create_indexes multiple times."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)

        # Call multiple times
        loader.create_indexes()
        loader.create_indexes()

        # Should execute statements each time (idempotent with IF NOT EXISTS)
        first_call_count = mock_session.run.call_count
        assert first_call_count >= 12  # At least 6 indexes × 2 calls


class TestPatentLoaderIntegration:
    """Integration-style tests for PatentLoader."""

    def test_session_context_manager_used(self):
        """Test that session context manager is properly used."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_context = MagicMock()
        mock_context.__enter__.return_value = mock_session
        mock_context.__exit__.return_value = None
        mock_client.session.return_value = mock_context

        loader = PatentLoader(mock_client)
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

        loader = PatentLoader(mock_client)

        # Should handle error and exit context
        loader.create_constraints()  # Errors are caught and logged

        # Context should still be exited
        mock_context.__exit__.assert_called()

    def test_config_none_uses_defaults(self):
        """Test passing None for config uses defaults."""
        mock_client = Mock(spec=Neo4jClient)
        loader = PatentLoader(mock_client, None)

        assert loader.config.batch_size == 1000
        assert loader.config.create_indexes is True

    def test_loader_with_real_config_object(self):
        """Test loader works with actual config object."""
        mock_client = Mock(spec=Neo4jClient)
        config = PatentLoaderConfig(
            batch_size=250,
            create_indexes=True,
            create_constraints=True,
            link_to_sbir=False,
        )

        loader = PatentLoader(mock_client, config)

        assert loader.config is config
        assert loader.config.batch_size == 250
        assert loader.config.link_to_sbir is False


class TestPatentLoaderConstraintQueries:
    """Tests for specific constraint query generation."""

    def test_patent_assignment_constraint_query(self):
        """Test PatentAssignment constraint includes rf_id."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)
        loader.create_constraints()

        # Check second call (PatentAssignment)
        second_call = mock_session.run.call_args_list[1]
        constraint_query = second_call[0][0]

        assert "PatentAssignment" in constraint_query
        assert "rf_id" in constraint_query

    def test_patent_entity_constraint_query(self):
        """Test PatentEntity constraint includes entity_id."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)
        loader.create_constraints()

        # Check third call (PatentEntity)
        third_call = mock_session.run.call_args_list[2]
        constraint_query = third_call[0][0]

        assert "PatentEntity" in constraint_query
        assert "entity_id" in constraint_query

    def test_all_constraints_use_if_not_exists(self):
        """Test all constraints use IF NOT EXISTS for idempotency."""
        mock_client = Mock(spec=Neo4jClient)
        mock_session = MagicMock()
        mock_client.session.return_value = MagicMock()
        mock_client.session.return_value.__enter__.return_value = mock_session

        loader = PatentLoader(mock_client)
        loader.create_constraints()

        # All constraint queries should use IF NOT EXISTS
        for call_args in mock_session.run.call_args_list:
            query = call_args[0][0]
            assert "IF NOT EXISTS" in query
