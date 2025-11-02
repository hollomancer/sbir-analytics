"""Unit tests for CLI display components."""

from unittest.mock import Mock

import pytest

from src.cli.display.metrics import create_metrics_table, format_threshold_indicator
from src.cli.display.progress import PipelineProgressTracker, create_progress_tracker
from src.cli.display.status import (
    create_asset_status_table,
    create_summary_panel,
    get_health_indicator,
)


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

