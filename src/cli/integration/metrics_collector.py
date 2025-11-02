"""Metrics collector for CLI performance data aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import json
from rich.console import Console
from loguru import logger

from src.config.schemas import PipelineConfig


@dataclass
class PipelineMetrics:
    """Pipeline performance metrics."""

    enrichment_success_rate: float
    processing_throughput: float  # records/second
    memory_usage_mb: float
    error_count: int
    last_updated: datetime


class MetricsCollector:
    """Metrics collector for CLI operations.

    Aggregates performance data from various sources including:
    - Performance monitor data
    - Asset execution metadata
    - Historical metrics files
    """

    def __init__(self, config: PipelineConfig, console: Console) -> None:
        """Initialize metrics collector.

        Args:
            config: Pipeline configuration
            console: Rich console for output
        """
        self.config = config
        self.console = console
        self.reports_dir = Path("reports")
        self.metrics_dir = self.reports_dir / "metrics"

    def get_metrics(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        asset_group: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get performance metrics within a time range.

        Args:
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering
            asset_group: Optional asset group filter

        Returns:
            List of metric dictionaries
        """
        metrics = []

        # Load from reports directory if available
        if self.metrics_dir.exists():
            for metric_file in self.metrics_dir.glob("*.json"):
                try:
                    with open(metric_file, encoding="utf-8") as f:
                        data = json.load(f)

                        # Apply filters
                        if start_date and data.get("timestamp"):
                            metric_time = datetime.fromisoformat(data["timestamp"])
                            if metric_time < start_date:
                                continue

                        if end_date and data.get("timestamp"):
                            metric_time = datetime.fromisoformat(data["timestamp"])
                            if metric_time > end_date:
                                continue

                        if asset_group and data.get("asset_group") != asset_group:
                            continue

                        metrics.append(data)

                except Exception as e:
                    logger.debug(f"Failed to load metric file {metric_file}: {e}")

        return sorted(metrics, key=lambda x: x.get("timestamp", ""), reverse=True)

    def get_latest_metrics(self) -> PipelineMetrics | None:
        """Get latest aggregated pipeline metrics.

        Returns:
            PipelineMetrics or None if no data available
        """
        # Get metrics from last 24 hours
        end_date = datetime.now()
        start_date = end_date - timedelta(days=1)

        metrics = self.get_metrics(start_date=start_date, end_date=end_date)

        if not metrics:
            return None

        # Aggregate metrics
        total_records = sum(m.get("records_processed", 0) for m in metrics)
        total_duration = sum(m.get("duration_seconds", 0) for m in metrics)
        total_errors = sum(m.get("error_count", 0) for m in metrics)
        avg_memory = (
            sum(m.get("peak_memory_mb", 0) for m in metrics) / len(metrics)
            if metrics
            else 0.0
        )
        success_count = sum(1 for m in metrics if m.get("success", False))
        success_rate = success_count / len(metrics) if metrics else 0.0

        throughput = total_records / total_duration if total_duration > 0 else 0.0

        return PipelineMetrics(
            enrichment_success_rate=success_rate,
            processing_throughput=throughput,
            memory_usage_mb=avg_memory,
            error_count=total_errors,
            last_updated=end_date,
        )

    def get_asset_group_metrics(self, asset_group: str) -> list[dict[str, Any]]:
        """Get metrics for a specific asset group.

        Args:
            asset_group: Asset group name

        Returns:
            List of metric dictionaries for the asset group
        """
        return self.get_metrics(asset_group=asset_group)

