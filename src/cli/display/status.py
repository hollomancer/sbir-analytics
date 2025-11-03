"""Status display component with Rich formatting."""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def get_health_indicator(status: str) -> Text:
    """Get health indicator with icon and color.

    Args:
        status: Status string (success, failed, running, etc.)

    Returns:
        Rich Text with indicator
    """
    indicators = {
        "success": Text("✓", style="bold green"),
        "healthy": Text("✓", style="bold green"),
        "failed": Text("✗", style="bold red"),
        "unhealthy": Text("✗", style="bold red"),
        "running": Text("⟳", style="bold yellow"),
        "warning": Text("⚠", style="bold yellow"),
        "not_started": Text("○", style="dim"),
        "unknown": Text("?", style="dim"),
    }
    return indicators.get(status.lower(), Text("?", style="dim"))


def create_asset_status_table(
    assets: list[dict[str, Any]],
    console: Console,
    title: str = "Asset Status",
) -> Table:
    """Create a formatted asset status table.

    Args:
        assets: List of asset dictionaries with status info
        console: Rich console
        title: Table title

    Returns:
        Rich Table instance
    """
    table = Table(title=title, show_header=True, header_style="bold magenta")
    table.add_column("Asset Key", style="cyan", no_wrap=True)
    table.add_column("Group", style="blue")
    table.add_column("Status", justify="center")
    table.add_column("Last Run", style="dim")
    table.add_column("Records", justify="right", style="dim")

    for asset in assets:
        asset_key = asset.get("key", "Unknown")
        group = asset.get("group", "-")
        status_str = asset.get("status", "unknown")
        last_run = asset.get("last_run", "Never")
        records = asset.get("records_processed", "-")

        indicator = get_health_indicator(status_str)

        table.add_row(
            asset_key,
            group,
            indicator,
            last_run,
            str(records) if records != "-" else "-",
        )

    return table


def create_summary_panel(
    summary_data: dict[str, Any],
    console: Console,
    title: str = "Pipeline Summary",
) -> Panel:
    """Create a summary panel with key metrics.

    Args:
        summary_data: Dictionary with summary statistics
        console: Rich console
        title: Panel title

    Returns:
        Rich Panel instance
    """
    content = Text()

    # Assets summary
    if "assets" in summary_data:
        assets = summary_data["assets"]
        total = assets.get("total", 0)
        success = assets.get("success", 0)
        failed = assets.get("failed", 0)
        content.append("Assets: ", style="cyan")
        content.append(f"{total} total", style="white")
        content.append(f", {success} success", style="green")
        if failed > 0:
            content.append(f", {failed} failed", style="red")
        content.append("\n")

    # Neo4j status
    if "neo4j" in summary_data:
        neo4j = summary_data["neo4j"]
        connected = neo4j.get("connected", False)
        if connected:
            content.append("Neo4j: ", style="cyan")
            content.append("✓ Connected", style="green")
            if "nodes" in neo4j:
                content.append(f" ({neo4j['nodes']:,} nodes)", style="dim")
        else:
            content.append("Neo4j: ", style="cyan")
            content.append("✗ Not connected", style="red")
        content.append("\n")

    # Metrics summary
    if "metrics" in summary_data:
        metrics = summary_data["metrics"]
        if "throughput" in metrics:
            content.append("Throughput: ", style="cyan")
            content.append(f"{metrics['throughput']:.1f} records/s", style="white")
            content.append("\n")

    return Panel(content, title=title, border_style="blue")
