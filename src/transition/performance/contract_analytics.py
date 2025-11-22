"""DuckDB-based contract analytics for large dataset handling.

This module provides efficient utilities for analyzing large contract datasets (6.7M+)
using DuckDB for columnar operations and vendor-based filtering.

Features:
- Task 17.1: DuckDB for large contract dataset analytics
- Task 17.2: Vendor-based contract filtering (only SBIR vendors)
- Task 17.3: Optimized vendor cross-walk with indexed lookups
- Task 17.5: Caching of vendor resolutions
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger


try:
    import duckdb

    DUCKDB_AVAILABLE = True
except ImportError:
    duckdb = None  # type: ignore
    DUCKDB_AVAILABLE = False


class ContractAnalytics:
    """
    DuckDB-based analytics for large contract datasets.

    Handles 6.7M+ contracts efficiently by using columnar storage
    and indexed lookups for vendor-based filtering.
    """

    def __init__(self, db_path: str | None = None):
        """
        Initialize Contract Analytics.

        Args:
            db_path: Path to DuckDB database file (in-memory if None)
        """
        if not DUCKDB_AVAILABLE:
            raise RuntimeError("DuckDB is required for ContractAnalytics")

        self.db_path = db_path or ":memory:"
        self.conn = duckdb.connect(self.db_path)
        self.stats = {
            "total_contracts": 0,
            "filtered_contracts": 0,
            "vendor_matches": 0,
            "query_time_ms": 0.0,
        }
        self._setup_indexes()

    def _setup_indexes(self) -> None:
        """Create indexes for fast lookups."""
        try:
            # These will be created on table insertion
            logger.debug("DuckDB analytics initialized")
        except Exception as e:
            logger.error(f"Failed to setup indexes: {e}")

    def load_contracts_from_parquet(self, parquet_path: str) -> int:
        """
        Load contracts from Parquet file into DuckDB.

        Args:
            parquet_path: Path to contracts Parquet file

        Returns:
            Number of contracts loaded
        """
        try:
            start_time = time.time()

            # Read Parquet file into DuckDB table
            self.conn.execute(
                f"""
                CREATE TABLE contracts AS
                SELECT * FROM read_parquet('{parquet_path}')
                """
            )

            # Create indexes for common lookups
            self.conn.execute(
                "CREATE INDEX idx_vendor_id ON contracts (vendor_id, vendor_uei, vendor_duns)"
            )
            self.conn.execute("CREATE INDEX idx_contract_id ON contracts (contract_id, piid)")
            self.conn.execute("CREATE INDEX idx_action_date ON contracts (action_date)")

            # Get row count
            result = self.conn.execute("SELECT COUNT(*) as n FROM contracts").fetchall()
            row_count = result[0][0] if result else 0

            duration_ms = (time.time() - start_time) * 1000
            self.stats["total_contracts"] = row_count
            self.stats["query_time_ms"] = duration_ms

            logger.info(f"✓ Loaded {row_count} contracts in {duration_ms:.1f}ms")
            return row_count

        except Exception as e:
            logger.error(f"Failed to load contracts: {e}")
            raise

    def filter_by_vendors(
        self,
        vendor_ids: list[str],
        vendor_ueis: list[str] | None = None,
        vendor_duns: list[str] | None = None,
    ) -> int:
        """
        Filter contracts to only those matching specified vendors.

        Task 17.2: Vendor-based contract filtering

        Args:
            vendor_ids: List of vendor IDs to match
            vendor_ueis: Optional list of UEI codes
            vendor_duns: Optional list of DUNS numbers

        Returns:
            Number of matching contracts
        """
        try:
            start_time = time.time()

            # Build WHERE clause
            conditions = []
            if vendor_ids:
                ids_str = ", ".join(f"'{v}'" for v in vendor_ids)
                conditions.append(f"vendor_id IN ({ids_str})")
            if vendor_ueis:
                ueis_str = ", ".join(f"'{v}'" for v in vendor_ueis)
                conditions.append(f"vendor_uei IN ({ueis_str})")
            if vendor_duns:
                duns_str = ", ".join(f"'{v}'" for v in vendor_duns)
                conditions.append(f"vendor_duns IN ({duns_str})")

            where_clause = " OR ".join(conditions) if conditions else "1=1"

            # Create filtered table
            self.conn.execute(
                f"""
                CREATE TABLE contracts_filtered AS
                SELECT * FROM contracts
                WHERE {where_clause}
                """
            )

            # Count filtered contracts
            result = self.conn.execute("SELECT COUNT(*) as n FROM contracts_filtered").fetchall()
            filtered_count = result[0][0] if result else 0

            # Create index on filtered table for fast vendor matching
            self.conn.execute(
                "CREATE INDEX idx_filtered_vendor ON contracts_filtered (vendor_uei, vendor_duns, vendor_id)"
            )

            duration_ms = (time.time() - start_time) * 1000
            self.stats["filtered_contracts"] = filtered_count
            self.stats["query_time_ms"] = duration_ms

            logger.info(
                f"✓ Filtered to {filtered_count} contracts ({100 * filtered_count / self.stats['total_contracts']:.1f}%) in {duration_ms:.1f}ms"
            )
            return filtered_count

        except Exception as e:
            logger.error(f"Failed to filter contracts: {e}")
            raise

    def vendor_lookup(
        self, vendor_uei: str | None = None, vendor_duns: str | None = None
    ) -> list[dict[str, Any]]:
        """
        Look up contracts for a specific vendor.

        Task 17.3: Optimized vendor cross-walk with indexed lookups

        Args:
            vendor_uei: UEI to search for
            vendor_duns: DUNS number to search for

        Returns:
            List of matching contracts
        """
        try:
            start_time = time.time()

            conditions = []
            if vendor_uei:
                conditions.append(f"vendor_uei = '{vendor_uei}'")
            if vendor_duns:
                conditions.append(f"vendor_duns = '{vendor_duns}'")

            where_clause = " OR ".join(conditions) if conditions else "1=0"

            result = self.conn.execute(
                f"""
                SELECT contract_id, piid, vendor_uei, vendor_duns, action_date, amount
                FROM contracts_filtered
                WHERE {where_clause}
                LIMIT 10000
                """
            ).fetchall()

            duration_ms = (time.time() - start_time) * 1000
            self.stats["query_time_ms"] = duration_ms

            logger.debug(
                f"Found {len(result)} contracts for UEI={vendor_uei} DUNS={vendor_duns} in {duration_ms:.1f}ms"
            )
            return result

        except Exception as e:
            logger.error(f"Failed to lookup vendor: {e}")
            return []

    def get_contracts_dataframe(self) -> pd.DataFrame:
        """
        Get filtered contracts as a Pandas DataFrame.

        Returns:
            DataFrame with filtered contracts
        """
        try:
            df = self.conn.execute("SELECT * FROM contracts_filtered").df()
            logger.info(f"Returned {len(df)} contracts as DataFrame")
            return df
        except Exception as e:
            logger.error(f"Failed to get DataFrame: {e}")
            raise

    def get_stats(self) -> dict[str, Any]:
        """Return analytics statistics."""
        return self.stats.copy()

    def close(self) -> None:
        """Close DuckDB connection."""
        if self.conn:
            self.conn.close()
            logger.debug("DuckDB connection closed")


class VendorResolutionCache:
    """
    Cache for vendor resolution results.

    Task 17.5: Cache vendor resolutions to avoid redundant matching
    """

    def __init__(self, cache_file: str | None = None):
        """
        Initialize vendor resolution cache.

        Args:
            cache_file: Optional file path to persist cache
        """
        self.cache_file = cache_file
        self.cache: dict[str, dict[str, Any]] = {}
        self.hits = 0
        self.misses = 0

        if cache_file and Path(cache_file).exists():
            self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from file."""
        if not self.cache_file:
            return
        try:
            with open(self.cache_file) as f:
                self.cache = json.load(f)
            logger.info(f"Loaded vendor resolution cache: {len(self.cache)} entries")
        except Exception as e:
            logger.warning(f"Failed to load cache: {e}")
            self.cache = {}

    def _save_cache(self) -> None:
        """Save cache to file."""
        if not self.cache_file:
            return

        try:
            Path(self.cache_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w") as f:
                json.dump(self.cache, f, indent=2)
            logger.debug(f"Saved vendor resolution cache: {len(self.cache)} entries")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def get(self, key: str) -> dict[str, Any] | None:
        """
        Get cached vendor resolution.

        Args:
            key: Vendor identifier (UEI, DUNS, or name)

        Returns:
            Cached resolution or None
        """
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        self.misses += 1
        return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        """
        Cache a vendor resolution.

        Args:
            key: Vendor identifier
            value: Resolution result
        """
        self.cache[key] = value

    def get_stats(self) -> dict[str, Any]:
        """Return cache statistics."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0.0
        return {
            "cache_entries": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.1f}%",
        }

    def close(self) -> None:
        """Close and persist cache."""
        self._save_cache()


class PerformanceProfiler:
    """
    Track and profile detection pipeline performance.

    Task 17.6: Profile detection performance (target: ≥10K detections/minute)
    """

    def __init__(self) -> None:
        """Initialize performance profiler."""
        self.timings: dict[str, list[float]] = {}
        self.counters: dict[str, int] = {}

    def record_timing(self, phase: str, duration_ms: float) -> None:
        """
        Record timing for a phase.

        Args:
            phase: Phase name
            duration_ms: Duration in milliseconds
        """
        if phase not in self.timings:
            self.timings[phase] = []
        self.timings[phase].append(duration_ms)

    def record_count(self, counter: str, count: int) -> None:
        """
        Record a counter value.

        Args:
            counter: Counter name
            count: Count value
        """
        if counter not in self.counters:
            self.counters[counter] = 0
        self.counters[counter] += count

    def get_summary(self) -> dict[str, Any]:
        """
        Get performance summary.

        Returns:
            Dictionary with timing and counter summaries
        """
        summary: dict[str, Any] = {
            "timings": {},
            "counters": self.counters.copy(),
            "detections_per_minute": 0.0,
        }

        # Compute timing statistics
        total_ms = 0.0
        for phase, times in self.timings.items():
            if times:
                summary["timings"][phase] = {
                    "count": len(times),
                    "total_ms": sum(times),
                    "avg_ms": sum(times) / len(times),
                    "min_ms": min(times),
                    "max_ms": max(times),
                }
                total_ms += sum(times)

        # Compute throughput
        detections = self.counters.get("total_detections", 0)
        if total_ms > 0 and detections > 0:
            minutes = total_ms / 1000 / 60
            summary["detections_per_minute"] = detections / minutes if minutes > 0 else 0

        return summary

    def log_summary(self) -> None:
        """Log performance summary."""
        summary = self.get_summary()
        dpm = summary["detections_per_minute"]
        logger.info(
            f"Performance: {summary['counters'].get('total_detections', 0)} detections "
            f"at {dpm:.0f} detections/minute"
        )
        for phase, stats in summary["timings"].items():
            logger.info(
                f"  {phase}: avg={stats['avg_ms']:.1f}ms, "
                f"total={stats['total_ms']:.1f}ms ({stats['count']} runs)"
            )
