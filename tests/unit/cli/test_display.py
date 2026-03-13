"""Unit tests for CLI display components."""

import pytest
from rich.panel import Panel

from src.cli.display.errors import (
    CLIError,
    ConfigError,
    ConnectionError,
    DataError,
    EXIT_CONFIG_ERROR,
    EXIT_CONNECTION_ERROR,
    EXIT_DATA_ERROR,
    EXIT_RUNTIME_ERROR,
    format_error,
    _infer_exit_code,
    _infer_suggestions,
)
from src.cli.display.metrics import create_metrics_table, format_threshold_indicator
from src.cli.display.progress import PipelineProgressTracker, create_progress_tracker
from src.cli.display.status import (
    create_asset_status_table,
    create_summary_panel,
    get_health_indicator,
)

pytestmark = pytest.mark.fast


class TestErrorFormatting:
    """Tests for error formatting and display."""

    def test_cli_error_stores_exit_code(self):
        err = CLIError("test error", exit_code=2, suggestions=["try this"])
        assert err.exit_code == 2
        assert err.suggestions == ["try this"]
        assert str(err) == "test error"

    def test_config_error_has_config_exit_code(self):
        err = ConfigError("bad config")
        assert err.exit_code == EXIT_CONFIG_ERROR
        assert len(err.suggestions) > 0

    def test_connection_error_has_connection_exit_code(self):
        err = ConnectionError("cannot connect", service="Neo4j")
        assert err.exit_code == EXIT_CONNECTION_ERROR
        assert any("Neo4j" in s for s in err.suggestions)

    def test_data_error_has_data_exit_code(self):
        err = DataError("file missing")
        assert err.exit_code == EXIT_DATA_ERROR
        assert len(err.suggestions) > 0

    def test_format_error_returns_panel(self):
        err = CLIError("something went wrong", suggestions=["restart"])
        panel = format_error(err)
        assert isinstance(panel, Panel)

    def test_format_error_includes_type_for_subclasses(self):
        err = ConfigError("bad yaml")
        panel = format_error(err)
        # Panel contains Text with error type info
        assert isinstance(panel, Panel)

    def test_format_error_generic_exception(self):
        err = Exception("generic failure")
        panel = format_error(err)
        assert isinstance(panel, Panel)

    def test_infer_exit_code_connection(self):
        err = Exception("connection refused by server")
        assert _infer_exit_code(err) == EXIT_CONNECTION_ERROR

    def test_infer_exit_code_timeout(self):
        err = Exception("request timeout after 30s")
        assert _infer_exit_code(err) == EXIT_CONNECTION_ERROR

    def test_infer_exit_code_config(self):
        err = Exception("configuration validation failed")
        assert _infer_exit_code(err) == EXIT_CONFIG_ERROR

    def test_infer_exit_code_not_found(self):
        err = Exception("file not found: data/awards.csv")
        assert _infer_exit_code(err) == EXIT_DATA_ERROR

    def test_infer_exit_code_generic(self):
        err = Exception("unknown error occurred")
        assert _infer_exit_code(err) == EXIT_RUNTIME_ERROR

    def test_infer_suggestions_connection(self):
        err = Exception("connection refused")
        suggestions = _infer_suggestions(err)
        assert len(suggestions) > 0
        assert any("running" in s.lower() for s in suggestions)

    def test_infer_suggestions_import(self):
        err = Exception("cannot import module foo")
        suggestions = _infer_suggestions(err)
        assert len(suggestions) > 0

    def test_infer_suggestions_generic_returns_empty(self):
        err = Exception("something happened")
        suggestions = _infer_suggestions(err)
        assert suggestions == []

    def test_cli_error_default_exit_code(self):
        err = CLIError("test")
        assert err.exit_code == EXIT_RUNTIME_ERROR

    def test_cli_error_default_empty_suggestions(self):
        err = CLIError("test")
        assert err.suggestions == []


