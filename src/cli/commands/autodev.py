"""Autonomous development CLI commands.

Provides commands to run the autonomous development loop, inspect
discovered tasks, and manage sessions.
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(name="autodev", help="Autonomous development loop")
console = Console()


@app.command("discover")
def discover_tasks(
    project_root: Path = typer.Option(".", "--root", "-r", help="Project root directory"),
    include_tests: bool = typer.Option(
        False, "--tests", help="Also run pytest to discover test failures (slower)"
    ),
) -> None:
    """Discover and display all available work items."""
    from src.autodev.orchestrator import LoopConfig, Orchestrator

    project_root = project_root.resolve()
    config = LoopConfig(project_root=project_root, discover_tests=include_tests)
    orch = Orchestrator(config)

    items = orch.discover_work()

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

    # Summary by source
    from collections import Counter

    source_counts = Counter(item.source.value for item in items)
    console.print("\n[bold]By source:[/bold]")
    for source, count in source_counts.most_common():
        console.print(f"  {source}: {count}")


@app.command("run")
def run_loop(
    project_root: Path = typer.Option(".", "--root", "-r", help="Project root directory"),
    max_tasks: int = typer.Option(50, "--max-tasks", "-n", help="Maximum tasks to process"),
    test_scope: str = typer.Option(
        "unit", "--test-scope", help="Test scope: fast, unit, smoke, integration, all"
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Generate prompts without executing"),
    executor: str = typer.Option(
        "dry-run",
        "--executor",
        "-e",
        help="Executor: dry-run, claude-code, claude-api",
    ),
    review_interval: int = typer.Option(
        5, "--review-interval", help="Tasks between mandatory human reviews"
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="Model for Claude executors"),
    token_budget: int = typer.Option(
        0,
        "--token-budget",
        "-b",
        help="Max total tokens to consume (0 = unlimited)",
    ),
) -> None:
    """Run the autonomous development loop."""
    from src.autodev.executor import ClaudeAPIExecutor, ClaudeCodeExecutor
    from src.autodev.orchestrator import LoopConfig, Orchestrator

    # --dry-run flag overrides executor choice
    is_dry_run = dry_run or executor == "dry-run"

    project_root = project_root.resolve()
    config = LoopConfig(
        project_root=project_root,
        max_tasks=max_tasks,
        test_scope=test_scope,
        dry_run=is_dry_run,
        review_interval=review_interval,
        interactive=True,
        max_token_budget=token_budget,
    )

    orch = Orchestrator(config)

    if is_dry_run:
        result = orch.run()
    elif executor == "claude-code":
        exec_fn = ClaudeCodeExecutor(model=model)
        result = orch.run_with_executor(exec_fn)
    elif executor == "claude-api":
        exec_fn = ClaudeAPIExecutor(model=model or "claude-sonnet-4-20250514")
        result = orch.run_with_executor(exec_fn)
    else:
        console.print(f"[red]Unknown executor: {executor}[/red]")
        raise typer.Exit(code=1)

    console.print(f"\n[bold]{result.summary}[/bold]")


@app.command("sessions")
def list_sessions(
    project_root: Path = typer.Option(".", "--root", "-r", help="Project root directory"),
) -> None:
    """List previous autonomous development sessions."""
    from src.autodev.session import SessionManager

    project_root = project_root.resolve()
    mgr = SessionManager(project_root)
    sessions = mgr.list_sessions()

    if not sessions:
        console.print("[dim]No sessions found.[/dim]")
        return

    table = Table(title="Autodev Sessions")
    table.add_column("Session ID", style="cyan")
    table.add_column("Started", style="dim")
    table.add_column("Branch")
    table.add_column("Attempted", justify="right")
    table.add_column("Succeeded", justify="right", style="green")
    table.add_column("Tokens", justify="right", style="dim")

    for s in sessions:
        tokens = s.get("total_tokens", "0")
        token_display = f"{int(tokens):,}" if int(tokens) > 0 else "-"
        table.add_row(
            s["session_id"],
            s["started_at"][:19],
            s["branch"],
            s["tasks_attempted"],
            s["tasks_succeeded"],
            token_display,
        )

    console.print(table)


@app.command("specs")
def show_specs(
    project_root: Path = typer.Option(".", "--root", "-r", help="Project root directory"),
) -> None:
    """Show Kiro specification status overview."""
    from src.autodev.task_parser import discover_specs

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
