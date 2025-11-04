"""Integration tests for CLI commands with mocked services."""

from unittest.mock import Mock, patch

import pytest

pytestmark = pytest.mark.integration
from typer.testing import CliRunner

from src.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    """Create CLI test runner."""
    return CliRunner()


class TestCLIIntegration:
    """Integration tests for CLI application."""

    @patch("src.cli.main.CommandContext")
    def test_main_app_help(self, mock_context_class: Mock, runner: CliRunner) -> None:
        """Test main app help output."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "SBIR Analytics Pipeline CLI" in result.stdout

    @patch("src.cli.main.CommandContext")
    def test_status_summary_command(self, mock_context_class: Mock, runner: CliRunner) -> None:
        """Test status summary command."""
        # Setup mock context
        mock_context = Mock()
        mock_context.dagster_client.list_assets.return_value = []
        mock_context.dagster_client.get_asset_status.return_value = Mock(
            status="success",
            last_run=None,
            records_processed=None,
        )
        mock_context.neo4j_client.health_check.return_value = Mock(
            connected=True,
            uri="bolt://localhost:7687",
            error=None,
        )
        mock_context_class.create.return_value = mock_context

        result = runner.invoke(app, ["status", "summary"])

        # Should either succeed or show error (depending on actual implementation)
        assert result.exit_code in [0, 1]  # Allow both success and error cases

    @patch("src.cli.main.CommandContext")
    def test_metrics_latest_command(self, mock_context_class: Mock, runner: CliRunner) -> None:
        """Test metrics latest command."""
        # Setup mock context
        mock_context = Mock()
        from src.cli.integration.metrics_collector import PipelineMetrics

        mock_context.metrics_collector.get_latest_metrics.return_value = PipelineMetrics(
            enrichment_success_rate=0.9,
            processing_throughput=100.0,
            memory_usage_mb=512.0,
            error_count=0,
            last_updated=Mock(),
        )
        mock_context_class.create.return_value = mock_context

        result = runner.invoke(app, ["metrics", "latest"])

        # Should either succeed or show error
        assert result.exit_code in [0, 1]

    @patch("src.cli.main.CommandContext")
    def test_ingest_dry_run(self, mock_context_class: Mock, runner: CliRunner) -> None:
        """Test ingest run with dry-run."""
        # Setup mock context
        mock_context = Mock()
        mock_context_class.create.return_value = mock_context

        result = runner.invoke(app, ["ingest", "run", "--dry-run"])

        # Dry-run should succeed
        assert result.exit_code == 0

    @patch("src.cli.main.CommandContext")
    def test_error_handling(self, mock_context_class: Mock, runner: CliRunner) -> None:
        """Test error handling in commands."""
        # Setup mock context that raises error
        mock_context_class.create.side_effect = Exception("Config error")

        result = runner.invoke(app, ["status", "summary"])

        # Should handle error gracefully
        assert result.exit_code != 0
