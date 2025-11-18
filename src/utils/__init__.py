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

# File I/O utilities
from .file_io import (
    read_parquet_or_ndjson,
    save_dataframe_parquet,
    write_json,
    write_json_atomic,
    write_ndjson,
)

# Chunking utilities
from .chunking import (
    ChunkIterator,
    batch_process,
    chunk_dataframe,
    chunk_generator,
    chunk_iterable,
)

# Error handling utilities
from .error_handling import (
    handle_asset_error,
    log_and_raise,
    retry_with_backoff,
    safe_execute,
)


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
    # File I/O
    "save_dataframe_parquet",
    "write_json",
    "write_json_atomic",
    "write_ndjson",
    "read_parquet_or_ndjson",
    # Chunking
    "chunk_dataframe",
    "chunk_iterable",
    "chunk_generator",
    "ChunkIterator",
    "batch_process",
    # Error handling
    "handle_asset_error",
    "log_and_raise",
    "retry_with_backoff",
    "safe_execute",
]
