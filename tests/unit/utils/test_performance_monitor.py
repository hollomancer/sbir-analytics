"""Unit tests for performance monitoring utilities.

Tests cover:
- PerformanceMonitor initialization
- Function timing decorator
- Memory monitoring decorator (with and without psutil)
- Time block context manager
- Monitor block context manager
- Metrics recording and retrieval
- Summary generation
- Export functionality
"""

import time
from unittest.mock import Mock, patch

import pytest

from src.utils.performance_monitor import PerformanceMonitor


pytestmark = pytest.mark.fast


@pytest.fixture
def monitor():
    """Create a performance monitor instance."""
    return PerformanceMonitor()


class TestPerformanceMonitorInitialization:
    """Tests for PerformanceMonitor initialization."""

    def test_init_creates_empty_metrics(self):
        """Test initialization creates empty metrics dict."""
        monitor = PerformanceMonitor()

        assert isinstance(monitor.metrics, dict)
        assert len(monitor.metrics) == 0

    @patch("src.utils.performance_monitor._PSUTIL_AVAILABLE", True)
    @patch("src.utils.performance_monitor.psutil")
    def test_init_with_psutil(self, mock_psutil):
        """Test initialization with psutil available."""
        mock_process = Mock()
        mock_psutil.Process.return_value = mock_process

        monitor = PerformanceMonitor()

        assert monitor._process is not None
        mock_psutil.Process.assert_called_once()

    @patch("src.utils.performance_monitor._PSUTIL_AVAILABLE", False)
    def test_init_without_psutil(self):
        """Test initialization without psutil."""
        monitor = PerformanceMonitor()

        assert monitor._process is None


class TestTimeFunctionDecorator:
    """Tests for time_function decorator."""

    def test_time_function_basic(self, monitor):
        """Test timing a simple function."""

        @monitor.time_function
        def simple_func():
            return 42

        result = simple_func()

        assert result == 42
        assert "simple_func" in monitor.metrics
        assert len(monitor.metrics["simple_func"]) == 1

        metric = monitor.metrics["simple_func"][0]
        assert metric["operation"] == "function_call"
        assert "duration" in metric
        assert metric["duration"] >= 0

    def test_time_function_with_args(self, monitor):
        """Test timing function with arguments."""

        @monitor.time_function
        def add_numbers(a, b):
            return a + b

        result = add_numbers(10, 20)

        assert result == 30
        assert "add_numbers" in monitor.metrics

    def test_time_function_with_kwargs(self, monitor):
        """Test timing function with keyword arguments."""

        @monitor.time_function
        def greet(name, greeting="Hello"):
            return f"{greeting}, {name}!"

        result = greet("World", greeting="Hi")

        assert result == "Hi, World!"
        assert "greet" in monitor.metrics

    def test_time_function_with_delay(self, monitor):
        """Test timing function with actual delay."""

        @monitor.time_function
        def slow_func():
            time.sleep(0.01)
            return "done"

        result = slow_func()

        assert result == "done"
        metric = monitor.metrics["slow_func"][0]
        assert metric["duration"] >= 0.01

    def test_time_function_multiple_calls(self, monitor):
        """Test timing same function multiple times."""

        @monitor.time_function
        def repeated_func():
            return True

        repeated_func()
        repeated_func()
        repeated_func()

        assert len(monitor.metrics["repeated_func"]) == 3

    def test_time_function_with_exception(self, monitor):
        """Test timing function that raises exception."""

        @monitor.time_function
        def failing_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_func()

        # Metric should still be recorded
        assert "failing_func" in monitor.metrics
        assert len(monitor.metrics["failing_func"]) == 1


