"""Metrics display component with Rich formatting."""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.table import Table
from rich.text import Text


def format_threshold_indicator(value: float, thresholds: dict[str, float]) -> Text:
    """Format value with color-coded threshold indicator.

    Args:
        value: Value to format
        thresholds: Dict with 'low', 'medium', 'high' threshold values

    Returns:
        Rich Text with colored indicator
    """
    low = thresholds.get("low", 0.0)
    medium = thresholds.get("medium", 0.5)
    high = thresholds.get("high", 1.0)

    if value >= high:
        style = "green"
        indicator = "✓"
    elif value >= medium:
        style = "yellow"
        indicator = "⚠"
    else:
        style = "red"
        indicator = "✗"

    text = Text()
    text.append(indicator, style=style)
    text.append(f" {value:.2f}")
    return text


def create_metrics_table(
    metrics: list[dict[str, Any]],
    console: Console,
    title: str = "Performance Metrics",
    show_throughput: bool = True,
    show_memory: bool = True,
) -> Table:
    """Create a formatted metrics table.

    Args:
        metrics: List of metric dictionaries
        console: Rich console
        title: Table title
        show_throughput: Show throughput column
        show_memory: Show memory column

    Returns:
        Rich Table instance
    """
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Timestamp", style="dim")
    table.add_column("Operation", style="cyan")
    table.add_column("Duration (s)", justify="right")
    table.add_column("Records", justify="right")

    if show_throughput:
        table.add_column("Throughput", justify="right", style="dim")

    if show_memory:
        table.add_column("Memory (MB)", justify="right", style="dim")

    table.add_column("Status", justify="center")

    for metric in metrics:
        timestamp = metric.get("timestamp", "Unknown")
        operation = metric.get("asset_key") or metric.get("operation", "Unknown")
        duration = metric.get("duration_seconds", 0)
        records = metric.get("records_processed", 0)
        success = metric.get("success", False)

        row_data = [
            str(timestamp),
            operation,
            f"{duration:.2f}" if duration else "-",
            str(records) if records else "-",
        ]

        if show_throughput:
            throughput = records / duration if duration > 0 else 0
            row_data.append(f"{throughput:.1f}/s" if throughput > 0 else "-")

        if show_memory:
            memory = metric.get("peak_memory_mb", 0)
            row_data.append(f"{memory:.1f}" if memory else "-")

        status_text = "[green]✓[/green]" if success else "[red]✗[/red]"
        row_data.append(status_text)

        table.add_row(*row_data)

    return table

