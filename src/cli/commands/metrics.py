"""Metrics command for displaying performance data."""

from __future__ import annotations

from datetime import datetime

import typer
from rich.panel import Panel
from rich.table import Table

from ..context import CommandContext


app = typer.Typer(name="metrics", help="Display pipeline performance metrics")


@app.command()
def show(
    ctx: typer.Context,
    start_date: str | None = typer.Option(
        None, "--start-date", "-s", help="Start date (YYYY-MM-DD)"
    ),
    end_date: str | None = typer.Option(None, "--end-date", "-e", help="End date (YYYY-MM-DD)"),
    asset_group: str | None = typer.Option(None, "--group", "-g", help="Filter by asset group"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum number of records to show"),
) -> None:
    """Display performance metrics."""
    context: CommandContext = ctx.obj

    try:
        # Parse dates
        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None

        if start_date and not start:
            context.console.print(
                f"[red]Invalid start date format: {start_date}. Use YYYY-MM-DD[/red]"
            )
            raise typer.Exit(code=1)

        if end_date and not end:
            context.console.print(f"[red]Invalid end date format: {end_date}. Use YYYY-MM-DD[/red]")
            raise typer.Exit(code=1)

        # Get metrics
        metrics = context.metrics_collector.get_metrics(
            start_date=start,
            end_date=end,
            asset_group=asset_group,
        )

        if not metrics:
            context.console.print("[yellow]No metrics found for the specified criteria.[/yellow]")
            return

        # Limit results
        metrics = metrics[:limit]

        # Create table
        table = Table(title="Performance Metrics", show_header=True, header_style="bold magenta")
        table.add_column("Timestamp", style="dim")
        table.add_column("Asset/Operation", style="cyan")
        table.add_column("Duration (s)", justify="right")
        table.add_column("Records", justify="right")
        table.add_column("Throughput", justify="right", style="dim")
        table.add_column("Memory (MB)", justify="right", style="dim")
        table.add_column("Status", justify="center")

        for metric in metrics:
            timestamp = metric.get("timestamp", "Unknown")
            if isinstance(timestamp, str):
                try:
                    dt = datetime.fromisoformat(timestamp)
                    timestamp = dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    pass

            operation = metric.get("asset_key") or metric.get("operation", "Unknown")
            duration = metric.get("duration_seconds", 0)
            records = metric.get("records_processed", 0)
            throughput = records / duration if duration > 0 else 0
            memory = metric.get("peak_memory_mb", 0)
            success = metric.get("success", False)

            status_text = "[green]✓[/green]" if success else "[red]✗[/red]"

            table.add_row(
                str(timestamp),
                operation,
                f"{duration:.2f}" if duration else "-",
                str(records) if records else "-",
                f"{throughput:.1f}/s" if throughput > 0 else "-",
                f"{memory:.1f}" if memory else "-",
                status_text,
            )

        context.console.print(table)

        # Show summary if multiple metrics
        if len(metrics) > 1:
            total_records = sum(m.get("records_processed", 0) for m in metrics)
            total_duration = sum(m.get("duration_seconds", 0) for m in metrics)
            avg_throughput = total_records / total_duration if total_duration > 0 else 0
            success_count = sum(1 for m in metrics if m.get("success", False))
            success_rate = (success_count / len(metrics)) * 100 if metrics else 0

            summary = f"""
Total Records: {total_records:,}
Total Duration: {total_duration:.2f}s
Average Throughput: {avg_throughput:.1f} records/s
Success Rate: {success_rate:.1f}%
            """.strip()

            context.console.print(Panel(summary, title="Summary", border_style="blue"))

    except Exception as e:
        context.console.print(f"[red]Error getting metrics: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def latest(ctx: typer.Context) -> None:
    """Display latest aggregated pipeline metrics."""
    context: CommandContext = ctx.obj

    try:
        metrics = context.metrics_collector.get_latest_metrics()

        if not metrics:
            context.console.print("[yellow]No recent metrics available.[/yellow]")
            return

        # Create metrics display
        table = Table(
            title="Latest Pipeline Metrics", show_header=True, header_style="bold magenta"
        )
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row(
            "Enrichment Success Rate",
            f"{metrics.enrichment_success_rate * 100:.1f}%",
        )
        table.add_row(
            "Processing Throughput",
            f"{metrics.processing_throughput:.1f} records/s",
        )
        table.add_row(
            "Memory Usage",
            f"{metrics.memory_usage_mb:.1f} MB",
        )
        table.add_row(
            "Error Count",
            str(metrics.error_count),
        )
        table.add_row(
            "Last Updated",
            metrics.last_updated.strftime("%Y-%m-%d %H:%M:%S"),
        )

        context.console.print(table)

    except Exception as e:
        context.console.print(f"[red]Error getting latest metrics: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def export(
    ctx: typer.Context,
    start_date: str | None = typer.Option(
        None, "--start-date", "-s", help="Start date (YYYY-MM-DD)"
    ),
    end_date: str | None = typer.Option(None, "--end-date", "-e", help="End date (YYYY-MM-DD)"),
    asset_group: str | None = typer.Option(None, "--group", "-g", help="Filter by asset group"),
    output: str = typer.Option("metrics.json", "--output", "-o", help="Output file path"),
    format: str = typer.Option("json", "--format", "-f", help="Output format (json or csv)"),
) -> None:
    """Export metrics to file."""
    context: CommandContext = ctx.obj

    try:
        # Parse dates
        start = datetime.fromisoformat(start_date) if start_date else None
        end = datetime.fromisoformat(end_date) if end_date else None

        # Get metrics
        metrics = context.metrics_collector.get_metrics(
            start_date=start,
            end_date=end,
            asset_group=asset_group,
        )

        if not metrics:
            context.console.print("[yellow]No metrics found to export.[/yellow]")
            return

        # Export based on format
        if format.lower() == "json":
            import json

            with open(output, "w", encoding="utf-8") as f:
                json.dump(metrics, f, indent=2, default=str)

            context.console.print(f"[green]Exported {len(metrics)} metrics to {output}[/green]")

        elif format.lower() == "csv":
            import csv

            if not metrics:
                context.console.print("[yellow]No metrics to export[/yellow]")
                return

            # Get all keys from first metric
            fieldnames = set()
            for metric in metrics:
                fieldnames.update(metric.keys())

            with open(output, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=sorted(fieldnames))
                writer.writeheader()
                writer.writerows(metrics)

            context.console.print(f"[green]Exported {len(metrics)} metrics to {output}[/green]")

        else:
            context.console.print(f"[red]Unsupported format: {format}. Use 'json' or 'csv'[/red]")
            raise typer.Exit(code=1)

    except Exception as e:
        context.console.print(f"[red]Error exporting metrics: {e}[/red]")
        raise typer.Exit(code=1)


def register_command(main_app: typer.Typer) -> None:
    """Register metrics commands with main app."""
    main_app.add_typer(app, name="metrics")
