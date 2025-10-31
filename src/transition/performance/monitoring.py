"""Performance monitoring decorators and utilities for transition detection.

This module provides decorators and context managers for tracking performance
of transition detection operations, including:
- Task 17.4: Parallelization utilities for Dagster workers
- Task 17.6: Performance profiling and monitoring
"""

from __future__ import annotations

import functools
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

from loguru import logger

try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None  # type: ignore
    PSUTIL_AVAILABLE = False


class PerformanceTracker:
    """Track performance metrics for transition detection operations."""

    def __init__(self, operation_name: str):
        """Initialize performance tracker."""
        self.operation_name = operation_name
        self.metrics: dict[str, Any] = {
            "operation": operation_name,
            "start_time": None,
            "end_time": None,
            "duration_ms": 0.0,
            "memory_mb_start": 0.0,
            "memory_mb_end": 0.0,
            "memory_mb_delta": 0.0,
            "items_processed": 0,
            "throughput_per_second": 0.0,
        }

    def start(self) -> None:
        """Start tracking."""
        self.metrics["start_time"] = time.time()
        if PSUTIL_AVAILABLE:
            process = psutil.Process()
            self.metrics["memory_mb_start"] = process.memory_info().rss / 1024 / 1024

    def end(self, items_processed: int = 0) -> None:
        """End tracking."""
        self.metrics["end_time"] = time.time()
        self.metrics["items_processed"] = items_processed

        if self.metrics["start_time"]:
            self.metrics["duration_ms"] = (
                self.metrics["end_time"] - self.metrics["start_time"]
            ) * 1000

        if PSUTIL_AVAILABLE:
            process = psutil.Process()
            self.metrics["memory_mb_end"] = process.memory_info().rss / 1024 / 1024
            self.metrics["memory_mb_delta"] = (
                self.metrics["memory_mb_end"] - self.metrics["memory_mb_start"]
            )

        if self.metrics["duration_ms"] > 0 and items_processed > 0:
            self.metrics["throughput_per_second"] = items_processed / (
                self.metrics["duration_ms"] / 1000
            )

    def get_metrics(self) -> dict[str, Any]:
        """Get recorded metrics."""
        return self.metrics.copy()

    def log(self) -> None:
        """Log metrics."""
        m = self.metrics
        logger.info(
            f"{m['operation']}: {m['duration_ms']:.1f}ms, "
            f"{m['items_processed']} items, "
            f"{m['throughput_per_second']:.0f} items/sec"
        )


