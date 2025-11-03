"""CLI command context and shared utilities.

Provides CommandContext dataclass for dependency injection of shared state
across CLI commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from rich.console import Console

if TYPE_CHECKING:
    from src.config.schemas import PipelineConfig

    from .integration.dagster_client import DagsterClient
    from .integration.metrics_collector import MetricsCollector
    from .integration.neo4j_client import Neo4jClient
else:
    PipelineConfig = Any
    DagsterClient = Any
    MetricsCollector = Any
    Neo4jClient = Any


@dataclass
class CommandContext:
    """Shared context for CLI commands.

    Provides access to configuration, console output, and integration clients.
    This enables dependency injection and consistent behavior across commands.
    """

    config: PipelineConfig
    console: Console
    dagster_client: DagsterClient
    neo4j_client: Neo4jClient
    metrics_collector: MetricsCollector

    @classmethod
    def create(cls, config: PipelineConfig | None = None) -> CommandContext:
        """Create a CommandContext instance with default clients.

        Args:
            config: Optional PipelineConfig. If None, loads from get_config().

        Returns:
            CommandContext instance with initialized clients.
        """
        # Import here to avoid circular dependencies
        from src.config.loader import get_config

        from .integration.dagster_client import DagsterClient
        from .integration.metrics_collector import MetricsCollector
        from .integration.neo4j_client import Neo4jClient

        if config is None:
            config = get_config()

        console = Console()

        # Initialize clients
        dagster_client = DagsterClient(config=config, console=console)
        neo4j_client = Neo4jClient(config=config, console=console)
        metrics_collector = MetricsCollector(config=config, console=console)

        return cls(
            config=config,
            console=console,
            dagster_client=dagster_client,
            neo4j_client=neo4j_client,
            metrics_collector=metrics_collector,
        )
