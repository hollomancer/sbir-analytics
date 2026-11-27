"""Performance monitoring package.

This package provides tools for tracking execution time and memory usage.

Epistemic tier: pipelines. This is the package default that ``sbir_etl.utils`` states
for deterministic shared helpers.
"""

from .core import (
    PerformanceMonitor,
    monitor_block,
    monitor_memory,
    performance_monitor,
    time_block,
    time_function,
)

EPISTEMIC_TIER = "pipelines"


__all__ = [
    "PerformanceMonitor",
    "performance_monitor",
    "time_function",
    "monitor_memory",
    "time_block",
    "monitor_block",
]
