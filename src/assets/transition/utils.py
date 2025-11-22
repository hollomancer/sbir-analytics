"""Shared utilities for Transition assets.

This module provides:
- Dagster import shims for testing environments
- Helper functions for file I/O and data processing
- Environment variable utilities
- Data preparation functions
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from uuid import uuid4

import pandas as pd
from loguru import logger

# Configuration and extractor imports (re-exported for use by other transition modules)
from src.config.loader import get_config  # noqa: F401
from src.extractors.contract_extractor import ContractExtractor  # noqa: F401
from src.transition.features.vendor_resolver import VendorRecord, VendorResolver  # noqa: F401


# Statistical reporting imports
try:  # pragma: no cover - defensive import
    from ..models.quality import ModuleReport  # type: ignore
    from ..utils.reporting.analyzers.transition_analyzer import TransitionDetectionAnalyzer
except Exception:
    ModuleReport = None
    TransitionDetectionAnalyzer = None


# Import-safe shims for Dagster
try:
    from dagster import (
        AssetCheckResult,
        AssetCheckSeverity,
        MetadataValue,
        Output,
        asset,
        asset_check,
    )
    from dagster import AssetExecutionContext as _RealAssetExecutionContext

    # Wrap the real AssetExecutionContext to accept no args for testing
    class AssetExecutionContext:
        def __init__(self, op_execution_context: Any = None) -> None:
            if op_execution_context is None:
                # For testing: create a minimal mock-like object
                self.log = logger
                self._is_shim = True
            else:
                # For real usage: use the real Dagster context
                self._real_context = _RealAssetExecutionContext(op_execution_context)
                self.log: Any = self._real_context.log  # type: ignore[assignment, no-redef]
                self._is_shim = False

except Exception:  # pragma: no cover
    # Minimal shims so this module can be imported without Dagster installed
    def asset(*args, **kwargs):  # type: ignore
        def _wrap(fn):
            return fn

        return _wrap

    class Output:  # type: ignore
        def __init__(self, value: Any, metadata=None) -> None:
            self.value = value
            self.metadata = metadata or {}

    class MetadataValue:  # type: ignore
        @staticmethod
        def json(v: Any) -> Any:
            return v

    class AssetExecutionContext:  # type: ignore
        def __init__(self, op_execution_context: Any = None) -> None:
            self.log = logger
            if op_execution_context:
                # Store if provided for compatibility
                self._op_execution_context = op_execution_context

    def asset_check(*args, **kwargs):  # type: ignore
        def _wrap(fn):
            return fn

        return _wrap

    class AssetCheckResult:  # type: ignore
        def __init__(
            self,
            passed: bool,
            severity=None,
            description: str = "",
            metadata: dict | None = None,
        ) -> None:
            self.passed = passed
            self.severity = severity
            self.description = description
            self.metadata = metadata or {}

    class AssetCheckSeverity:  # type: ignore
        ERROR = "ERROR"
        WARN = "WARN"


# Import centralized file I/O utilities
from src.utils.common.path_utils import ensure_parent_dir as _ensure_parent_dir
from src.utils.data.file_io import save_dataframe_parquet, write_json


# Re-export for use by transition assets
__all__ = [
    "Output",
    "MetadataValue",
    "asset",
    "asset_check",
    "AssetExecutionContext",
    "AssetCheckResult",
    "AssetCheckSeverity",
    "now_utc_iso",
    "_norm_name",
    "_env_float",
    "_env_int",
    "_env_bool",
    "_ensure_parent_dir",
    "save_dataframe_parquet",
    "write_json",
]


def now_utc_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def _norm_name(s: str | None) -> str:
    return (s or "").strip().lower()


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except Exception:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except Exception:
        return default


def _env_bool(key: str, default: bool) -> bool:
    v = os.getenv(key)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


# Neo4j imports (import-safe)
try:
    from neo4j import Driver

    from src.loaders.neo4j import Neo4jClient, Neo4jConfig
except Exception:
    Driver = None  # type: ignore
    Neo4jClient = None  # type: ignore
    Neo4jConfig = None  # type: ignore

# Neo4j configuration defaults
DEFAULT_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
DEFAULT_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")
DEFAULT_NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

# Transition loading thresholds
TRANSITION_MIN_NODE_COUNT = _env_int("SBIR_ETL__TRANSITION__MIN_NODE_COUNT", 100)
TRANSITION_LOAD_SUCCESS_THRESHOLD = _env_float("SBIR_ETL__TRANSITION__LOAD_SUCCESS_THRESHOLD", 0.99)


def _get_neo4j_driver() -> Any:
    """Create and return a Neo4j driver, or None if unavailable.

    DEPRECATED: Use _get_neo4j_client() instead. This function is kept for
    backward compatibility with TransitionProfileLoader.
    """
    if Driver is None:
        logger.warning("Neo4j driver unavailable; skipping Neo4j operations")
        return None

    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            DEFAULT_NEO4J_URI,
            auth=(DEFAULT_NEO4J_USER, DEFAULT_NEO4J_PASSWORD),
        )
        driver.verify_connectivity()
        logger.info("✓ Connected to Neo4j")
        return driver
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        raise


def _get_neo4j_client() -> Any:
    """Create and return a Neo4jClient, or None if unavailable."""
    if Neo4jClient is None or Neo4jConfig is None:
        logger.warning("Neo4j client unavailable; skipping Neo4j operations")
        return None

    try:
        config = Neo4jConfig(
            uri=DEFAULT_NEO4J_URI,
            username=DEFAULT_NEO4J_USER,
            password=DEFAULT_NEO4J_PASSWORD,
            database=DEFAULT_NEO4J_DATABASE,
        )
        client = Neo4jClient(config)
        # Verify connectivity
        with client.session() as session:
            session.run("RETURN 1")
        logger.info("✓ Connected to Neo4j via Neo4jClient")
        return client
    except Exception as e:
        logger.error(f"Failed to connect to Neo4j: {e}")
        raise


def _prepare_transition_dataframe(transitions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare transition DataFrame for loading into Neo4j.

    Ensures required columns exist and generates transition_id if missing.
    """
    df = transitions_df.copy()

    # Ensure transition_id column exists
    if "transition_id" not in df.columns:
        df["transition_id"] = [f"TRANS-{uuid4().hex[:12].upper()}" for _ in range(len(df))]

    # Ensure required columns exist with sensible defaults
    required_cols = [
        "transition_id",
        "award_id",
        "contract_id",
        "score",
        "method",
        "computed_at",
    ]
    for col in required_cols:
        if col not in df.columns:
            if col == "computed_at":
                df[col] = datetime.utcnow().isoformat()
            elif col == "score":
                df[col] = 0.5
            else:
                df[col] = None

    # Normalize column names for Neo4j
    df["likelihood_score"] = pd.to_numeric(df["score"], errors="coerce").fillna(0.5)

    # Add confidence level based on score
    def _confidence_level(score: float) -> str:
        try:
            s = float(score)
            if s >= 0.75:
                return "high"
            elif s >= 0.60:
                return "likely"
            else:
                return "possible"
        except Exception:
            return "possible"

    df["confidence"] = df["likelihood_score"].apply(_confidence_level)

    # Ensure detection_date
    if "detection_date" not in df.columns:
        if "computed_at" in df.columns:
            df["detection_date"] = df["computed_at"]
        else:
            df["detection_date"] = datetime.utcnow().isoformat()

    return df[
        [
            "transition_id",
            "award_id",
            "contract_id",
            "likelihood_score",
            "confidence",
            "detection_date",
            "method",
        ]
    ]


# -----------------------------
# 0) contracts_ingestion
# -----------------------------
