"""Integration tests for CLI commands."""

import pytest
from typer.testing import CliRunner

from src.cli.main import app

pytestmark = pytest.mark.integration


@pytest.fixture
def runner() -> CliRunner:
    """Create CLI test runner."""
    return CliRunner()


class TestCLIIntegration:
    """Integration tests for CLI application."""

    def test_main_app_help(self, runner: CliRunner) -> None:
        """Test main app help output."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "SBIR" in result.stdout or "CLI" in result.stdout

    @pytest.mark.skip(reason="Requires running services - see INTEGRATION_TEST_ANALYSIS.md")
    def test_status_summary_command(self, runner: CliRunner) -> None:
        """Test status summary command."""
        result = runner.invoke(app, ["status", "summary"])
        # Requires Neo4j and other services
        assert result.exit_code in [0, 1]

    @pytest.mark.skip(reason="Requires running services - see INTEGRATION_TEST_ANALYSIS.md")
    def test_metrics_latest_command(self, runner: CliRunner) -> None:
        """Test metrics latest command."""
        result = runner.invoke(app, ["metrics", "latest"])
        # Requires metrics data
        assert result.exit_code in [0, 1]

    @pytest.mark.skip(reason="Requires running services - see INTEGRATION_TEST_ANALYSIS.md")
    def test_ingest_dry_run(self, runner: CliRunner) -> None:
        """Test ingest run with dry-run."""
        result = runner.invoke(app, ["ingest", "run", "--dry-run"])
        # Requires configuration and services
        assert result.exit_code == 0

    @pytest.mark.skip(reason="Requires running services - see INTEGRATION_TEST_ANALYSIS.md")
    def test_error_handling(self, runner: CliRunner) -> None:
        """Test error handling in commands."""
        result = runner.invoke(app, ["status", "summary"])
        # Error handling depends on service availability
        assert result.exit_code != 0
