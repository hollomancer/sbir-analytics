# sbir-etl/src/utils/performance_monitor.py
"""Performance monitoring utilities for SBIR ETL operations.

Provides decorators and context managers for tracking memory usage, execution time,
and other performance metrics during data processing operations.

Usage examples:
    from src.utils.performance_monitor import performance_monitor, time_block, monitor_block

    @performance_monitor.time_function
    def my_task(...):
        ...

    with time_block("phase1"):
        do_work()

    with monitor_block("heavy_phase"):
        do_heavy_work()
"""

from __future__ import annotations

import contextlib
import functools
import json
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

# psutil is optional; when available we record memory usage
try:
    import psutil

    _PSUTIL_AVAILABLE = True
except Exception:
    psutil = None  # type: ignore
    _PSUTIL_AVAILABLE = False


class PerformanceMonitor:
    """Performance monitoring utility for tracking resource usage and timing."""

    def __init__(self) -> None:
        """Initialize performance monitor."""
        # metrics: name -> list of measurement dicts
        self.metrics: dict[str, list[dict[str, Any]]] = {}
        self._process = psutil.Process() if _PSUTIL_AVAILABLE else None

    # -----------------------
    # Decorators
    # -----------------------
    def time_function(self, func: Callable) -> Callable:
        """Decorator to measure elapsed time for a function call.

        Records a metric entry under the function name with start/end/duration.
        """

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                end = time.time()
                duration = end - start
                self._record(
                    func.__name__,
                    {
                        "operation": "function_call",
                        "start_time": start,
                        "end_time": end,
                        "duration": duration,
                    },
                )

        return wrapper

    def monitor_memory(self, func: Callable) -> Callable:
        """Decorator to record memory usage before/after function execution.

        When psutil is not available this decorator falls back to timing only.
        """

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not _PSUTIL_AVAILABLE or self._process is None:
                # Fallback to timing-only
                return self.time_function(func)(*args, **kwargs)

            start_time = time.time()
            start_mem = self._get_memory_mb()
            try:
                return func(*args, **kwargs)
            finally:
                end_time = time.time()
                end_mem = self._get_memory_mb()
                # peak memory best-effort if available via memory_info (platform dependent)
                peak_mem = self._get_peak_memory_mb()
                self._record(
                    f"{func.__name__}_memory",
                    {
                        "operation": "memory_monitor",
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration": end_time - start_time,
                        "start_memory_mb": start_mem,
                        "end_memory_mb": end_mem,
                        "peak_memory_mb": peak_mem,
                        "memory_delta_mb": end_mem - start_mem,
                    },
                )

        return wrapper

    # -----------------------
    # Context managers
    # -----------------------
    @contextmanager
    def time_block(self, name: str):
        """Context manager to time a block of code.

        Example:
            with performance_monitor.time_block("import_csv"):
                import_csv(...)
        """
        start = time.time()
        try:
            yield
        finally:
            end = time.time()
            duration = end - start
            self._record(
                name,
                {
                    "operation": "time_block",
                    "start_time": start,
                    "end_time": end,
                    "duration": duration,
                },
            )

    @contextmanager
    def monitor_block(self, name: str):
        """Context manager to measure time and memory for a block of code.

        If psutil is unavailable, falls back to time_block behavior.
        """
        if not _PSUTIL_AVAILABLE or self._process is None:
            with self.time_block(name):
                yield
            return

        start_time = time.time()
        start_mem = self._get_memory_mb()
        try:
            yield
        finally:
            end_time = time.time()
            end_mem = self._get_memory_mb()
            peak_mem = self._get_peak_memory_mb()
            self._record(
                name,
                {
                    "operation": "monitor_block",
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": end_time - start_time,
                    "start_memory_mb": start_mem,
                    "end_memory_mb": end_mem,
                    "peak_memory_mb": peak_mem,
                    "memory_delta_mb": end_mem - start_mem,
                },
            )

    # -----------------------
    # Helpers / introspection
    # -----------------------
    def _get_memory_mb(self) -> float:
        """Return current resident memory usage (MB) for the running process."""
        if not self._process:
            return 0.0
        try:
            return float(self._process.memory_info().rss) / (1024 * 1024)
        except Exception:
            return 0.0

    def _get_peak_memory_mb(self) -> float:
        """Return a best-effort peak memory usage (MB). Implementation is platform dependent."""
        if not self._process:
            return 0.0
        try:
            # Some platforms expose peak_wset/peak_rss; fall back to rss if not available
            info = self._process.memory_info()
            peak = getattr(info, "peak_wset", None) or getattr(info, "peak_rss", None) or info.rss
            return float(peak) / (1024 * 1024)
        except Exception:
            try:
                return float(self._process.memory_info().rss) / (1024 * 1024)
            except Exception:
                return 0.0

    def _record(self, name: str, data: dict[str, Any]) -> None:
        """Record a metric entry for a named operation."""
        bucket = self.metrics.setdefault(name, [])
        # enrich with timestamp
        data.setdefault("timestamp", time.time())
        bucket.append(data)

    def get_latest_metric(self, name: str) -> dict[str, Any] | None:
        """Return the most recent metric entry for a given name, or None."""
        bucket = self.metrics.get(name)
        if not bucket:
            return None
        return bucket[-1]

    def get_metrics_summary(self) -> dict[str, dict[str, Any]]:
        """Return a summarized view of collected metrics.

        Summary includes count, total/avg/max duration, memory stats where available.
        """
        summary: dict[str, dict[str, Any]] = {}
        for name, entries in self.metrics.items():
            durations = [e.get("duration", 0.0) for e in entries if "duration" in e]
            memory_deltas = [
                e.get("memory_delta_mb", 0.0) for e in entries if "memory_delta_mb" in e
            ]
            peak_memories = [e.get("peak_memory_mb", 0.0) for e in entries if "peak_memory_mb" in e]
            summary[name] = {
                "count": len(entries),
                "total_duration": sum(durations),
                "avg_duration": (sum(durations) / len(durations)) if durations else 0.0,
                "max_duration": max(durations) if durations else 0.0,
                "total_memory_delta_mb": sum(memory_deltas),
                "avg_memory_delta_mb": (sum(memory_deltas) / len(memory_deltas))
                if memory_deltas
                else 0.0,
                "max_peak_memory_mb": max(peak_memories) if peak_memories else 0.0,
                "latest": entries[-1] if entries else None,
            }
        return summary

    def reset_metrics(self) -> None:
        """Clear all collected metrics."""
        self.metrics.clear()

    def export_metrics(self, filepath: str) -> None:
        """Export raw metrics to a JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.metrics, f, indent=2, default=str)

    def get_performance_report(self) -> dict[str, Any]:
        """Return a comprehensive performance report with summary and overall stats."""
        summary = self.get_metrics_summary()
        total_operations = sum(s.get("count", 0) for s in summary.values())
        total_duration = sum(s.get("total_duration", 0.0) for s in summary.values())
        avg_operation_duration = (total_duration / total_operations) if total_operations else 0.0
        return {
            "summary": summary,
            "overall": {
                "total_operations": total_operations,
                "total_duration": total_duration,
                "avg_operation_duration": avg_operation_duration,
            },
            "psutil_available": _PSUTIL_AVAILABLE,
            "timestamp": time.time(),
        }


# Global instance and convenience helpers
performance_monitor = PerformanceMonitor()


def time_function(func: Callable) -> Callable:
    """Module-level convenience decorator for timing a function."""
    return performance_monitor.time_function(func)


def monitor_memory(func: Callable) -> Callable:
    """Module-level convenience decorator for memory monitoring."""
    return performance_monitor.monitor_memory(func)


@contextlib.contextmanager
def time_block(name: str):
    """Module-level convenience context manager to time a block."""
    with performance_monitor.time_block(name):
        yield


@contextlib.contextmanager
def monitor_block(name: str):
    """Module-level convenience context manager to monitor time & memory for a block."""
    with performance_monitor.monitor_block(name):
        yield
