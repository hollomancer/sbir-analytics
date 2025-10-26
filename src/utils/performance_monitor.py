sbir - etl / src / utils / performance_monitor.py
"""Performance monitoring utilities for SBIR ETL operations.

Provides decorators and context managers for tracking memory usage, execution time,
and other performance metrics during data processing operations.
"""

import functools
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional

try:
    import psutil

    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False
    psutil = None


class PerformanceMonitor:
    """Performance monitoring utility for tracking resource usage and timing."""

    def __init__(self):
        """Initialize performance monitor."""
        self.metrics: Dict[str, Dict[str, Any]] = {}
        self._process = psutil.Process() if _PSUTIL_AVAILABLE else None

    def time_function(self, func: Callable) -> Callable:
        """Decorator to time function execution.

        Args:
            func: Function to time

        Returns:
            Wrapped function that records timing metrics
        """

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.time()
                duration = end_time - start_time

                self._record_metric(
                    func.__name__,
                    {
                        "duration": duration,
                        "start_time": start_time,
                        "end_time": end_time,
                        "operation": "function_call",
                    },
                )

        return wrapper

    def monitor_memory(self, func: Callable) -> Callable:
        """Decorator to monitor memory usage during function execution.

        Args:
            func: Function to monitor

        Returns:
            Wrapped function that records memory metrics
        """

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not _PSUTIL_AVAILABLE:
                # Fallback without memory monitoring
                return func(*args, **kwargs)

            start_mem = self._get_memory_usage()
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                return result
            finally:
                end_time = time.time()
                end_mem = self._get_memory_usage()
                peak_mem = self._get_peak_memory()

                self._record_metric(
                    f"{func.__name__}_memory",
                    {
                        "start_memory_mb": start_mem,
                        "end_memory_mb": end_mem,
                        "peak_memory_mb": peak_mem,
                        "memory_delta_mb": end_mem - start_mem,
                        "duration": end_time - start_time,
                        "operation": "memory_monitor",
                    },
                )

        return wrapper

    @contextmanager
    def time_block(self, name: str):
        """Context manager to time a block of code.

        Args:
            name: Name for the timing block
        """
        start_time = time.time()
        try:
            yield
        finally:
            end_time = time.time()
            duration = end_time - start_time

            self._record_metric(
                name,
                {
                    "duration": duration,
                    "start_time": start_time,
                    "end_time": end_time,
                    "operation": "time_block",
                },
            )

    @contextmanager
    def monitor_block(self, name: str):
        """Context manager to monitor memory and time for a block of code.

        Args:
            name: Name for the monitoring block
        """
        if not _PSUTIL_AVAILABLE:
            # Fallback to timing only
            with self.time_block(name):
                yield
            return

        start_mem = self._get_memory_usage()
        start_time = time.time()

        try:
            yield
        finally:
            end_time = time.time()
            end_mem = self._get_memory_usage()
            peak_mem = self._get_peak_memory()

            self._record_metric(
                name,
                {
                    "duration": end_time - start_time,
                    "start_memory_mb": start_mem,
                    "end_memory_mb": end_mem,
                    "peak_memory_mb": peak_mem,
                    "memory_delta_mb": end_mem - start_mem,
                    "start_time": start_time,
                    "end_time": end_time,
                    "operation": "monitor_block",
                },
            )

    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB."""
        if not self._process:
            return 0.0
        return self._process.memory_info().rss / (1024 * 1024)

    def _get_peak_memory(self) -> float:
        """Get peak memory usage in MB since process start."""
        if not self._process:
            return 0.0
        return self._process.memory_info().peak_wset / (1024 * 1024)

    def _record_metric(self, name: str, data: Dict[str, Any]):
        """Record a performance metric.

        Args:
            name: Metric name
            data: Metric data dictionary
        """
        if name not in self.metrics:
            self.metrics[name] = []

        # Add timestamp if not present
        if "timestamp" not in data:
            data["timestamp"] = time.time()

        self.metrics[name].append(data)

    def get_latest_metric(self, name: str) -> Optional[Dict[str, Any]]:
        """Get the latest metric for a given name.

        Args:
            name: Metric name

        Returns:
            Latest metric data or None if not found
        """
        if name in self.metrics and self.metrics[name]:
            return self.metrics[name][-1]
        return None

    def get_metrics_summary(self) -> Dict[str, Dict[str, Any]]:
        """Get summary of all metrics.

        Returns:
            Dictionary with metric summaries
        """
        summary = {}

        for name, measurements in self.metrics.items():
            if not measurements:
                continue

            durations = [m.get("duration", 0) for m in measurements if "duration" in m]
            memory_deltas = [
                m.get("memory_delta_mb", 0) for m in measurements if "memory_delta_mb" in m
            ]
            peak_memories = [
                m.get("peak_memory_mb", 0) for m in measurements if "peak_memory_mb" in m
            ]

            summary[name] = {
                "count": len(measurements),
                "total_duration": sum(durations),
                "avg_duration": sum(durations) / len(durations) if durations else 0,
                "max_duration": max(durations) if durations else 0,
                "total_memory_delta": sum(memory_deltas),
                "avg_memory_delta": sum(memory_deltas) / len(memory_deltas) if memory_deltas else 0,
                "max_peak_memory": max(peak_memories) if peak_memories else 0,
                "latest": measurements[-1] if measurements else None,
            }

        return summary

    def reset_metrics(self):
        """Reset all collected metrics."""
        self.metrics.clear()

    def export_metrics(self, filepath: str):
        """Export metrics to JSON file.

        Args:
            filepath: Path to export metrics
        """
        import json

        with open(filepath, "w") as f:
            json.dump(self.metrics, f, indent=2, default=str)

    def get_performance_report(self) -> Dict[str, Any]:
        """Generate a comprehensive performance report.

        Returns:
            Performance report dictionary
        """
        summary = self.get_metrics_summary()

        # Calculate overall statistics
        total_operations = sum(stats["count"] for stats in summary.values())
        total_duration = sum(stats["total_duration"] for stats in summary.values())

        return {
            "summary": summary,
            "overall": {
                "total_operations": total_operations,
                "total_duration": total_duration,
                "avg_operation_duration": total_duration / total_operations
                if total_operations > 0
                else 0,
            },
            "timestamp": time.time(),
            "psutil_available": _PSUTIL_AVAILABLE,
        }


# Global performance monitor instance
performance_monitor = PerformanceMonitor()


def time_function(func: Callable) -> Callable:
    """Global decorator to time function execution."""
    return performance_monitor.time_function(func)


def monitor_memory(func: Callable) -> Callable:
    """Global decorator to monitor memory usage."""
    return performance_monitor.monitor_memory(func)


@contextmanager
def time_block(name: str):
    """Global context manager to time code blocks."""
    with performance_monitor.time_block(name):
        yield


@contextmanager
def monitor_block(name: str):
    """Global context manager to monitor memory and time."""
    with performance_monitor.monitor_block(name):
        yield
