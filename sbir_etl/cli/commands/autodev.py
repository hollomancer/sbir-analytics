"""Autonomous development CLI commands.

Provides commands to discover pending tasks and inspect Kiro spec status.
The actual implementation loop runs through the ``autodev-runner`` agent.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="autodev", help="Autonomous development task discovery")
console = Console()


@app.command("discover")
def discover_tasks(
    project_root: Path = typer.Option(".", "--root", "-r", help="Project root directory"),
    include_tests: bool = typer.Option(
        False, "--tests", help="Also run pytest to discover test failures (slower)"
    ),
) -> None:
    """Discover and display all available work items."""
    from sbir_etl.autodev.orchestrator import DiscoveryConfig, discover_work

    project_root = project_root.resolve()
    config = DiscoveryConfig(project_root=project_root, discover_tests=include_tests)

    items = discover_work(config)

    table = Table(title=f"Work Items ({len(items)} found)")
    table.add_column("#", style="dim", width=4)
    table.add_column("Source", style="cyan", width=14)
    table.add_column("Risk", width=8)
    table.add_column("Title", min_width=40)
    table.add_column("File", style="dim", max_width=40)

    risk_colors = {"low": "green", "medium": "yellow", "high": "red"}

    for i, item in enumerate(items, 1):
        risk_val = item.risk.value if hasattr(item.risk, "value") else str(item.risk)
        risk_color = risk_colors.get(risk_val, "white")
        table.add_row(
            str(i),
            item.source.value,
            f"[{risk_color}]{risk_val}[/{risk_color}]",
            item.title[:60],
            (item.file_path or "")[:40],
        )

    console.print(table)

    source_counts = Counter(item.source.value for item in items)
    console.print("\n[bold]By source:[/bold]")
    for source, count in source_counts.most_common():
        console.print(f"  {source}: {count}")


@app.command("specs")
def show_specs(
    project_root: Path = typer.Option(".", "--root", "-r", help="Project root directory"),
) -> None:
    """Show Kiro specification status overview."""
    from sbir_etl.autodev.task_parser import discover_specs

    project_root = project_root.resolve()
    specs_root = project_root / ".kiro" / "specs"
    specs = discover_specs(specs_root)

    if not specs:
        console.print("[dim]No specs found.[/dim]")
        return

    table = Table(title="Kiro Specifications")
    table.add_column("Spec", min_width=30)
    table.add_column("Total", justify="right", width=6)
    table.add_column("Done", justify="right", width=6, style="green")
    table.add_column("Pending", justify="right", width=8, style="yellow")
    table.add_column("Progress", width=12)

    for spec in specs:
        pct = spec.progress_pct
        bar_filled = int(pct / 10)
        bar = "[green]" + "█" * bar_filled + "[/green]" + "░" * (10 - bar_filled)
        table.add_row(
            spec.name,
            str(len(spec.tasks)),
            str(len(spec.completed_tasks)),
            str(len(spec.pending_tasks)),
            f"{bar} {pct:.0f}%",
        )

    console.print(table)


def register_command(main_app: typer.Typer) -> None:
    """Register autodev commands with main CLI app."""
    main_app.add_typer(app, name="autodev")
