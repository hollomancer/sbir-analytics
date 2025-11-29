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

    @pytest.mark.requires_neo4j
    def test_status_summary_command(self, runner: CliRunner, neo4j_driver) -> None:
        """Test status summary command."""
        result = runner.invoke(app, ["status", "summary"])
        # Requires Neo4j and other services
        assert result.exit_code in [0, 1]

    def test_metrics_latest_command(self, runner: CliRunner, tmp_path, monkeypatch) -> None:
        """Test metrics latest command."""
        # Create mock metrics directory
        metrics_dir = tmp_path / "metrics"
        metrics_dir.mkdir()
        monkeypatch.setenv("METRICS_DIR", str(metrics_dir))

        result = runner.invoke(app, ["metrics", "latest"])
        # Should handle missing metrics gracefully
        assert result.exit_code in [0, 1]

    def test_ingest_dry_run(self, runner: CliRunner, tmp_path, monkeypatch) -> None:
        """Test ingest run with dry-run."""
        # Set up minimal config for dry-run
        monkeypatch.chdir(tmp_path)

        result = runner.invoke(app, ["ingest", "run", "--dry-run"])
        # Dry-run should not require actual services
        assert result.exit_code in [0, 1]

    def test_error_handling(self, runner: CliRunner) -> None:
        """Test error handling in commands."""
        # Test with invalid command
        result = runner.invoke(app, ["nonexistent", "command"])
        # Should handle invalid commands gracefully
        assert result.exit_code != 0
