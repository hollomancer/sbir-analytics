"""Status command for displaying pipeline and system status."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from ..context import CommandContext

app = typer.Typer(name="status", help="Display pipeline and system status")


def get_status_indicator(status: str) -> Text:
    """Get Rich Text indicator for status.

    Args:
        status: Status string (success, failed, running, not_started, etc.)

    Returns:
        Rich Text with colored indicator
    """
    indicators = {
        "success": Text("✓", style="green"),
        "failed": Text("✗", style="red"),
        "running": Text("⟳", style="yellow"),
        "not_started": Text("○", style="dim"),
        "unknown": Text("?", style="dim"),
    }
    return indicators.get(status.lower(), Text("?", style="dim"))


@app.command()
def assets(
    ctx: typer.Context,
    group: str | None = typer.Option(None, "--group", "-g", help="Filter by asset group"),
) -> None:
    """Display asset materialization status."""
    context: CommandContext = ctx.obj

    try:
        # Get all assets
        assets_list = context.dagster_client.list_assets()

        # Filter by group if specified
        if group:
            assets_list = [a for a in assets_list if a.get("group") == group]

        # Create table
        table = Table(title="Asset Status", show_header=True, header_style="bold magenta")
        table.add_column("Asset Key", style="cyan", no_wrap=True)
        table.add_column("Group", style="blue")
        table.add_column("Status", justify="center")
        table.add_column("Last Run", style="dim")
        table.add_column("Records", justify="right", style="dim")

        # Get status for each asset
        for asset in assets_list:
            asset_key = asset["key"]
            status = context.dagster_client.get_asset_status(asset_key)

            indicator = get_status_indicator(status.status)
            last_run = (
                status.last_run.strftime("%Y-%m-%d %H:%M")
                if status.last_run
                else "Never"
            )
            records = (
                str(status.records_processed) if status.records_processed else "-"
            )

            table.add_row(
                asset_key,
                asset.get("group", "-"),
                indicator,
                last_run,
                records,
            )

        context.console.print(table)

    except Exception as e:
        context.console.print(f"[red]Error getting asset status: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def neo4j(
    ctx: typer.Context,
    detailed: bool = typer.Option(False, "--detailed", "-d", help="Show detailed statistics"),
) -> None:
    """Display Neo4j connection health and database statistics."""
    context: CommandContext = ctx.obj

    try:
        # Check health
        health = context.neo4j_client.health_check()

        # Health panel
        if health.connected:
            status_text = Text(f"✓ Connected to {health.uri}", style="green")
            if health.version:
                status_text.append(f"\nVersion: {health.version}", style="dim")
        else:
            status_text = Text(f"✗ Connection failed: {health.error}", style="red")

        context.console.print(Panel(status_text, title="Neo4j Health", border_style="blue"))

        # Detailed statistics if requested
        if detailed and health.connected:
            stats = context.neo4j_client.get_statistics()

            if stats:
                # Node counts table
                nodes_table = Table(title="Node Counts", show_header=True)
                nodes_table.add_column("Label", style="cyan")
                nodes_table.add_column("Count", justify="right")

                for label, count in sorted(stats.node_counts.items(), key=lambda x: -x[1]):
                    nodes_table.add_row(label or "(no label)", str(count))

                nodes_table.add_row("[bold]Total[/bold]", f"[bold]{stats.total_nodes}[/bold]")

                context.console.print(nodes_table)

                # Relationship counts table
                rels_table = Table(title="Relationship Counts", show_header=True)
                rels_table.add_column("Type", style="cyan")
                rels_table.add_column("Count", justify="right")

                for rel_type, count in sorted(stats.relationship_counts.items(), key=lambda x: -x[1]):
                    rels_table.add_row(rel_type, str(count))

                rels_table.add_row("[bold]Total[/bold]", f"[bold]{stats.total_relationships}[/bold]")

                context.console.print(rels_table)

    except Exception as e:
        context.console.print(f"[red]Error checking Neo4j status: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def summary(ctx: typer.Context) -> None:
    """Display summary of pipeline status."""
    context: CommandContext = ctx.obj

    try:
        # Get assets
        assets_list = context.dagster_client.list_assets()
        asset_statuses = [
            context.dagster_client.get_asset_status(asset["key"]) for asset in assets_list
        ]

        # Count by status
        status_counts = {}
        for status in asset_statuses:
            s = status.status
            status_counts[s] = status_counts.get(s, 0) + 1

        # Neo4j health
        neo4j_health = context.neo4j_client.health_check()

        # Create summary table
        summary_table = Table(title="Pipeline Status Summary", show_header=True)
        summary_table.add_column("Component", style="cyan")
        summary_table.add_column("Status", justify="center")
        summary_table.add_column("Details", style="dim")

        # Assets summary
        total_assets = len(assets_list)
        success_count = status_counts.get("success", 0)
        failed_count = status_counts.get("failed", 0)
        not_started = status_counts.get("not_started", 0)

        assets_status = get_status_indicator(
            "success" if failed_count == 0 and not_started == 0 else "running"
        )
        assets_details = f"{total_assets} total, {success_count} success, {failed_count} failed, {not_started} not started"

        summary_table.add_row("Assets", assets_status, assets_details)

        # Neo4j status
        neo4j_status = get_status_indicator("success" if neo4j_health.connected else "failed")
        neo4j_details = (
            f"Connected to {neo4j_health.uri}"
            if neo4j_health.connected
            else f"Failed: {neo4j_health.error}"
        )

        summary_table.add_row("Neo4j", neo4j_status, neo4j_details)

        context.console.print(summary_table)

    except Exception as e:
        context.console.print(f"[red]Error getting status summary: {e}[/red]")
        raise typer.Exit(code=1)


def register_command(main_app: typer.Typer) -> None:
    """Register status commands with main app."""
    main_app.add_typer(app, name="status")

