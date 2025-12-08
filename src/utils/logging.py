"""Compatibility wrapper for legacy logging imports.

This project consolidated logging helpers under
`src.utils.common.logging_config`.  Some notebooks and scripts still import
`src.utils.logging`, so we re-export the public API here to avoid breaking
older tooling until everything is updated.
"""

from src.utils.common.logging_config import (
    LogContext,
    configure_logging_from_config,
    log_debug,
    log_error,
    log_exception,
    log_info,
    log_warning,
    log_with_context,
    setup_logging,
)


__all__ = [
    "LogContext",
    "configure_logging_from_config",
    "log_debug",
    "log_error",
    "log_exception",
    "log_info",
    "log_warning",
    "log_with_context",
    "setup_logging",
]
