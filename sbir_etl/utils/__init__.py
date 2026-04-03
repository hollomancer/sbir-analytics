"""Shared utilities for the SBIR ETL pipeline."""

# Cache utilities
from .cache.base_cache import BaseDataFrameCache

# Date utilities
from .date_utils import (
    format_date_iso,
    parse_date,
    parse_date_safe,
    validate_date_range,
)

# Logging utilities
from .logging_config import (
    LogContext,
    configure_logging_from_config,
    log_with_context,
    setup_logging,
)

# Path utilities
from .path_utils import (
    ensure_dir,
    ensure_parent_dir,
    ensure_path_exists,
    normalize_path_list,
    resolve_path,
    safe_path_join,
)

# Chunking utilities
from .data.chunking import (
    ChunkIterator,
    batch_process,
    chunk_dataframe,
    chunk_generator,
    chunk_iterable,
)

# DuckDB utilities
from .data.duckdb_client import DuckDBClient, get_duckdb_client

# File I/O utilities
from .data.file_io import (
    read_parquet_or_ndjson,
    save_dataframe_parquet,
    write_json,
    write_json_atomic,
    write_ndjson,
)

# Asset column utilities
from .asset_column_helper import AssetColumnHelper
from .column_finder import ColumnFinder


# Error handling utilities
from .error_handling import handle_asset_error, log_and_raise, retry_with_backoff, safe_execute

# Metrics
from .metrics import MetricsCollector, PipelineMetrics

# Text normalization
from .text_normalization import normalize_company_name, normalize_name, normalize_recipient_name


__all__ = [
    # Cache
    "BaseDataFrameCache",
    # Date utilities
    "parse_date",
    "parse_date_safe",
    "format_date_iso",
    "validate_date_range",
    # Logging
    "LogContext",
    "configure_logging_from_config",
    "log_with_context",
    "setup_logging",
    # Path utilities
    "ensure_dir",
    "ensure_parent_dir",
    "ensure_path_exists",
    "normalize_path_list",
    "resolve_path",
    "safe_path_join",
    # DuckDB
    "DuckDBClient",
    "get_duckdb_client",
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
    # Column discovery
    "ColumnFinder",
    "AssetColumnHelper",
    # Error handling
    "handle_asset_error",
    "log_and_raise",
    "retry_with_backoff",
    "safe_execute",
    # Metrics
    "MetricsCollector",
    "PipelineMetrics",
    # Text normalization
    "normalize_name",
    "normalize_company_name",
    "normalize_recipient_name",
]