class TestMonitorMemoryDecorator:
    """Tests for monitor_memory decorator."""

    @patch("src.utils.performance_monitor._PSUTIL_AVAILABLE", True)
    @patch("src.utils.performance_monitor.psutil")
    def test_monitor_memory_with_psutil(self, mock_psutil):
        """Test memory monitoring with psutil available."""
        mock_process = Mock()
        mock_process.memory_info.return_value.rss = 100 * 1024 * 1024  # 100 MB
        mock_psutil.Process.return_value = mock_process

        monitor = PerformanceMonitor()

        @monitor.monitor_memory
        def memory_func():
            return "result"

        result = memory_func()

        assert result == "result"
        assert "memory_func_memory" in monitor.metrics

        metric = monitor.metrics["memory_func_memory"][0]
        assert metric["operation"] == "memory_monitor"
        assert "start_memory_mb" in metric
        assert "end_memory_mb" in metric
        assert "memory_delta_mb" in metric

    @patch("src.utils.performance_monitor._PSUTIL_AVAILABLE", False)
    def test_monitor_memory_without_psutil(self, monitor):
        """Test memory monitoring falls back to timing without psutil."""

        @monitor.monitor_memory
        def simple_func():
            return "result"

        result = simple_func()

        assert result == "result"
        # Should fallback to time_function behavior
        assert "simple_func" in monitor.metrics or "simple_func_memory" in monitor.metrics


class TestTimeBlockContextManager:
    """Tests for time_block context manager."""

    def test_time_block_basic(self, monitor):
        """Test timing a code block."""
        with monitor.time_block("test_block"):
            pass

        assert "test_block" in monitor.metrics
        metric = monitor.metrics["test_block"][0]
        assert metric["operation"] == "time_block"
        assert metric["duration"] >= 0

    def test_time_block_with_delay(self, monitor):
        """Test timing block with actual work."""
        with monitor.time_block("slow_block"):
            time.sleep(0.01)

        metric = monitor.metrics["slow_block"][0]
        assert metric["duration"] >= 0.01

    def test_time_block_nested(self, monitor):
        """Test nested time blocks."""
        with monitor.time_block("outer"):
            with monitor.time_block("inner"):
                pass

        assert "outer" in monitor.metrics
        assert "inner" in monitor.metrics

        outer_duration = monitor.metrics["outer"][0]["duration"]
        inner_duration = monitor.metrics["inner"][0]["duration"]
        assert outer_duration >= inner_duration

    def test_time_block_with_exception(self, monitor):
        """Test time block with exception."""
        with pytest.raises(ValueError):
            with monitor.time_block("error_block"):
                raise ValueError("Test error")

        # Metric should still be recorded
        assert "error_block" in monitor.metrics

    def test_time_block_multiple_uses(self, monitor):
        """Test using same block name multiple times."""
        with monitor.time_block("repeated_block"):
            pass

        with monitor.time_block("repeated_block"):
            pass

        assert len(monitor.metrics["repeated_block"]) == 2


class TestMonitorBlockContextManager:
    """Tests for monitor_block context manager."""

    @patch("src.utils.performance_monitor._PSUTIL_AVAILABLE", True)
    @patch("src.utils.performance_monitor.psutil")
    def test_monitor_block_with_psutil(self, mock_psutil):
        """Test monitoring block with psutil."""
        mock_process = Mock()
        mock_process.memory_info.return_value.rss = 100 * 1024 * 1024
        mock_psutil.Process.return_value = mock_process

        monitor = PerformanceMonitor()

        with monitor.monitor_block("test_monitor"):
            pass

        assert "test_monitor" in monitor.metrics
        metric = monitor.metrics["test_monitor"][0]
        assert "start_memory_mb" in metric
        assert "end_memory_mb" in metric

    @patch("src.utils.performance_monitor._PSUTIL_AVAILABLE", False)
    def test_monitor_block_without_psutil(self, monitor):
        """Test monitor block falls back to timing."""
        with monitor.monitor_block("fallback_block"):
            pass

        # Should record timing even without psutil
        assert "fallback_block" in monitor.metrics


