"""Main CLI application entry point for SBIR ETL Pipeline.

This module provides the Typer application instance and command registration.
Uses the same logging infrastructure as the main pipeline, with a CLI-friendly
pretty format on stderr so Rich output on stdout remains uncluttered.
"""

from __future__ import annotations

import typer
from loguru import logger
from rich.console import Console

from .display.errors import EXIT_CONFIG_ERROR, handle_error


# Initialize Typer app
app = typer.Typer(
    name="sbir-cli",
    help="SBIR Analytics Pipeline CLI",
    add_completion=False,
    no_args_is_help=True,
)

# Global console instance for Rich output
console = Console()


def setup_logging(verbose: bool = False, debug: bool = False) -> None:
    """Configure logging for CLI using the pipeline's logging infrastructure.

    Uses the same ``setup_logging`` from ``src.utils.common.logging_config`` so
    that log format, file rotation, and context variables behave identically to
    the main pipeline.  The CLI always uses "text" format (pretty) since Rich
    tables and panels are the primary output channel.

    Args:
        verbose: Enable debug-level logging to console.
        debug: Alias for verbose (for ``--debug`` flag).
    """
    from sbir_etl.utils.logging_config import setup_logging as pipeline_setup_logging

    log_level = "DEBUG" if (verbose or debug) else "INFO"

    # Attempt to load file path from config; fall back gracefully
    file_path: str | None = None
    try:
        from sbir_etl.config.loader import get_config

        config = get_config()
        file_path = config.logging.file_path
    except Exception:
        pass  # Config may not be available yet; skip file logging

    pipeline_setup_logging(
        level=log_level,
        format_type="text",  # CLI always uses pretty format
        file_path=file_path,
        include_stage=False,  # CLI commands don't set pipeline stage
        include_run_id=False,  # CLI commands don't set run IDs
        include_timestamps=True,
    )


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
    debug: bool = typer.Option(False, "--debug", help="Enable debug-level logging"),
) -> None:
    """SBIR Analytics Pipeline CLI.

    Provides commands for pipeline operations, status monitoring, and metrics.
    """
    try:
        # Setup logging using the shared pipeline infrastructure
        setup_logging(verbose=verbose, debug=debug)

        # Store context in typer context for commands
        from .context import CommandContext

        ctx.obj = CommandContext.create()

        if ctx.invoked_subcommand is None:
            # Show help if no command provided
            console.print(app.info.help)
            raise typer.Exit(code=0)

    except typer.Exit:
        raise
    except Exception as e:
        logger.opt(exception=True).error(f"CLI initialization failed: {e}")
        handle_error(e, exit_code=EXIT_CONFIG_ERROR)
        raise


# Register commands
from .commands import autodev, benchmark, dashboard, enrich, ingest, metrics, status, transition


status.register_command(app)
metrics.register_command(app)
ingest.register_command(app)
enrich.register_command(app)
dashboard.register_command(app)
transition.register_command(app)
benchmark.register_command(app)
autodev.register_command(app)


if __name__ == "__main__":
    app()
