"""Metrics collection for enrichment freshness tracking.

Extends the pipeline metrics framework to emit per-source freshness coverage,
attempt rates, success rates, and SLA compliance metrics.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from ..config.loader import get_config
from ..utils.enrichment_freshness import FreshnessStore


class EnrichmentFreshnessMetrics:
    """Metrics for enrichment freshness tracking."""

    def __init__(
        self,
        source: str,
        total_records: int,
        within_sla: int,
        stale_count: int,
        success_count: int,
        failed_count: int,
        unchanged_count: int,
        attempt_count: int,
        api_calls: int,
        api_errors: int,
        sla_days: int,
    ):
        """Initialize freshness metrics.

        Args:
            source: Enrichment source name
            total_records: Total number of records tracked
            within_sla: Number of records within SLA threshold
            stale_count: Number of stale records
            success_count: Number of successful enrichments
            failed_count: Number of failed enrichments
            unchanged_count: Number of unchanged records (delta detection)
            attempt_count: Total enrichment attempts
            api_calls: Number of API calls made
            api_errors: Number of API errors encountered
            sla_days: SLA threshold in days
        """
        self.source = source
        self.timestamp = datetime.now().isoformat()
        self.total_records = total_records
        self.within_sla = within_sla
        self.stale_count = stale_count
        self.success_count = success_count
        self.failed_count = failed_count
        self.unchanged_count = unchanged_count
        self.attempt_count = attempt_count
        self.api_calls = api_calls
        self.api_errors = api_errors
        self.sla_days = sla_days

        # Calculate derived metrics
        self.coverage_rate = (within_sla / total_records) if total_records > 0 else 0.0
        self.success_rate = (success_count / attempt_count) if attempt_count > 0 else 0.0
        self.staleness_rate = (stale_count / total_records) if total_records > 0 else 0.0
        self.error_rate = (api_errors / api_calls) if api_calls > 0 else 0.0
        self.unchanged_rate = (unchanged_count / attempt_count) if attempt_count > 0 else 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return {
            "source": self.source,
            "timestamp": self.timestamp,
            "sla_days": self.sla_days,
            "records": {
                "total": self.total_records,
                "within_sla": self.within_sla,
                "stale": self.stale_count,
            },
            "enrichments": {
                "attempts": self.attempt_count,
                "success": self.success_count,
                "failed": self.failed_count,
                "unchanged": self.unchanged_count,
            },
            "api": {
                "calls": self.api_calls,
                "errors": self.api_errors,
            },
            "rates": {
                "coverage_rate": self.coverage_rate,
                "success_rate": self.success_rate,
                "staleness_rate": self.staleness_rate,
                "error_rate": self.error_rate,
                "unchanged_rate": self.unchanged_rate,
            },
        }

    def meets_thresholds(
        self,
        min_coverage_rate: float = 0.85,
        min_success_rate: float = 0.90,
        max_error_rate: float = 0.10,
    ) -> dict[str, bool]:
        """Check if metrics meet quality thresholds.

        Args:
            min_coverage_rate: Minimum coverage rate (within SLA)
            min_success_rate: Minimum success rate for enrichments
            max_error_rate: Maximum allowed API error rate

        Returns:
            Dictionary with threshold check results
        """
        return {
            "coverage_threshold_met": self.coverage_rate >= min_coverage_rate,
            "success_threshold_met": self.success_rate >= min_success_rate,
            "error_threshold_met": self.error_rate <= max_error_rate,
        }


class EnrichmentMetricsCollector:
    """Collector for enrichment freshness metrics."""

    def __init__(self, metrics_file: Path | str | None = None):
        """Initialize enrichment metrics collector.

        Args:
            metrics_file: Path to metrics output file. Defaults to config value.
        """
        config = get_config()
        if metrics_file is None:
            metrics_file = config.enrichment_refresh.usaspending.metrics_file

        self.metrics_file = Path(metrics_file)
        self.metrics_file.parent.mkdir(parents=True, exist_ok=True)

        # Track API call counts during collection period
        self.api_call_counts: dict[str, int] = {}
        self.api_error_counts: dict[str, int] = {}

    def record_api_call(self, source: str, error: bool = False) -> None:
        """Record an API call for metrics.

        Args:
            source: Enrichment source name
            error: Whether the call resulted in an error
        """
        self.api_call_counts[source] = self.api_call_counts.get(source, 0) + 1
        if error:
            self.api_error_counts[source] = self.api_error_counts.get(source, 0) + 1

    def compute_metrics(self, source: str) -> EnrichmentFreshnessMetrics:
        """Compute freshness metrics for a source.

        Args:
            source: Enrichment source name

        Returns:
            EnrichmentFreshnessMetrics instance
        """
        config = get_config()
        refresh_config = config.enrichment_refresh.usaspending
        sla_days = refresh_config.sla_staleness_days

        store = FreshnessStore()
        df = store.load_all()

        # Filter to source
        if not df.empty and "source" in df.columns:
            df_source = df[df["source"] == source].copy()
        else:
            df_source = df

        total_records = len(df_source)

        # Count records by status
        if not df_source.empty and "status" in df_source.columns:
            success_count = len(df_source[df_source["status"] == "success"])
            failed_count = len(df_source[df_source["status"] == "failed"])
            unchanged_count = len(df_source[df_source["status"] == "unchanged"])
        else:
            success_count = failed_count = unchanged_count = 0

        # Count stale records
        stale_records = store.get_stale_records(source, sla_days)
        stale_count = len(stale_records)
        within_sla = total_records - stale_count

        # Count attempts
        if not df_source.empty and "attempt_count" in df_source.columns:
            attempt_count = int(df_source["attempt_count"].sum())
        else:
            attempt_count = success_count + failed_count

        # API call metrics
        api_calls = self.api_call_counts.get(source, 0)
        api_errors = self.api_error_counts.get(source, 0)

        return EnrichmentFreshnessMetrics(
            source=source,
            total_records=total_records,
            within_sla=within_sla,
            stale_count=stale_count,
            success_count=success_count,
            failed_count=failed_count,
            unchanged_count=unchanged_count,
            attempt_count=attempt_count,
            api_calls=api_calls,
            api_errors=api_errors,
            sla_days=sla_days,
        )

    def emit_metrics(self, source: str) -> Path:
        """Emit metrics to JSON file.

        Args:
            source: Enrichment source name

        Returns:
            Path to emitted metrics file
        """
        metrics = self.compute_metrics(source)

        # Load existing metrics or create new structure
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file) as f:
                    all_metrics = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load existing metrics: {e}")
                all_metrics = {}
        else:
            all_metrics = {}

        # Update metrics for this source
        if "sources" not in all_metrics:
            all_metrics["sources"] = {}

        all_metrics["sources"][source] = metrics.to_dict()
        all_metrics["last_updated"] = datetime.now().isoformat()

        # Write updated metrics
        with open(self.metrics_file, "w") as f:
            json.dump(all_metrics, f, indent=2)

        logger.info(
            f"Emitted {source} freshness metrics: "
            f"coverage={metrics.coverage_rate:.1%}, "
            f"success={metrics.success_rate:.1%}, "
            f"staleness={metrics.staleness_rate:.1%}"
        )

        return self.metrics_file


def emit_freshness_metrics(source: str = "usaspending") -> Path:
    """Emit freshness metrics for an enrichment source.

    Args:
        source: Enrichment source name

    Returns:
        Path to metrics file
    """
    collector = EnrichmentMetricsCollector()
    return collector.emit_metrics(source)
