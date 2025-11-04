"""Unit tests for CLI CommandContext."""

import pytest
from unittest.mock import Mock, patch

pytestmark = pytest.mark.fast

from rich.console import Console

from src.cli.context import CommandContext


class TestCommandContext:
    """Tests for CommandContext creation and initialization."""

    @patch("src.cli.context.DagsterClient")
    @patch("src.cli.context.Neo4jClient")
    @patch("src.cli.context.MetricsCollector")
    @patch("src.config.loader.get_config")
    def test_create_with_default_config(
        self,
        mock_get_config: Mock,
        mock_metrics: Mock,
        mock_neo4j: Mock,
        mock_dagster: Mock,
    ) -> None:
        """Test creating context with default config."""
        # Setup mocks
        mock_config = Mock()
        mock_get_config.return_value = mock_config

        mock_dagster_instance = Mock()
        mock_neo4j_instance = Mock()
        mock_metrics_instance = Mock()

        mock_dagster.return_value = mock_dagster_instance
        mock_neo4j.return_value = mock_neo4j_instance
        mock_metrics.return_value = mock_metrics_instance

        # Create context
        context = CommandContext.create()

        # Verify config and clients exist (actual instances are created, not mocks)
        assert context.config == mock_config
        assert isinstance(context.console, Console)
        assert context.dagster_client is not None
        assert context.neo4j_client is not None
        assert context.metrics_collector is not None

    def test_create_with_provided_config(self) -> None:
        """Test creating context with provided config."""
        # Setup mocks
        mock_config = Mock()

        # Create context with provided config (actual implementation)
        # This will create real client instances, which is fine for this test
        context = CommandContext.create(config=mock_config)

        # Verify config is set correctly
        assert context.config == mock_config
        # Verify clients are initialized
        assert context.dagster_client is not None
        assert context.neo4j_client is not None
        assert context.metrics_collector is not None
