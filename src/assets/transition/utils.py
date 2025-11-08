"""Shared utilities for Transition assets.

This module provides:
- Dagster import shims for testing environments
- Helper functions for file I/O and data processing
- Environment variable utilities
- Data preparation functions
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
from loguru import logger


# Statistical reporting imports
try:  # pragma: no cover - defensive import
    from ..models.quality import ModuleReport  # type: ignore
    from ..utils.reporting.analyzers.transition_analyzer import (
        TransitionDetectionAnalyzer,  # type: ignore
    )
except Exception:
    ModuleReport = None  # type: ignore
    TransitionDetectionAnalyzer = None  # type: ignore

# Re-export these imports for use by other transition modules
from ...config.loader import get_config  # noqa: F401
from ...exceptions import FileSystemError  # noqa: F401
from ...extractors.contract_extractor import ContractExtractor  # noqa: F401
from ...transition.features.vendor_resolver import VendorRecord, VendorResolver  # noqa: F401

# Neo4j imports
try:
    from neo4j import Driver

    from ...loaders import Neo4jClient
except Exception:
    Driver = None
    Neo4jClient = None

# Default Neo4j connection settings
DEFAULT_NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
DEFAULT_NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
DEFAULT_NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "neo4j")
DEFAULT_NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

# Transition loading thresholds
TRANSITION_MIN_NODE_COUNT = int(os.environ.get("SBIR_ETL__TRANSITION__MIN_NODE_COUNT", "1"))
TRANSITION_LOAD_SUCCESS_THRESHOLD = float(
    os.environ.get("SBIR_ETL__TRANSITION__LOAD_SUCCESS_THRESHOLD", "0.95")
)

# Import-safe shims for Dagster
try:
    from dagster import (
        AssetCheckResult,
        AssetCheckSeverity,
        AssetExecutionContext as _RealAssetExecutionContext,
        MetadataValue,
        Output,
        asset,
        asset_check,
    )

    # Wrap the real AssetExecutionContext to accept no args for testing
    class AssetExecutionContext:  # type: ignore
        def __init__(self, op_execution_context=None) -> None:
            if op_execution_context is None:
                # For testing: create a minimal mock-like object
                self.log = logger
                self._is_shim = True
            else:
                # For real usage: use the real Dagster context
                self._real_context = _RealAssetExecutionContext(op_execution_context)
                self.log = self._real_context.log
                self._is_shim = False

except Exception:  # pragma: no cover
    # Minimal shims so this module can be imported without Dagster installed
    def asset(*args, **kwargs):  # type: ignore
        def _wrap(fn):
            return fn

        return _wrap

    class Output:  # type: ignore
        def __init__(self, value, metadata=None):
            self.value = value
            self.metadata = metadata or {}

    class MetadataValue:  # type: ignore
        @staticmethod
        def json(v: Any) -> Any:
            return v

    class AssetExecutionContext:  # type: ignore
        def __init__(self, op_execution_context=None) -> None:
            self.log = logger
            if op_execution_context:
                # Store if provided for compatibility
                self._op_execution_context = op_execution_context

    def asset_check(*args, **kwargs):  # type: ignore
        def _wrap(fn):
            return fn

        return _wrap


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save_dataframe_parquet(df: pd.DataFrame, path: Path) -> None:
    """Persist a DataFrame to parquet, falling back to NDJSON if pyarrow not present."""
    _ensure_parent_dir(path)
    try:
        df.to_parquet(path, index=False)
    except Exception:
        # Fallback to NDJSON in the same directory with .ndjson suffix
        ndjson_path = path.with_suffix(".ndjson")

        # Convert values to JSON-serializable, handling NaN/NaT/NumPy scalars and nested containers
        def _to_jsonable(x):
            try:
                if pd.isna(x):
                    return None
            except Exception:
                pass
            # pandas Timestamps
            if hasattr(x, "isoformat"):
                try:
                    return x.isoformat()
                except Exception:
                    pass
            # NumPy scalars
            try:
                import numpy as _np  # type: ignore

                if isinstance(x, _np.generic):
                    try:
                        return x.item()
                    except Exception:
                        pass
            except Exception:
                pass
            # Containers
            if isinstance(x, dict):
                return {str(k): _to_jsonable(v) for k, v in x.items()}
            if isinstance(x, list | tuple | set):
                return [_to_jsonable(v) for v in list(x)]
            return x

        with ndjson_path.open("w", encoding="utf-8") as fh:
            for _, row in df.iterrows():
                record = {k: _to_jsonable(v) for k, v in row.items()}
                fh.write(json.dumps(record) + "\n")
        logger.warning("Parquet save failed; wrote NDJSON fallback", path=str(ndjson_path))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_parent_dir(path)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


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


def _get_neo4j_driver() -> Driver | None:
    """Create and return a Neo4j driver, or None if unavailable."""
    if Driver is None or Neo4jClient is None:
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