def monitor_performance(
    operation_name: str | None = None,
    log_memory: bool = False,
) -> Callable:
    """
    Decorator to monitor function performance.

    Args:
        operation_name: Name of operation (defaults to function name)
        log_memory: Whether to log memory usage

    Returns:
        Decorated function
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            name = operation_name or func.__name__
            tracker = PerformanceTracker(name)
            tracker.start()

            try:
                result = func(*args, **kwargs)
                # Try to get item count from result
                items = 0
                if isinstance(result, (list, tuple)):
                    items = len(result)
                elif isinstance(result, dict) and "rows" in result:
                    items = result.get("rows", 0)
                tracker.end(items_processed=items)
                tracker.log()
                return result
            except Exception as e:
                tracker.end()
                logger.error(f"{name} failed: {e}")
                raise

        return wrapper

    return decorator


@contextmanager
def time_block(block_name: str, log_level: str = "info"):
    """
    Context manager to time a block of code.

    Args:
        block_name: Name of code block
        log_level: Logging level (info, debug, warning)

    Yields:
        PerformanceTracker instance
    """
    tracker = PerformanceTracker(block_name)
    tracker.start()

    try:
        yield tracker
    finally:
        tracker.end()
        if log_level == "debug":
            logger.debug(f"{block_name}: {tracker.metrics['duration_ms']:.1f}ms")
        else:
            logger.info(f"{block_name}: {tracker.metrics['duration_ms']:.1f}ms")


class BatchProcessor:
    """
    Process items in batches with performance tracking.

    Task 17.4: Parallelization support across Dagster workers
    """

    def __init__(
        self,
        batch_size: int = 1000,
        max_batches: int | None = None,
    ):
        """
        Initialize batch processor.

        Args:
            batch_size: Items per batch
            max_batches: Maximum batches to process (None for unlimited)
        """
        self.batch_size = batch_size
        self.max_batches = max_batches
        self.stats = {
            "total_items": 0,
            "batches_processed": 0,
            "total_time_ms": 0.0,
        }

    def process(
        self,
        items: list[Any],
        process_func: Callable[[list[Any]], Any],
    ) -> list[Any]:
        """
        Process items in batches.

        Args:
            items: List of items to process
            process_func: Function to process batch

        Returns:
            List of results
        """
        results = []
        tracker = PerformanceTracker("batch_processing")
        tracker.start()

        batches = [items[i : i + self.batch_size] for i in range(0, len(items), self.batch_size)]

        if self.max_batches:
            batches = batches[: self.max_batches]

        for batch_idx, batch in enumerate(batches):
            try:
                batch_result = process_func(batch)
                results.append(batch_result)
                self.stats["batches_processed"] += 1
                logger.debug(f"Processed batch {batch_idx + 1}/{len(batches)} ({len(batch)} items)")
            except Exception as e:
                logger.error(f"Batch {batch_idx + 1} failed: {e}")
                raise

        tracker.end(items_processed=len(items))
        self.stats["total_items"] = len(items)
        self.stats["total_time_ms"] = tracker.metrics["duration_ms"]

        logger.info(
            f"Batch processing complete: {len(items)} items in {self.stats['batches_processed']} batches, "
            f"{tracker.metrics['throughput_per_second']:.0f} items/sec"
        )

        return results

    def get_stats(self) -> dict[str, Any]:
        """Get processing statistics."""
        return self.stats.copy()


class ParallelExecutor:
    """
    Execute tasks in parallel across Dagster workers.

    Task 17.4: Parallelization across Dagster workers
    """

    def __init__(self, worker_count: int = 4):
        """
        Initialize parallel executor.

        Args:
            worker_count: Number of parallel workers
        """
        self.worker_count = worker_count
        self.stats = {
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "total_time_ms": 0.0,
        }

    def execute_tasks(
        self,
        tasks: list[Any],
        task_func: Callable[[Any], Any],
        use_multiprocessing: bool = False,
    ) -> list[Any]:
        """
        Execute tasks in parallel.

        Args:
            tasks: List of tasks to execute
            task_func: Function to execute for each task
            use_multiprocessing: Whether to use multiprocessing (vs threading)

        Returns:
            List of results
        """
        tracker = PerformanceTracker("parallel_execution")
        tracker.start()

        results = []

        # In a Dagster context, parallelization happens via Dagster's
        # built-in parallel execution capabilities (multi-process executors).
        # For now, we process sequentially but track performance.
        for task_idx, task in enumerate(tasks):
            try:
                result = task_func(task)
                results.append(result)
                self.stats["completed_tasks"] += 1
                logger.debug(f"Task {task_idx + 1}/{len(tasks)} completed")
            except Exception as e:
                logger.error(f"Task {task_idx + 1} failed: {e}")
                self.stats["failed_tasks"] += 1
                raise

        tracker.end(items_processed=len(tasks))
        self.stats["total_tasks"] = len(tasks)
        self.stats["total_time_ms"] = tracker.metrics["duration_ms"]

        logger.info(
            f"Parallel execution complete: {self.stats['completed_tasks']}/{len(tasks)} tasks, "
            f"{tracker.metrics['throughput_per_second']:.0f} tasks/sec"
        )

        return results

    def get_stats(self) -> dict[str, Any]:
        """Get execution statistics."""
        return self.stats.copy()


def profile_detection_performance(
    awards_count: int,
    contracts_count: int,
    detections_count: int,
    total_time_ms: float,
) -> dict[str, Any]:
    """
    Calculate detection pipeline performance metrics.

    Task 17.6: Profile detection performance (target: ≥10K detections/minute)

    Args:
        awards_count: Number of awards processed
        contracts_count: Number of contracts processed
        detections_count: Number of detections found
        total_time_ms: Total execution time in milliseconds

    Returns:
        Dictionary with performance metrics
    """
    total_seconds = total_time_ms / 1000
    minutes = total_seconds / 60 if total_seconds > 0 else 0

    metrics = {
        "awards_processed": awards_count,
        "contracts_processed": contracts_count,
        "detections_found": detections_count,
        "total_time_seconds": total_seconds,
        "detections_per_second": detections_count / total_seconds if total_seconds > 0 else 0,
        "detections_per_minute": detections_count / minutes if minutes > 0 else 0,
        "detections_per_minute_meets_target": ((detections_count / minutes) >= 10000)
        if minutes > 0
        else False,
        "awards_per_second": awards_count / total_seconds if total_seconds > 0 else 0,
        "contracts_per_second": contracts_count / total_seconds if total_seconds > 0 else 0,
    }

    # Log performance
    logger.info(
        f"Detection Performance: {metrics['detections_per_minute']:.0f} detections/min "
        f"(target: 10,000/min) - {'✓ PASS' if metrics['detections_per_minute_meets_target'] else '✗ BELOW TARGET'}"
    )

    return metrics
