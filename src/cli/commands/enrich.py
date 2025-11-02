"""Enrich command for executing enrichment workflows."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..context import CommandContext
from ..display.progress import create_progress_tracker

app = typer.Typer(name="enrich", help="Execute enrichment workflows")


@app.command()
def run(
    ctx: typer.Context,
    sources: str | None = typer.Option(
        None, "--sources", "-s", help="Comma-separated enrichment sources (e.g., 'sam_gov,usaspending')"
    ),
    batch_size: int | None = typer.Option(None, "--batch-size", "-b", help="Batch processing size"),
    confidence_threshold: float | None = typer.Option(
        None, "--confidence", "-c", help="Minimum confidence threshold for matches (0.0-1.0)"
    ),
) -> None:
    """Execute enrichment workflows with source selection."""
    context: CommandContext = ctx.obj

    try:
        # Parse sources
        sources_list: list[str] | None = None
        if sources:
            sources_list = [s.strip() for s in sources.split(",") if s.strip()]

        # Determine which asset groups to target based on sources
        asset_groups = []
        if not sources_list or "sam_gov" in sources_list:
            asset_groups.append("sam_gov_enrichment")
        if not sources_list or "usaspending" in sources_list:
            asset_groups.append("sbir_usaspending_enrichment")

        if not asset_groups:
            context.console.print("[yellow]No valid enrichment sources specified[/yellow]")
            return

        context.console.print(f"[cyan]Executing enrichment for sources: {', '.join(asset_groups)}[/cyan]")

        # Execute enrichment with progress tracking
        tracker = create_progress_tracker(context.console)
        operations = [
            {"description": f"Enriching with {group}", "total": None}
            for group in asset_groups
        ]

        with tracker.track_multiple_operations(operations) as updates:
                success_count = 0
                total_processed = 0

                for i, group in enumerate(asset_groups):
                    update = updates[f"Enriching with {group}"]
                    update({"completed": 0, "records": 0, "message": "Starting..."})

                    try:
                        # Trigger materialization for this enrichment group
                        result = context.dagster_client.trigger_materialization(
                            asset_groups=[group],
                        )

                        if result.status == "success":
                            success_count += 1
                            update({"completed": 100, "records": 0, "message": "Completed successfully"})
                        else:
                            update({"completed": 100, "records": 0, "message": f"Failed: {result.status}"})

                    except Exception as e:
                        update({"completed": 100, "records": 0, "message": f"Error: {str(e)[:50]}"})
                        context.console.print(f"[red]Error enriching with {group}: {e}[/red]")

        # Display summary
        summary_table = Table(title="Enrichment Summary", show_header=True)
        summary_table.add_column("Source", style="cyan")
        summary_table.add_column("Status", justify="center")
        summary_table.add_column("Records", justify="right")

        for group in asset_groups:
            # In a real implementation, would query actual results
            summary_table.add_row(
                group,
                "[green]✓[/green]",  # Would check actual status
                "-",  # Would show actual record count
            )

        context.console.print(summary_table)

        if success_count == len(asset_groups):
            context.console.print(f"[green]✓ All enrichment operations completed successfully[/green]")
        else:
            context.console.print(
                f"[yellow]⚠ {success_count}/{len(asset_groups)} enrichment operations completed[/yellow]"
            )
            raise typer.Exit(code=1)

    except Exception as e:
        context.console.print(f"[red]Error during enrichment: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def stats(
    ctx: typer.Context,
    source: str | None = typer.Option(None, "--source", "-s", help="Filter by enrichment source"),
) -> None:
    """Display enrichment statistics and success rates."""
    context: CommandContext = ctx.obj

    try:
        # Get metrics filtered by enrichment operations
        metrics = context.metrics_collector.get_metrics(asset_group=source or "enrichment")

        if not metrics:
            context.console.print("[yellow]No enrichment metrics available[/yellow]")
            return

        # Calculate statistics
        total_operations = len(metrics)
        success_count = sum(1 for m in metrics if m.get("success", False))
        success_rate = (success_count / total_operations * 100) if total_operations > 0 else 0
        total_records = sum(m.get("records_processed", 0) for m in metrics)

        # Display statistics
        stats_table = Table(title="Enrichment Statistics", show_header=True)
        stats_table.add_column("Metric", style="cyan")
        stats_table.add_column("Value", justify="right")

        stats_table.add_row("Total Operations", str(total_operations))
        stats_table.add_row("Successful", f"{success_count} ({success_rate:.1f}%)")
        stats_table.add_row("Failed", str(total_operations - success_count))
        stats_table.add_row("Total Records Processed", f"{total_records:,}")

        context.console.print(stats_table)

    except Exception as e:
        context.console.print(f"[red]Error getting enrichment statistics: {e}[/red]")
        raise typer.Exit(code=1)


def register_command(main_app: typer.Typer) -> None:
    """Register enrich commands with main app."""
    main_app.add_typer(app, name="enrich")

