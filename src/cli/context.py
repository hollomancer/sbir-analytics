"""CLI command context and shared utilities.

Provides CommandContext dataclass for dependency injection of shared state
across CLI commands.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger
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

    Provides access to configuration, console output, integration clients,
    and structured logging with context variables.

    Attributes:
        config: Pipeline configuration
        console: Rich console for formatted output
        dagster_client: Dagster API client
        neo4j_client: Neo4j database client
        metrics_collector: Metrics collection client
        run_id: Unique identifier for this CLI session
        logger: Loguru logger with context binding
    """

    config: PipelineConfig
    console: Console
    dagster_client: DagsterClient
    neo4j_client: Neo4jClient
    metrics_collector: MetricsCollector
    run_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def __post_init__(self) -> None:
        """Set up structured logging context after initialization."""
        # Bind context variables to logger for all CLI operations
        self.logger = logger.bind(
            component="cli",
            run_id=self.run_id,
            environment=self.config.pipeline.get("environment", "unknown")
        )

    @classmethod
    def create(cls, config: PipelineConfig | None = None, run_id: str | None = None) -> CommandContext:
        """Create a CommandContext instance with default clients and structured logging.

        Args:
            config: Optional PipelineConfig. If None, loads from get_config().
            run_id: Optional run identifier. If None, generates a unique ID.

        Returns:
            CommandContext instance with initialized clients and logging context.
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

        # Create context with optional run_id
        ctx_kwargs = {
            "config": config,
            "console": console,
            "dagster_client": dagster_client,
            "neo4j_client": neo4j_client,
            "metrics_collector": metrics_collector,
        }
        if run_id is not None:
            ctx_kwargs["run_id"] = run_id

        context = cls(**ctx_kwargs)

        # Log CLI session start
        context.logger.info(
            "CLI session started",
            extra={
                "command": "unknown",  # Will be updated by command
                "pid": __import__("os").getpid(),
            }
        )

        return context
