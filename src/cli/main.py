"""Main CLI application entry point for SBIR ETL Pipeline.

This module provides the Typer application instance and command registration.
"""

from __future__ import annotations

import sys
from typing import Any

import typer
from rich.console import Console
from loguru import logger

from .display.errors import CLIError, handle_error

# Initialize Typer app
app = typer.Typer(
    name="sbir-cli",
    help="SBIR Analytics Pipeline CLI",
    add_completion=False,
    no_args_is_help=True,
)

# Global console instance for Rich output
console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for CLI.

    Args:
        verbose: Enable debug-level logging
    """
    # Remove default handler
    logger.remove()

    # Add console handler with appropriate level
    log_level = "DEBUG" if verbose else "INFO"
    logger.add(
        sys.stderr,
        format="<level>{level: <8}</level> | {message}",
        level=log_level,
        colorize=True,
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """SBIR Analytics Pipeline CLI.

    Provides commands for pipeline operations, status monitoring, and metrics.
    """
    try:
        # Setup logging
        setup_logging(verbose=verbose)

        # Store context in typer context for commands
        from .context import CommandContext

        ctx.obj = CommandContext.create()

        if ctx.invoked_subcommand is None:
            # Show help if no command provided
            console.print(app.info.help)
            raise typer.Exit(code=0)

    except Exception as e:
        handle_error(e, exit_code=2)  # Config errors use exit code 2
        raise


# Register commands
from .commands import dashboard, enrich, ingest, metrics, status

status.register_command(app)
metrics.register_command(app)
ingest.register_command(app)
enrich.register_command(app)
dashboard.register_command(app)


if __name__ == "__main__":
    app()

