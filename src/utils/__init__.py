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
from .text_normalization import normalize_company_name, normalize_name, normalize_recipient_name

# Column discovery utilities
from .column_finder import ColumnFinder
from .asset_column_helper import AssetColumnHelper

# Configuration utilities
from .config_accessor import ConfigAccessor


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
    # Text normalization
    "normalize_name",
    "normalize_company_name",
    "normalize_recipient_name",
    # Column discovery
    "ColumnFinder",
    "AssetColumnHelper",
    # Configuration
    "ConfigAccessor",
]