class TestMetricsRecording:
    """Tests for metrics recording and retrieval."""

    def test_get_metrics_for_operation(self, monitor):
        """Test retrieving metrics for specific operation."""

        @monitor.time_function
        def test_func():
            pass

        test_func()
        test_func()

        metrics = monitor.get_metrics("test_func")

        assert len(metrics) == 2
        assert all(m["operation"] == "function_call" for m in metrics)

    def test_get_metrics_nonexistent(self, monitor):
        """Test retrieving metrics for nonexistent operation."""
        metrics = monitor.get_metrics("nonexistent")

        assert metrics == []

    def test_get_all_metrics(self, monitor):
        """Test retrieving all metrics."""

        @monitor.time_function
        def func1():
            pass

        @monitor.time_function
        def func2():
            pass

        func1()
        func2()

        all_metrics = monitor.get_all_metrics()

        assert "func1" in all_metrics
        assert "func2" in all_metrics

    def test_clear_metrics(self, monitor):
        """Test clearing all metrics."""

        @monitor.time_function
        def test_func():
            pass

        test_func()
        assert len(monitor.metrics) > 0

        monitor.clear_metrics()

        assert len(monitor.metrics) == 0

    def test_clear_specific_metric(self, monitor):
        """Test clearing specific metric."""

        @monitor.time_function
        def func1():
            pass

        @monitor.time_function
        def func2():
            pass

        func1()
        func2()

        monitor.clear_metrics("func1")

        assert "func1" not in monitor.metrics
        assert "func2" in monitor.metrics


class TestMetricsSummary:
    """Tests for metrics summary generation."""

    def test_get_summary(self, monitor):
        """Test generating metrics summary."""

        @monitor.time_function
        def test_func():
            time.sleep(0.001)

        test_func()
        test_func()
        test_func()

        summary = monitor.get_summary("test_func")

        assert summary["operation_name"] == "test_func"
        assert summary["call_count"] == 3
        assert "total_duration" in summary
        assert "avg_duration" in summary
        assert "min_duration" in summary
        assert "max_duration" in summary

    def test_get_summary_empty(self, monitor):
        """Test summary for operation with no metrics."""
        summary = monitor.get_summary("nonexistent")

        assert summary["operation_name"] == "nonexistent"
        assert summary["call_count"] == 0

    def test_get_all_summaries(self, monitor):
        """Test getting summaries for all operations."""

        @monitor.time_function
        def func1():
            pass

        @monitor.time_function
        def func2():
            pass

        func1()
        func2()

        summaries = monitor.get_all_summaries()

        assert len(summaries) == 2
        assert any(s["operation_name"] == "func1" for s in summaries)
        assert any(s["operation_name"] == "func2" for s in summaries)


class TestMetricsExport:
    """Tests for metrics export functionality."""

    def test_export_to_json(self, monitor, tmp_path):
        """Test exporting metrics to JSON."""

        @monitor.time_function
        def test_func():
            return 42

        test_func()

        output_file = tmp_path / "metrics.json"
        monitor.export_to_json(output_file)

        assert output_file.exists()

        # Verify JSON is valid
        import json

        with open(output_file) as f:
            data = json.load(f)

        assert "test_func" in data
        assert isinstance(data["test_func"], list)

    def test_export_empty_metrics(self, monitor, tmp_path):
        """Test exporting empty metrics."""
        output_file = tmp_path / "empty_metrics.json"
        monitor.export_to_json(output_file)

        assert output_file.exists()

        import json

        with open(output_file) as f:
            data = json.load(f)

        assert data == {}


class TestPerformanceMonitorIntegration:
    """Integration tests for complete workflows."""

    def test_complete_workflow(self, monitor):
        """Test complete monitoring workflow."""

        @monitor.time_function
        def process_data():
            with monitor.time_block("loading"):
                time.sleep(0.001)

            with monitor.time_block("processing"):
                time.sleep(0.001)

            return "complete"

        result = process_data()

        assert result == "complete"
        assert "process_data" in monitor.metrics
        assert "loading" in monitor.metrics
        assert "processing" in monitor.metrics

    def test_multiple_operations_summary(self, monitor):
        """Test summary with multiple operations."""

        @monitor.time_function
        def fast_func():
            pass

        @monitor.time_function
        def slow_func():
            time.sleep(0.01)

        fast_func()
        fast_func()
        slow_func()

        fast_summary = monitor.get_summary("fast_func")
        slow_summary = monitor.get_summary("slow_func")

        assert fast_summary["call_count"] == 2
        assert slow_summary["call_count"] == 1
        assert slow_summary["avg_duration"] > fast_summary["avg_duration"]
