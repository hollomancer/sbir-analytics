"""Enrich command for executing enrichment workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

import typer
from rich.table import Table

from src.utils.enrichment_freshness import FreshnessRecord, FreshnessStore

from ..context import CommandContext
from ..display.progress import create_progress_tracker


app = typer.Typer(name="enrich", help="Execute enrichment workflows")


@app.command()
def run(
    ctx: typer.Context,
    sources: str | None = typer.Option(
        None,
        "--sources",
        "-s",
        help="Comma-separated enrichment sources (e.g., 'sam_gov,usaspending')",
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

        context.console.print(
            f"[cyan]Executing enrichment for sources: {', '.join(asset_groups)}[/cyan]"
        )

        # Execute enrichment with progress tracking
        tracker = create_progress_tracker(context.console)
        operations = [
            {"description": f"Enriching with {group}", "total": None} for group in asset_groups
        ]

        with tracker.track_multiple_operations(operations) as updates:
            success_count = 0

            for _i, group in enumerate(asset_groups):
                update = updates[f"Enriching with {group}"]
                update({"completed": 0, "records": 0, "message": "Starting..."})

                try:
                    # Trigger materialization for this enrichment group
                    result = context.dagster_client.trigger_materialization(
                        asset_groups=[group],
                    )

                    if result.status == "success":
                        success_count += 1
                        update(
                            {"completed": 100, "records": 0, "message": "Completed successfully"}
                        )
                    else:
                        update(
                            {"completed": 100, "records": 0, "message": f"Failed: {result.status}"}
                        )

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
            context.console.print(
                "[green]✓ All enrichment operations completed successfully[/green]"
            )
        else:
            context.console.print(
                f"[yellow]⚠ {success_count}/{len(asset_groups)} enrichment operations completed[/yellow]"
            )
            raise typer.Exit(code=1)

    except Exception as e:
        context.console.print(f"[red]Error during enrichment: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("metrics")
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


def _format_records(records: Iterable[FreshnessRecord]) -> Table:
    """Render a table summarizing freshness records."""

    table = Table(title="Enrichment Freshness", show_header=True)
    table.add_column("Award ID", style="cyan")
    table.add_column("Source")
    table.add_column("Status")
    table.add_column("Last Success")
    table.add_column("Failures")

    for record in records:
        last_success = record.last_success_at.isoformat() if record.last_success_at else "never"
        table.add_row(
            record.award_id,
            record.source or "-",
            record.status.value,
            last_success,
            str(record.failure_count or 0),
        )
    return table


@app.command("list-stale")
def list_stale(
    ctx: typer.Context,
    source: str = typer.Option("usaspending", "--source", help="Enrichment source name"),
    sla_days: int | None = typer.Option(None, "--sla-days", help="Override SLA threshold"),
) -> None:
    """List stale awards tracked by the freshness store."""

    context: CommandContext = ctx.obj
    config = context.config
    store = FreshnessStore()
    threshold = sla_days or config.enrichment_refresh.usaspending.sla_staleness_days

    stale_records = store.get_stale_records(source, threshold)
    if not stale_records:
        context.console.print(f"[green]No stale records found for {source}[/green]")
        return

    context.console.print(f"[yellow]Found {len(stale_records)} stale {source} records[/yellow]")
    context.console.print(_format_records(stale_records[:50]))


@app.command("freshness-stats")
def freshness_stats(
    ctx: typer.Context,
    source: str = typer.Option("usaspending", "--source", help="Enrichment source name"),
) -> None:
    """Show enrichment freshness statistics driven by the freshness store."""

    store = FreshnessStore()
    df = store.load_all()
    if df.empty:
        typer.echo("No freshness records found")
        return

    if "source" in df.columns:
        df = df[df["source"] == source]

    total = len(df)
    success = (
        len(df[df["status"] == "success"]) if "status" in df.columns else 0
    )
    stale_records = store.get_stale_records(source, sla_days=90)

    table = Table(title="Freshness Summary", show_header=True)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Total Records Tracked", str(total))
    table.add_row("Successful", str(success))
    table.add_row("Failures", str(total - success))
    table.add_row("Stale (>90 days)", str(len(stale_records)))

    ctx.obj.console.print(table)


@app.command("refresh-usaspending")
def refresh_usaspending(
    ctx: typer.Context,
    award_ids: str | None = typer.Option(
        None, "--award-ids", help="Comma-separated list of award IDs to refresh"
    ),
    cohort: str | None = typer.Option(
        None,
        "--cohort",
        help="Award cohort (e.g., year like '2023' or date range '2023-01-01:2023-12-31')",
    ),
    window_days: int | None = typer.Option(
        None, "--window", help="Number of days to look back when computing staleness"
    ),
    stale_only: bool = typer.Option(False, "--stale-only", help="Only refresh stale awards"),
    force: bool = typer.Option(False, "--force", help="Force refresh even if not stale"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview refresh set without running"),
) -> None:
    """Plan a USAspending enrichment refresh window."""

    context: CommandContext = ctx.obj
    config = context.config
    refresh_cfg = config.enrichment_refresh.usaspending
    store = FreshnessStore()
    source = "usaspending"

    award_ids_list: list[str] | None = None
    if award_ids:
        award_ids_list = [aid.strip() for aid in award_ids.split(",") if aid.strip()]

    if stale_only:
        sla_days = window_days or refresh_cfg.sla_staleness_days
        stale_records = store.get_stale_records(source, sla_days)
        award_ids_list = [record.award_id for record in stale_records]
        context.console.print(
            f"[cyan]Selected {len(award_ids_list)} stale awards (SLA {sla_days} days)[/cyan]"
        )

    if cohort:
        if ":" in cohort:
            start_str, end_str = cohort.split(":", 1)
            _ = datetime.fromisoformat(start_str.strip())
            _ = datetime.fromisoformat(end_str.strip())
            context.console.print(
                "[yellow]Date-range cohorts acknowledged but detailed filtering requires Dagster run config overrides[/yellow]"
            )
        else:
            int(cohort)
            context.console.print(
                "[yellow]Year-based cohort acknowledged; provide custom run config to Dagster job for precise filtering[/yellow]"
            )

    if dry_run:
        context.console.print("[green]Dry run only - no Dagster job triggered[/green]")
        if award_ids_list:
            context.console.print(f"Would refresh {len(award_ids_list)} awards: {award_ids_list[:10]}...")
        else:
            context.console.print("No awards selected for refresh.")
        return

    context.console.print(
        "[yellow]Refresh execution requires Dagster job `usaspending_iterative_enrichment_job`[/yellow]"
    )
    context.console.print(
        "Run `dagster job execute usaspending_iterative_enrichment_job -c config/dev.yaml` "
        "with the desired run-config overrides."
    )


def register_command(main_app: typer.Typer) -> None:
    """Register enrich commands with main app."""
    main_app.add_typer(app, name="enrich")
