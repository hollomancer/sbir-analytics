"""Progress tracking component using Rich Progress."""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from loguru import logger


class PipelineProgressTracker:
    """Progress tracker for pipeline operations using Rich Progress.

    Provides multi-task progress tracking with custom columns for
    pipeline-specific information like records processed and throughput.
    """

    def __init__(
        self,
        console: Console,
        refresh_rate: float = 0.1,
        show_percentage: bool = True,
        show_speed: bool = True,
    ) -> None:
        """Initialize progress tracker.

        Args:
            console: Rich console for output
            refresh_rate: Progress update refresh rate in seconds
            show_percentage: Show percentage completion
            show_speed: Show processing speed (throughput)
        """
        self.console = console
        self.refresh_rate = refresh_rate
        self.show_percentage = show_percentage
        self.show_speed = show_speed

        # Build progress columns
        columns = [
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
        ]

        if show_percentage:
            columns.append(TextColumn("[progress.percentage]{task.percentage:>3.0f}%"))

        columns.extend(
            [
                TextColumn("[dim]Elapsed:[/dim] {task.elapsed:.1f}s"),
                TimeRemainingColumn(),
            ]
        )

        if show_speed:
            columns.append(TextColumn("[dim]Speed:[/dim] {task.fields[speed]:.1f}/s"))

        self.progress = Progress(*columns, console=console, refresh_per_second=1 / refresh_rate)

    @contextmanager
    def track_operation(
        self,
        description: str,
        total: float | None = None,
        records_field: str = "records",
    ) -> Iterator[Callable[[dict[str, Any]], None]]:
        """Context manager for tracking a single operation.

        Args:
            description: Operation description
            total: Total units to process (None for indeterminate)
            records_field: Field name for records count in update dict

        Yields:
            Update callback function that accepts a dict with progress info
        """
        with self.progress:
            task_id = self.progress.add_task(
                description,
                total=total,
                speed=0.0,
            )

            start_time = time.time()
            last_update = start_time
            last_count = 0

            def update(info: dict[str, Any]) -> None:
                """Update progress with operation info.

                Args:
                    info: Dictionary with progress information:
                        - completed: Number of units completed
                        - records: Number of records processed (optional)
                        - message: Additional status message (optional)
                        - speed: Processing speed (optional, auto-calculated if not provided)
                """
                nonlocal last_update, last_count

                current_time = time.time()
                completed = info.get("completed", 0)
                records = info.get(records_field, info.get("records", completed))

                # Calculate speed if not provided
                if "speed" in info:
                    speed = info["speed"]
                else:
                    elapsed = current_time - start_time
                    if elapsed > 0:
                        speed = records / elapsed
                    else:
                        speed = 0.0

                # Update progress
                self.progress.update(
                    task_id,
                    completed=completed,
                    speed=speed,
                )

                # Update description if message provided
                if "message" in info:
                    full_description = f"{description} - {info['message']}"
                    self.progress.update(task_id, description=full_description)

                last_update = current_time
                last_count = records

            try:
                yield update
            finally:
                # Ensure task is marked complete
                if total is None:
                    # For indeterminate tasks, mark as complete
                    self.progress.update(task_id, completed=float("inf"))
                else:
                    self.progress.update(task_id, completed=total)
                # Stop progress context
                self.progress.stop()

    @contextmanager
    def track_multiple_operations(
        self, operations: list[dict[str, Any]]
    ) -> Iterator[dict[str, Callable[[dict[str, Any]], None]]]:
        """Context manager for tracking multiple parallel operations.

        Args:
            operations: List of operation dicts with 'description' and optional 'total'

        Yields:
            Dictionary mapping operation descriptions to update callbacks
        """
        # Start progress context
        self.progress.start()
        task_ids: dict[str, TaskID] = {}
        start_times: dict[str, float] = {}

        # Create tasks for all operations
        for op in operations:
            desc = op["description"]
            total = op.get("total")
            task_id = self.progress.add_task(desc, total=total, speed=0.0)
            task_ids[desc] = task_id
            start_times[desc] = time.time()

        def create_update_callback(desc: str) -> Callable[[dict[str, Any]], None]:
            """Create update callback for a specific operation.

            Args:
                desc: Operation description

            Returns:
                Update callback function
            """
            task_id = task_ids[desc]
            start_time = start_times[desc]

            def update(info: dict[str, Any]) -> None:
                """Update progress for this operation."""
                completed = info.get("completed", 0)
                records = info.get("records", completed)

                # Calculate speed
                elapsed = time.time() - start_time
                speed = records / elapsed if elapsed > 0 else 0.0

                self.progress.update(
                    task_id,
                    completed=completed,
                    speed=speed,
                )

                if "message" in info:
                    full_description = f"{desc} - {info['message']}"
                    self.progress.update(task_id, description=full_description)

            return update

        # Build update callbacks dict
        update_callbacks = {
            op["description"]: create_update_callback(op["description"])
            for op in operations
        }

        try:
            yield update_callbacks
        finally:
            # Mark all tasks as complete
            for task_id in task_ids.values():
                if self.progress.tasks[task_id].total:
                    # Only update if task has a total
                    total = self.progress.tasks[task_id].total
                    self.progress.update(task_id, completed=total)
            # Stop progress context
            self.progress.stop()

    def update_task(
        self,
        task_id: TaskID,
        completed: float | None = None,
        description: str | None = None,
        records: int | None = None,
        speed: float | None = None,
    ) -> None:
        """Update a specific task.

        Args:
            task_id: Task ID from add_task
            completed: Number of units completed
            description: New task description
            records: Number of records processed
            speed: Processing speed (calculated if not provided)
        """
        update_dict: dict[str, Any] = {}

        if completed is not None:
            update_dict["completed"] = completed

        if description is not None:
            update_dict["description"] = description

        if speed is not None:
            update_dict["speed"] = speed
        elif records is not None and completed is not None:
            # Calculate speed from records
            task = self.progress.tasks[task_id]
            if hasattr(task, "start_time") and task.start_time:
                elapsed = time.time() - task.start_time
                update_dict["speed"] = records / elapsed if elapsed > 0 else 0.0

        self.progress.update(task_id, **update_dict)


def create_progress_tracker(
    console: Console,
    refresh_rate: float = 0.1,
    show_percentage: bool = True,
    show_speed: bool = True,
) -> PipelineProgressTracker:
    """Create a progress tracker instance.

    Args:
        console: Rich console
        refresh_rate: Refresh rate in seconds
        show_percentage: Show percentage
        show_speed: Show speed

    Returns:
        PipelineProgressTracker instance
    """
    return PipelineProgressTracker(
        console=console,
        refresh_rate=refresh_rate,
        show_percentage=show_percentage,
        show_speed=show_speed,
    )

