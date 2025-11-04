"""Interactive dashboard command for real-time monitoring."""

from __future__ import annotations

import signal
import sys
import time
from typing import Any

import typer
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from ..context import CommandContext
from ..display.status import create_asset_status_table, get_health_indicator


app = typer.Typer(name="dashboard", help="Interactive real-time monitoring dashboard")


def create_dashboard_layout(context: CommandContext) -> Layout:
    """Create dashboard layout with panels.

    Args:
        context: Command context

    Returns:
        Rich Layout instance
    """
    layout = Layout()

    # Split into header and body
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="body"),
    )

    # Split body into left and right columns
    layout["body"].split_row(
        Layout(name="left"),
        Layout(name="right"),
    )

    # Split left into assets and metrics
    layout["left"].split_column(
        Layout(name="assets", ratio=2),
        Layout(name="metrics", ratio=1),
    )

    # Split right into status and info
    layout["right"].split_column(
        Layout(name="status", ratio=1),
        Layout(name="info", ratio=1),
    )

    return layout


def update_dashboard(context: CommandContext, layout: Layout) -> None:
    """Update dashboard with current data.

    Args:
        context: Command context
        layout: Dashboard layout
    """
    try:
        # Header
        header_text = Text("SBIR Pipeline Dashboard", style="bold magenta")
        header_text.append(" | Press 'q' to quit, 'r' to refresh", style="dim")
        layout["header"].update(Panel(header_text, border_style="magenta"))

        # Assets panel
        try:
            assets_list = context.dagster_client.list_assets()
            # Get status for each asset
            assets_with_status = []
            for asset in assets_list[:10]:  # Limit to 10 for display
                status = context.dagster_client.get_asset_status(asset["key"])
                assets_with_status.append(
                    {
                        "key": asset["key"],
                        "group": asset.get("group", "-"),
                        "status": status.status,
                        "last_run": (
                            status.last_run.strftime("%Y-%m-%d %H:%M")
                            if status.last_run
                            else "Never"
                        ),
                        "records_processed": status.records_processed,
                    }
                )

            assets_table = create_asset_status_table(assets_with_status, context.console, "Assets")
            layout["assets"].update(assets_table)

        except Exception as e:
            layout["assets"].update(Panel(f"[red]Error loading assets: {e}[/red]", title="Assets"))

        # Metrics panel
        try:
            metrics = context.metrics_collector.get_latest_metrics()
            if metrics:
                metrics_text = Text()
                metrics_text.append("Success Rate: ", style="cyan")
                metrics_text.append(
                    f"{metrics.enrichment_success_rate * 100:.1f}%\n", style="white"
                )
                metrics_text.append("Throughput: ", style="cyan")
                metrics_text.append(
                    f"{metrics.processing_throughput:.1f} records/s\n", style="white"
                )
                metrics_text.append("Memory: ", style="cyan")
                metrics_text.append(f"{metrics.memory_usage_mb:.1f} MB\n", style="white")
                metrics_text.append("Errors: ", style="cyan")
                metrics_text.append(
                    str(metrics.error_count), style="red" if metrics.error_count > 0 else "white"
                )
                layout["metrics"].update(Panel(metrics_text, title="Metrics", border_style="blue"))
            else:
                layout["metrics"].update(Panel("[dim]No metrics available[/dim]", title="Metrics"))

        except Exception as e:
            layout["metrics"].update(
                Panel(f"[red]Error loading metrics: {e}[/red]", title="Metrics")
            )

        # Status panel
        try:
            neo4j_health = context.neo4j_client.health_check()
            status_text = Text()
            status_text.append("Neo4j: ", style="cyan")
            indicator = get_health_indicator("success" if neo4j_health.connected else "failed")
            status_text.append(indicator)
            if neo4j_health.connected:
                status_text.append(f" {neo4j_health.uri}", style="dim")
                if neo4j_health.version:
                    status_text.append(f"\nVersion: {neo4j_health.version}", style="dim")
            else:
                status_text.append(f" {neo4j_health.error or 'Not connected'}", style="red")

            layout["status"].update(Panel(status_text, title="System Status", border_style="blue"))

        except Exception as e:
            layout["status"].update(
                Panel(f"[red]Error checking status: {e}[/red]", title="System Status")
            )

        # Info panel
        info_text = Text()
        info_text.append("Last Updated: ", style="cyan")
        info_text.append(time.strftime("%Y-%m-%d %H:%M:%S"), style="dim")
        info_text.append("\n\nHotkeys:", style="bold")
        info_text.append("\n  q - Quit", style="dim")
        info_text.append("\n  r - Refresh now", style="dim")
        info_text.append("\n  i - Trigger ingest", style="dim")
        info_text.append("\n  e - Trigger enrich", style="dim")

        layout["info"].update(Panel(info_text, title="Info", border_style="blue"))

    except Exception as e:
        error_text = Text(f"[red]Error updating dashboard: {e}[/red]")
        layout["header"].update(Panel(error_text, border_style="red"))


@app.command()
def start(
    ctx: typer.Context,
    refresh_interval: int = typer.Option(10, "--refresh", "-r", help="Refresh interval in seconds"),
) -> None:
    """Start interactive dashboard with auto-refresh."""
    context: CommandContext = ctx.obj

    # Create layout
    layout = create_dashboard_layout(context)

    # Signal handler for graceful shutdown
    def signal_handler(sig: Any, frame: Any) -> None:
        context.console.print("\n[yellow]Shutting down dashboard...[/yellow]")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    context.console.print("[cyan]Starting dashboard...[/cyan]")
    context.console.print("[dim]Press Ctrl+C or 'q' to quit[/dim]\n")

    try:
        with Live(layout, refresh_per_second=1, screen=True) as live:
            # Initial update
            update_dashboard(context, layout)
            live.update(layout)

            # Auto-refresh loop
            start_time = time.time()
            while True:
                time.sleep(0.5)  # Check for keyboard input more frequently

                # Check if refresh interval has passed
                elapsed = time.time() - start_time
                if elapsed >= refresh_interval:
                    update_dashboard(context, layout)
                    live.update(layout)
                    start_time = time.time()

                # Note: Keyboard input handling would require additional setup
                # For now, Ctrl+C works via signal handler

    except KeyboardInterrupt:
        context.console.print("\n[yellow]Dashboard stopped[/yellow]")
    except Exception as e:
        context.console.print(f"[red]Dashboard error: {e}[/red]")
        raise typer.Exit(code=1)


def register_command(main_app: typer.Typer) -> None:
    """Register dashboard commands with main app."""
    main_app.add_typer(app, name="dashboard")
