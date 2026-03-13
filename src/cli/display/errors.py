"""Error formatting and display utilities for the SBIR CLI.

Provides Rich-formatted error messages with context-aware suggestions,
exit code mapping, and a decorator for consistent error handling in commands.

Exit code conventions:
    0  - Success
    1  - General runtime error
    2  - Configuration / validation error
    3  - Connection error (Dagster, Neo4j, API)
    4  - Data error (missing files, corrupt data)
"""

from __future__ import annotations

from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ..context import CommandContext

# ---------------------------------------------------------------------------
# Exit code constants
# ---------------------------------------------------------------------------
EXIT_SUCCESS = 0
EXIT_RUNTIME_ERROR = 1
EXIT_CONFIG_ERROR = 2
EXIT_CONNECTION_ERROR = 3
EXIT_DATA_ERROR = 4


class CLIError(Exception):
    """Base exception for CLI errors with exit code support."""

    def __init__(
        self, message: str, exit_code: int = EXIT_RUNTIME_ERROR, suggestions: list[str] | None = None
    ) -> None:
        """Initialize CLI error.

        Args:
            message: Error message
            exit_code: Exit code to use (see module-level constants)
            suggestions: Optional list of suggested fixes
        """
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.suggestions = suggestions or []


class ConfigError(CLIError):
    """Configuration-related error."""

    def __init__(self, message: str, suggestions: list[str] | None = None) -> None:
        default_suggestions = suggestions or [
            "Verify config/base.yaml syntax",
            "Check environment variable overrides (SBIR_ETL__*)",
            "Run with --verbose for detailed error messages",
        ]
        super().__init__(message, exit_code=EXIT_CONFIG_ERROR, suggestions=default_suggestions)


class ConnectionError(CLIError):
    """Service connection error (Dagster, Neo4j, APIs)."""

    def __init__(self, message: str, service: str = "", suggestions: list[str] | None = None) -> None:
        default_suggestions = suggestions or [
            f"Check if {service or 'the service'} is running",
            "Verify connection settings in config/base.yaml",
            "Check network connectivity",
        ]
        super().__init__(message, exit_code=EXIT_CONNECTION_ERROR, suggestions=default_suggestions)


class DataError(CLIError):
    """Data-related error (missing files, corrupt data)."""

    def __init__(self, message: str, suggestions: list[str] | None = None) -> None:
        default_suggestions = suggestions or [
            "Verify data files exist in the expected location",
            "Run 'sbir-cli ingest' to refresh data",
            "Check file permissions",
        ]
        super().__init__(message, exit_code=EXIT_DATA_ERROR, suggestions=default_suggestions)


def _infer_exit_code(error: Exception) -> int:
    """Infer an appropriate exit code from an exception type and message."""
    error_str = str(error).lower()
    if "connection" in error_str or "connect" in error_str or "timeout" in error_str:
        return EXIT_CONNECTION_ERROR
    if "config" in error_str or "configuration" in error_str or "validation" in error_str:
        return EXIT_CONFIG_ERROR
    if "not found" in error_str or "no such file" in error_str or "missing" in error_str:
        return EXIT_DATA_ERROR
    return EXIT_RUNTIME_ERROR


def _infer_suggestions(error: Exception) -> list[str]:
    """Generate context-aware suggestions based on error type and message."""
    error_str = str(error).lower()

    if "connection" in error_str or "connect" in error_str or "timeout" in error_str:
        return [
            "Check if services (Dagster, Neo4j) are running",
            "Verify connection settings in config/base.yaml",
            "Check network connectivity",
        ]
    if "config" in error_str or "configuration" in error_str:
        return [
            "Verify config/base.yaml syntax",
            "Check environment variable overrides (SBIR_ETL__*)",
            "Run with --verbose for detailed error messages",
        ]
    if "import" in error_str or "module" in error_str:
        return [
            "Run 'uv sync' to ensure dependencies are installed",
            "Check Python path and virtual environment",
        ]
    if "permission" in error_str or "access denied" in error_str:
        return [
            "Check file and directory permissions",
            "Verify AWS credentials if accessing S3 resources",
        ]
    if "not found" in error_str or "no such file" in error_str:
        return [
            "Verify the file path exists",
            "Run 'sbir-cli ingest' to populate data files",
            "Check paths configuration in config/base.yaml",
        ]
    return []


def format_error(
    error: Exception,
    context: CommandContext | None = None,
    include_suggestions: bool = True,
) -> Panel:
    """Format an error for Rich display.

    Args:
        error: Exception to format
        context: Optional command context
        include_suggestions: Include troubleshooting suggestions

    Returns:
        Rich Panel with formatted error
    """
    # Build error text
    error_text = Text()
    error_text.append("Error: ", style="bold red")
    error_text.append(str(error), style="red")

    # Add error type if it's not a generic Exception
    error_type = type(error).__name__
    if error_type not in ("Exception", "CLIError"):
        error_text.append(f"\n\nType: {error_type}", style="dim")

    # Add suggestions if available
    suggestions: list[str] = []
    if isinstance(error, CLIError) and error.suggestions:
        suggestions = error.suggestions
    elif include_suggestions:
        suggestions = _infer_suggestions(error)

    if suggestions:
        suggestion_text = Text("\n\nSuggested fixes:", style="bold yellow")
        for i, suggestion in enumerate(suggestions, 1):
            suggestion_text.append(f"\n  {i}. {suggestion}", style="yellow")
        error_text.append(suggestion_text)

    return Panel(error_text, title="Error", border_style="red")


def handle_error(
    error: Exception,
    context: CommandContext | None = None,
    exit_code: int | None = None,
) -> None:
    """Handle and display an error, then exit.

    Args:
        error: Exception to handle
        context: Optional command context
        exit_code: Override exit code (uses error.exit_code if CLIError)
    """
    console = context.console if context else Console()

    # Format and display error
    error_panel = format_error(error, context=context)
    console.print(error_panel)

    # Determine exit code
    if exit_code is not None:
        code = exit_code
    elif isinstance(error, CLIError):
        code = error.exit_code
    else:
        code = 1

    raise typer.Exit(code=code)


def handle_cli_error(func: Any) -> Any:
    """Decorator to handle errors in CLI commands.

    Catches exceptions and formats them nicely before exiting.
    """
    import functools

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except typer.Exit:
            raise  # Re-raise typer exits
        except Exception as e:
            # Try to get context from kwargs or first arg
            context = kwargs.get("ctx")
            if context and hasattr(context, "obj"):
                ctx_obj = context.obj
                if isinstance(ctx_obj, CommandContext):
                    handle_error(e, context=ctx_obj)
            else:
                handle_error(e)

    return wrapper
