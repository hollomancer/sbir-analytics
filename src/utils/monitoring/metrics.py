"""Performance metrics data classes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PerformanceMetrics:
    """Container for performance metrics from a benchmark or asset run.

    This dataclass is used for benchmarking and comparison purposes.
    For pipeline execution metrics, see src.models.statistical_reports.PerformanceMetrics.
    """

    total_duration_seconds: float
    records_per_second: float
    peak_memory_mb: float
    avg_memory_delta_mb: float
    match_rate: float | None = None
    matched_records: int | None = None
    total_records: int | None = None
    exact_matches: int | None = None
    fuzzy_matches: int | None = None
    timestamp: str | None = None

    @classmethod
    def from_benchmark(cls, benchmark_data: dict[str, Any]) -> "PerformanceMetrics":
        """Create PerformanceMetrics from benchmark JSON data.

        Args:
            benchmark_data: Benchmark results dict with performance_metrics and enrichment_stats

        Returns:
            PerformanceMetrics instance
        """
        perf = benchmark_data.get("performance_metrics", {})
        stats = benchmark_data.get("enrichment_stats", {})

        return cls(
            total_duration_seconds=perf.get("total_duration_seconds", 0),
            records_per_second=perf.get("records_per_second", 0),
            peak_memory_mb=perf.get("peak_memory_mb", 0),
            avg_memory_delta_mb=perf.get("avg_memory_delta_mb", 0),
            match_rate=stats.get("match_rate"),
            matched_records=stats.get("matched_awards"),
            total_records=stats.get("total_awards"),
            exact_matches=stats.get("exact_matches"),
            fuzzy_matches=stats.get("fuzzy_matches"),
            timestamp=benchmark_data.get("timestamp"),
        )

    @classmethod
    def from_asset_metadata(cls, metadata: dict[str, Any]) -> "PerformanceMetrics":
        """Create PerformanceMetrics from Dagster asset metadata.

        Args:
            metadata: Asset metadata dict with performance_* keys

        Returns:
            PerformanceMetrics instance
        """
        return cls(
            total_duration_seconds=metadata.get("performance_total_duration_seconds", 0),
            records_per_second=metadata.get("performance_records_per_second", 0),
            peak_memory_mb=metadata.get("performance_peak_memory_mb", 0),
            avg_memory_delta_mb=metadata.get("performance_avg_memory_delta_mb", 0),
            match_rate=metadata.get("enrichment_match_rate"),
            matched_records=metadata.get("enrichment_matched_records"),
            total_records=metadata.get("enrichment_total_records"),
            timestamp=metadata.get("timestamp"),
        )


@dataclass
class MetricComparison:
    """Result of comparing two metric sets."""

    baseline_metrics: PerformanceMetrics
    current_metrics: PerformanceMetrics
    time_delta_percent: float
    memory_delta_percent: float
    match_rate_delta_percent: float | None = None
    regression_severity: str = "PASS"  # PASS, WARNING, FAILURE
    regression_messages: list[str] = field(default_factory=list)
