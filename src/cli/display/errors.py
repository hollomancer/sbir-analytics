"""Error formatting and display utilities."""

from __future__ import annotations

import sys
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from ..context import CommandContext


class CLIError(Exception):
    """Base exception for CLI errors with exit code support."""

    def __init__(self, message: str, exit_code: int = 1, suggestions: list[str] | None = None) -> None:
        """Initialize CLI error.

        Args:
            message: Error message
            exit_code: Exit code to use (1 for errors, 2 for config errors)
            suggestions: Optional list of suggested fixes
        """
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code
        self.suggestions = suggestions or []


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
    console = context.console if context else Console()

    # Build error text
    error_text = Text()
    error_text.append("✗ ", style="bold red")
    error_text.append(str(error), style="red")

    # Add error type if it's not a generic Exception
    if type(error).__name__ != "Exception":
        error_text.append(f"\n\nType: {type(error).__name__}", style="dim")

    # Add suggestions if available
    suggestions = []
    if isinstance(error, CLIError) and error.suggestions:
        suggestions = error.suggestions
    elif include_suggestions:
        # Generate generic suggestions based on error type
        if "connection" in str(error).lower() or "connect" in str(error).lower():
            suggestions = [
                "Check if services (Dagster, Neo4j) are running",
                "Verify connection settings in config/base.yaml",
                "Check network connectivity",
            ]
        elif "config" in str(error).lower() or "configuration" in str(error).lower():
            suggestions = [
                "Verify config/base.yaml syntax",
                "Check environment variable overrides",
                "Run with --verbose for detailed error messages",
            ]
        elif "import" in str(error).lower():
            suggestions = [
                "Run 'poetry install' to ensure dependencies are installed",
                "Check Python path and virtual environment",
            ]

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

