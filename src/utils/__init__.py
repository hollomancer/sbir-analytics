"""Shared utilities for the SBIR ETL pipeline."""

from .duckdb_client import DuckDBClient, get_duckdb_client
from .logging_config import (
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
from .metrics import MetricsCollector, PipelineMetrics

__all__ = [
    # Logging
    "LogContext",
    "configure_logging_from_config",
    "log_debug",
    "log_error",
    "log_exception",
    "log_info",
    "log_warning",
    "log_with_context",
    "setup_logging",
    # DuckDB
    "DuckDBClient",
    "get_duckdb_client",
    # Metrics
    "MetricsCollector",
    "PipelineMetrics",
]