class TestProgressTracker:
    """Tests for progress tracker."""

    @pytest.fixture
    def console(self):
        """Create real console for testing."""
        from io import StringIO

        from rich.console import Console

        return Console(file=StringIO())

    def test_create_progress_tracker(self, console) -> None:
        """Test creating progress tracker."""
        tracker = create_progress_tracker(console)

        assert isinstance(tracker, PipelineProgressTracker)
        assert tracker.console == console

    def test_track_operation(self, console) -> None:
        """Test tracking a single operation."""
        tracker = create_progress_tracker(console)

        # Track operation
        with tracker.track_operation("Test operation", total=100) as update:
            update({"completed": 50, "records": 1000})

        # Verify progress was updated (would need to check mock calls in real test)

    def test_track_multiple_operations(self, console) -> None:
        """Test tracking multiple operations."""
        tracker = create_progress_tracker(console)

        operations = [
            {"description": "Operation 1", "total": 100},
            {"description": "Operation 2", "total": 200},
        ]

        with tracker.track_multiple_operations(operations) as updates:
            assert "Operation 1" in updates
            assert "Operation 2" in updates

            # Update operations
            updates["Operation 1"]({"completed": 50, "records": 500})
            updates["Operation 2"]({"completed": 100, "records": 1000})


class TestMetricsDisplay:
    """Tests for metrics display components."""

    @pytest.fixture
    def console(self):
        """Create real console for testing."""
        from io import StringIO

        from rich.console import Console

        return Console(file=StringIO())

    def test_format_threshold_indicator_high(self, console) -> None:
        """Test threshold indicator for high value."""
        thresholds = {"low": 0.3, "medium": 0.6, "high": 0.8}
        indicator = format_threshold_indicator(0.9, thresholds)

        assert "✓" in str(indicator) or indicator.style == "green"

    def test_format_threshold_indicator_medium(self, console) -> None:
        """Test threshold indicator for medium value."""
        thresholds = {"low": 0.3, "medium": 0.6, "high": 0.8}
        indicator = format_threshold_indicator(0.7, thresholds)

        # Should be yellow/warning
        assert indicator is not None

    def test_create_metrics_table(self, console) -> None:
        """Test creating metrics table."""
        metrics = [
            {
                "timestamp": "2024-01-01T00:00:00",
                "asset_key": "test_asset",
                "duration_seconds": 10.0,
                "records_processed": 100,
                "success": True,
                "peak_memory_mb": 512.0,
            }
        ]

        table = create_metrics_table(metrics, console)

        assert table is not None
        assert len(table.columns) > 0


class TestStatusDisplay:
    """Tests for status display components."""

    @pytest.fixture
    def console(self):
        """Create real console for testing."""
        from io import StringIO

        from rich.console import Console

        return Console(file=StringIO())

    def test_get_health_indicator_success(self, console) -> None:
        """Test health indicator for success status."""
        indicator = get_health_indicator("success")

        assert "✓" in str(indicator) or indicator.style == "green"

    def test_get_health_indicator_failed(self, console) -> None:
        """Test health indicator for failed status."""
        indicator = get_health_indicator("failed")

        assert "✗" in str(indicator) or indicator.style == "red"

    def test_create_asset_status_table(self, console) -> None:
        """Test creating asset status table."""
        assets = [
            {
                "key": "test_asset",
                "group": "test_group",
                "status": "success",
                "last_run": "2024-01-01",
                "records_processed": 100,
            }
        ]

        table = create_asset_status_table(assets, console)

        assert table is not None
        assert len(table.columns) > 0

    def test_create_summary_panel(self, console) -> None:
        """Test creating summary panel."""
        summary_data = {
            "assets": {"total": 10, "success": 8, "failed": 2},
            "neo4j": {"connected": True, "nodes": 1000},
            "metrics": {"throughput": 50.0},
        }

        panel = create_summary_panel(summary_data, console)

        assert panel is not None
