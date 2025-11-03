"""Ingest command for triggering data extraction and loading operations."""

from __future__ import annotations

import typer
from rich.panel import Panel

from ..context import CommandContext
from ..display.progress import create_progress_tracker

app = typer.Typer(name="ingest", help="Trigger data ingestion operations")


@app.command()
def run(
    ctx: typer.Context,
    asset_groups: str | None = typer.Option(
        None,
        "--groups",
        "-g",
        help="Comma-separated asset group names (e.g., 'sbir_ingestion,usaspending_ingestion')",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-d", help="Preview operations without executing"
    ),
    force_refresh: bool = typer.Option(False, "--force", "-f", help="Force refresh (skip cache)"),
) -> None:
    """Trigger data ingestion operations for specified asset groups."""
    context: CommandContext = ctx.obj

    try:
        # Parse asset groups
        groups_list: list[str] | None = None
        if asset_groups:
            groups_list = [g.strip() for g in asset_groups.split(",") if g.strip()]

        if dry_run:
            # Preview mode - show what would be executed
            context.console.print("[yellow]DRY RUN MODE - No operations will be executed[/yellow]")

            if groups_list:
                context.console.print(
                    f"[cyan]Would materialize asset groups: {', '.join(groups_list)}[/cyan]"
                )
            else:
                context.console.print("[cyan]Would materialize all assets[/cyan]")

            if force_refresh:
                context.console.print("[cyan]Force refresh: enabled[/cyan]")

            context.console.print("\n[dim]Remove --dry-run to execute operations[/dim]")
            return

        # Execute materialization
        tracker = create_progress_tracker(context.console)
        with tracker.track_operation(
            "Materializing ingestion assets",
            total=None,  # Indeterminate progress
        ) as update:
            # Update progress callback
            update({"completed": 0, "records": 0, "message": "Starting materialization..."})

            try:
                # Trigger materialization
                result = context.dagster_client.trigger_materialization(
                    asset_groups=groups_list,
                )

                update({"completed": 100, "records": 0, "message": "Materialization completed"})

                # Display result
                if result.status == "success":
                    success_panel = Panel(
                        f"[green]✓ Materialization started successfully[/green]\n"
                        f"Run ID: [cyan]{result.run_id}[/cyan]\n"
                        f"Started at: {result.started_at.strftime('%Y-%m-%d %H:%M:%S')}",
                        title="Success",
                        border_style="green",
                    )
                    context.console.print(success_panel)
                else:
                    error_panel = Panel(
                        f"[red]✗ Materialization failed[/red]\n"
                        f"Run ID: [cyan]{result.run_id}[/cyan]\n"
                        f"Status: {result.status}",
                        title="Error",
                        border_style="red",
                    )
                    context.console.print(error_panel)
                    raise typer.Exit(code=1)

            except Exception as e:
                update({"completed": 0, "records": 0, "message": f"Error: {str(e)}"})
                context.console.print(f"[red]Error during materialization: {e}[/red]")
                raise typer.Exit(code=1)

    except Exception as e:
        context.console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)


@app.command()
def status(
    ctx: typer.Context,
    run_id: str | None = typer.Option(
        None, "--run-id", "-r", help="Check status of specific run ID"
    ),
) -> None:
    """Check status of ingestion runs."""
    context: CommandContext = ctx.obj

    try:
        if run_id:
            # Get status for specific run
            run_status = context.dagster_client.get_run_status(run_id)

            if run_status.get("status") == "not_found":
                context.console.print(f"[yellow]Run ID {run_id} not found[/yellow]")
                return

            # Display run status
            typer.style("Rich table would go here")  # TODO: Use Rich table
            context.console.print(f"[cyan]Run Status for {run_id}:[/cyan]")
            context.console.print(f"  Status: {run_status.get('status')}")
            context.console.print(f"  Start Time: {run_status.get('start_time', 'Unknown')}")
            context.console.print(f"  End Time: {run_status.get('end_time', 'In progress')}")
        else:
            # List recent runs (would need additional Dagster API call)
            context.console.print("[yellow]Listing all runs not yet implemented[/yellow]")
            context.console.print("[dim]Use --run-id to check a specific run[/dim]")

    except Exception as e:
        context.console.print(f"[red]Error getting run status: {e}[/red]")
        raise typer.Exit(code=1)


def register_command(main_app: typer.Typer) -> None:
    """Register ingest commands with main app."""
    main_app.add_typer(app, name="ingest")
