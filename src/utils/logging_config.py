"""Structured logging configuration using loguru."""

import sys
from contextvars import ContextVar
from pathlib import Path

from loguru import logger

from ..config.loader import get_config

# Context variables for structured logging
stage_context: ContextVar[str | None] = ContextVar("stage", default=None)
run_id_context: ContextVar[str | None] = ContextVar("run_id", default=None)


def setup_logging(
    level: str = "INFO",
    format: str | None = None,
    format_type: str | None = None,
    file_path: str | None = None,
    max_file_size_mb: int = 100,
    backup_count: int = 5,
    include_stage: bool = True,
    include_run_id: bool = True,
    include_timestamps: bool = True,
) -> None:
    """Set up structured logging configuration.

    Notes:
    - Accepts both `format` and `format_type` for backward compatibility; `format_type`
      takes precedence if provided.
    - Invalid logging level names are handled gracefully by falling back to 'INFO'.
    """
    # Remove default handler
    logger.remove()

    # Choose format_type, prefer explicit format_type, then format, default to "json"
    chosen_format = format_type or format or "json"
    format_type_local = chosen_format

    # Create format string based on configuration
    format_parts = []

    if include_timestamps:
        format_parts.append("<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green>")

    format_parts.append("<level>{level: <8}</level>")

    if include_stage:
        format_parts.append("<cyan>{extra[stage]: <12}</cyan>")

    if include_run_id:
        format_parts.append("<magenta>{extra[run_id]: <8}</magenta>")

    format_parts.append("<level>{message}</level>")

    if format_type_local == "json":
        # Use JSON format for structured logging
        log_format = "{message}"
        serialize = True
    else:
        # Use pretty format for development
        log_format = " | ".join(format_parts)
        serialize = False

    # Validate logging level; fallback to INFO if invalid
    safe_level = "INFO"
    try:
        # This will raise if the level name doesn't exist in loguru
        logger.level(level)
        safe_level = level
    except Exception:
        # Best-effort warning; don't raise if logger isn't configured yet
        try:
            logger.warning(f"Invalid logging level '{level}' provided; falling back to 'INFO'")
        except Exception:
            pass
        safe_level = "INFO"

    # Add console handler
    logger.add(
        sys.stdout,
        level=safe_level,
        format=log_format,
        serialize=serialize,
        colorize=format_type_local != "json",
    )

    # Add file handler if specified
    if file_path:
        log_file_path = Path(file_path)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_file_path,
            level=safe_level,
            format=log_format,
            serialize=serialize,
            rotation=f"{max_file_size_mb} MB",
            retention=backup_count,
            encoding="utf-8",
        )


def configure_logging_from_config() -> None:
    """Configure logging using the current configuration."""
    config = get_config()

    setup_logging(
        level=config.logging.level,
        format_type=config.logging.format,
        file_path=config.logging.file_path,
        max_file_size_mb=config.logging.max_file_size_mb,
        backup_count=config.logging.backup_count,
        include_stage=config.logging.include_stage,
        include_run_id=config.logging.include_run_id,
        include_timestamps=config.logging.include_timestamps,
    )


class LogContext:
    """Context manager for adding context to log messages."""

    def __init__(self, stage: str | None = None, run_id: str | None = None):
        """Initialize log context.

        Args:
            stage: Pipeline stage name
            run_id: Run identifier
        """
        self.stage = stage
        self.run_id = run_id
        self.stage_token = None
        self.run_id_token = None

    def __enter__(self):
        """Set context variables."""
        if self.stage is not None:
            self.stage_token = stage_context.set(self.stage)
        if self.run_id is not None:
            self.run_id_token = run_id_context.set(self.run_id)

        # Bind context to logger
        extra = {}
        if self.stage:
            extra["stage"] = self.stage
        if self.run_id:
            extra["run_id"] = self.run_id

        if extra:
            return logger.bind(**extra)
        return logger

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Reset context variables."""
        if self.stage_token is not None:
            stage_context.reset(self.stage_token)
        if self.run_id_token is not None:
            run_id_context.reset(self.run_id_token)


def log_with_context(stage: str | None = None, run_id: str | None = None):
    """Context manager for logging with context.

    Args:
        stage: Pipeline stage name
        run_id: Run identifier

    Returns:
        Context manager that yields a logger with context
    """
    return LogContext(stage=stage, run_id=run_id)


# Convenience functions for different log levels
def log_debug(message: str, *args, **kwargs) -> None:
    """Log debug message."""
    logger.bind(stage=stage_context.get(), run_id=run_id_context.get()).debug(
        message, *args, **kwargs
    )


def log_info(message: str, *args, **kwargs) -> None:
    """Log info message."""
    logger.bind(stage=stage_context.get(), run_id=run_id_context.get()).info(
        message, *args, **kwargs
    )


def log_warning(message: str, *args, **kwargs) -> None:
    """Log warning message."""
    logger.bind(stage=stage_context.get(), run_id=run_id_context.get()).warning(
        message, *args, **kwargs
    )


def log_error(message: str, *args, **kwargs) -> None:
    """Log error message."""
    logger.bind(stage=stage_context.get(), run_id=run_id_context.get()).error(
        message, *args, **kwargs
    )


def log_exception(message: str, *args, **kwargs) -> None:
    """Log exception with traceback."""
    logger.bind(stage=stage_context.get(), run_id=run_id_context.get()).exception(
        message, *args, **kwargs
    )
