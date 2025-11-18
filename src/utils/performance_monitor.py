# sbir-etl/src/utils/performance_monitor.py
"""Performance monitoring and reporting utilities for SBIR ETL operations.

This module provides:
- Decorators and context managers for tracking memory usage, execution time
- Performance metrics containers and comparison utilities
- Report generation (Markdown, HTML) for benchmarks and asset metrics
- Baseline comparison and regression detection

Usage examples:
    from src.utils.performance_monitor import performance_monitor, time_block, monitor_block

    @performance_monitor.time_function
    def my_task(...):
        ...

    with time_block("phase1"):
        do_work()

    with monitor_block("heavy_phase"):
        do_heavy_work()
"""

from __future__ import annotations

import contextlib
import functools
import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from loguru import logger

try:
    from ..reporting.formats.html_templates import HTMLReportBuilder
except Exception:
    HTMLReportBuilder = None  # type: ignore[assignment, unused-ignore]


T = TypeVar("T")

# psutil is optional; when available we record memory usage
try:
    import psutil

    _PSUTIL_AVAILABLE = True
except Exception:
    psutil = None  # type: ignore[assignment, unused-ignore]
    _PSUTIL_AVAILABLE = False


class PerformanceMonitor:
    """Performance monitoring utility for tracking resource usage and timing."""

    def __init__(self) -> None:
        """Initialize performance monitor."""
        # metrics: name -> list of measurement dicts
        self.metrics: dict[str, list[dict[str, Any]]] = {}
        self._process = psutil.Process() if _PSUTIL_AVAILABLE else None

    # -----------------------
    # Decorators
    # -----------------------
    def time_function(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator to measure elapsed time for a function call.

        Records a metric entry under the function name with start/end/duration.
        """

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                end = time.time()
                duration = end - start
                self._record(
                    func.__name__,
                    {
                        "operation": "function_call",
                        "start_time": start,
                        "end_time": end,
                        "duration": duration,
                    },
                )

        return wrapper

    def monitor_memory(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorator to record memory usage before/after function execution.

        When psutil is not available this decorator falls back to timing only.
        """

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            if not _PSUTIL_AVAILABLE or self._process is None:
                # Fallback to timing-only
                return self.time_function(func)(*args, **kwargs)

            start_time = time.time()
            start_mem = self._get_memory_mb()
            try:
                return func(*args, **kwargs)
            finally:
                end_time = time.time()
                end_mem = self._get_memory_mb()
                # peak memory best-effort if available via memory_info (platform dependent)
                peak_mem = self._get_peak_memory_mb()
                self._record(
                    f"{func.__name__}_memory",
                    {
                        "operation": "memory_monitor",
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration": end_time - start_time,
                        "start_memory_mb": start_mem,
                        "end_memory_mb": end_mem,
                        "peak_memory_mb": peak_mem,
                        "memory_delta_mb": end_mem - start_mem,
                    },
                )

        return wrapper

    # -----------------------
    # Context managers
    # -----------------------
    @contextmanager
    def time_block(self, name: str) -> Iterator[None]:
        """Context manager to time a block of code.

        Example:
            with performance_monitor.time_block("import_csv"):
                import_csv(...)
        """
        start = time.time()
        try:
            yield
        finally:
            end = time.time()
            duration = end - start
            self._record(
                name,
                {
                    "operation": "time_block",
                    "start_time": start,
                    "end_time": end,
                    "duration": duration,
                },
            )

    @contextmanager
    def monitor_block(self, name: str) -> Iterator[None]:
        """Context manager to measure time and memory for a block of code.

        If psutil is unavailable, falls back to time_block behavior.
        """
        if not _PSUTIL_AVAILABLE or self._process is None:
            with self.time_block(name):
                yield
            return

        start_time = time.time()
        start_mem = self._get_memory_mb()
        try:
            yield
        finally:
            end_time = time.time()
            end_mem = self._get_memory_mb()
            peak_mem = self._get_peak_memory_mb()
            self._record(
                name,
                {
                    "operation": "monitor_block",
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": end_time - start_time,
                    "start_memory_mb": start_mem,
                    "end_memory_mb": end_mem,
                    "peak_memory_mb": peak_mem,
                    "memory_delta_mb": end_mem - start_mem,
                },
            )

    # -----------------------
    # Helpers / introspection
    # -----------------------
    def _get_memory_mb(self) -> float:
        """Return current resident memory usage (MB) for the running process."""
        if not self._process:
            return 0.0
        try:
            return float(self._process.memory_info().rss) / (1024 * 1024)
        except Exception:
            return 0.0

    def _get_peak_memory_mb(self) -> float:
        """Return a best-effort peak memory usage (MB). Implementation is platform dependent."""
        if not self._process:
            return 0.0
        try:
            # Some platforms expose peak_wset/peak_rss; fall back to rss if not available
            info = self._process.memory_info()
            peak = getattr(info, "peak_wset", None) or getattr(info, "peak_rss", None) or info.rss
            return float(peak) / (1024 * 1024)
        except Exception:
            try:
                return float(self._process.memory_info().rss) / (1024 * 1024)
            except Exception:
                return 0.0

    def _record(self, name: str, data: dict[str, Any]) -> None:
        """Record a metric entry for a named operation."""
        bucket = self.metrics.setdefault(name, [])
        # enrich with timestamp
        data.setdefault("timestamp", time.time())
        bucket.append(data)

    def get_latest_metric(self, name: str) -> dict[str, Any] | None:
        """Return the most recent metric entry for a given name, or None."""
        bucket = self.metrics.get(name)
        if not bucket:
            return None
        return bucket[-1]

    def get_metrics_summary(self) -> dict[str, dict[str, Any]]:
        """Return a summarized view of collected metrics.

        Summary includes count, total/avg/max duration, memory stats where available.
        """
        summary: dict[str, dict[str, Any]] = {}
        for name, entries in self.metrics.items():
            durations = [e.get("duration", 0.0) for e in entries if "duration" in e]
            memory_deltas = [
                e.get("memory_delta_mb", 0.0) for e in entries if "memory_delta_mb" in e
            ]
            peak_memories = [e.get("peak_memory_mb", 0.0) for e in entries if "peak_memory_mb" in e]
            summary[name] = {
                "count": len(entries),
                "total_duration": sum(durations),
                "avg_duration": (sum(durations) / len(durations)) if durations else 0.0,
                "max_duration": max(durations) if durations else 0.0,
                "total_memory_delta_mb": sum(memory_deltas),
                "avg_memory_delta_mb": (sum(memory_deltas) / len(memory_deltas))
                if memory_deltas
                else 0.0,
                "max_peak_memory_mb": max(peak_memories) if peak_memories else 0.0,
                "latest": entries[-1] if entries else None,
            }
        return summary

    def reset_metrics(self) -> None:
        """Clear all collected metrics."""
        self.metrics.clear()

    def export_metrics(self, filepath: str) -> None:
        """Export raw metrics to a JSON file."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.metrics, f, indent=2, default=str)

    def get_performance_report(self) -> dict[str, Any]:
        """Return a comprehensive performance report with summary and overall stats."""
        summary = self.get_metrics_summary()
        total_operations = sum(s.get("count", 0) for s in summary.values())
        total_duration = sum(s.get("total_duration", 0.0) for s in summary.values())
        avg_operation_duration = (total_duration / total_operations) if total_operations else 0.0
        return {
            "summary": summary,
            "overall": {
                "total_operations": total_operations,
                "total_duration": total_duration,
                "avg_operation_duration": avg_operation_duration,
            },
            "psutil_available": _PSUTIL_AVAILABLE,
            "timestamp": time.time(),
        }

    def export_metrics_for_reporting(self) -> dict[str, Any]:
        """Export metrics in standard format for reporting modules.

        Returns:
            Dictionary with metrics formatted for performance_reporting and statistical_reporter
        """
        summary = self.get_metrics_summary()
        total_operations = sum(s.get("count", 0) for s in summary.values())
        total_duration = sum(s.get("total_duration", 0.0) for s in summary.values())
        max_peak_memory = max(
            (s.get("max_peak_memory_mb", 0.0) for s in summary.values()), default=0.0
        )
        avg_memory_delta = sum(
            (s.get("avg_memory_delta_mb", 0.0) for s in summary.values())
        ) / len(summary) if summary else 0.0

        return {
            "total_duration_seconds": total_duration,
            "total_operations": total_operations,
            "peak_memory_mb": max_peak_memory,
            "avg_memory_delta_mb": avg_memory_delta,
            "psutil_available": _PSUTIL_AVAILABLE,
            "timestamp": time.time(),
            "summary": summary,
        }

    def get_metrics_for_alerts(self) -> dict[str, Any]:
        """Get metrics in format suitable for alert generation.

        Returns:
            Dictionary with key metrics that can be checked against thresholds
        """
        summary = self.get_metrics_summary()
        total_duration = sum(s.get("total_duration", 0.0) for s in summary.values())
        max_peak_memory = max(
            (s.get("max_peak_memory_mb", 0.0) for s in summary.values()), default=0.0
        )
        avg_memory_delta = sum(
            (s.get("avg_memory_delta_mb", 0.0) for s in summary.values())
        ) / len(summary) if summary else 0.0

        return {
            "total_duration_seconds": total_duration,
            "peak_memory_mb": max_peak_memory,
            "avg_memory_delta_mb": avg_memory_delta,
            "operation_count": sum(s.get("count", 0) for s in summary.values()),
        }


# Global instance and convenience helpers
performance_monitor = PerformanceMonitor()


def time_function(func: Callable) -> Callable:
    """Module-level convenience decorator for timing a function."""
    return performance_monitor.time_function(func)


def monitor_memory(func: Callable[..., T]) -> Callable[..., T]:
    """Module-level convenience decorator for memory monitoring."""
    return performance_monitor.monitor_memory(func)


@contextlib.contextmanager
def time_block(name: str) -> Iterator[None]:
    """Module-level convenience context manager to time a block."""
    with performance_monitor.time_block(name):
        yield


@contextlib.contextmanager
def monitor_block(name: str) -> Iterator[None]:
    """Module-level convenience context manager to monitor time & memory for a block."""
    with performance_monitor.monitor_block(name):
        yield


# ============================================================================
# Performance Reporting (merged from performance_reporting.py)
# ============================================================================


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


class PerformanceReporter:
    """Generate performance reports from metrics and benchmarks."""

    def __init__(
        self,
        time_warning_threshold: float = 10.0,
        time_failure_threshold: float = 25.0,
        memory_warning_threshold: float = 20.0,
        memory_failure_threshold: float = 50.0,
        match_rate_failure_threshold: float = -5.0,
    ):
        """Initialize reporter with regression thresholds.

        Args:
            time_warning_threshold: Time increase % for warning (default 10%)
            time_failure_threshold: Time increase % for failure (default 25%)
            memory_warning_threshold: Memory increase % for warning (default 20%)
            memory_failure_threshold: Memory increase % for failure (default 50%)
            match_rate_failure_threshold: Match rate decrease % for failure (default -5%)
        """
        self.time_warning_threshold = time_warning_threshold
        self.time_failure_threshold = time_failure_threshold
        self.memory_warning_threshold = memory_warning_threshold
        self.memory_failure_threshold = memory_failure_threshold
        self.match_rate_failure_threshold = match_rate_failure_threshold

    def compare_metrics(
        self,
        baseline: PerformanceMetrics,
        current: PerformanceMetrics,
    ) -> MetricComparison:
        """Compare current metrics against baseline and detect regressions.

        Args:
            baseline: Baseline performance metrics
            current: Current performance metrics

        Returns:
            MetricComparison with analysis and severity
        """
        # Calculate deltas
        time_delta_percent = (
            (
                (current.total_duration_seconds - baseline.total_duration_seconds)
                / baseline.total_duration_seconds
                * 100
            )
            if baseline.total_duration_seconds > 0
            else 0
        )

        memory_delta_percent = (
            ((current.peak_memory_mb - baseline.peak_memory_mb) / baseline.peak_memory_mb * 100)
            if baseline.peak_memory_mb > 0
            else 0
        )

        match_rate_delta_percent = None
        if baseline.match_rate is not None and current.match_rate is not None:
            match_rate_delta_percent = (current.match_rate - baseline.match_rate) * 100

        # Assess severity
        messages = []
        severity = "PASS"

        # Time checks
        if time_delta_percent > self.time_failure_threshold:
            messages.append(
                f"Time regression: +{time_delta_percent:.1f}% "
                f"({baseline.total_duration_seconds:.2f}s → {current.total_duration_seconds:.2f}s)"
            )
            severity = "FAILURE"
        elif time_delta_percent > self.time_warning_threshold:
            messages.append(
                f"Time warning: +{time_delta_percent:.1f}% "
                f"({baseline.total_duration_seconds:.2f}s → {current.total_duration_seconds:.2f}s)"
            )
            if severity == "PASS":
                severity = "WARNING"

        # Memory checks
        if memory_delta_percent > self.memory_failure_threshold:
            messages.append(
                f"Memory regression: +{memory_delta_percent:.1f}% "
                f"({baseline.peak_memory_mb:.0f}MB → {current.peak_memory_mb:.0f}MB)"
            )
            severity = "FAILURE"
        elif memory_delta_percent > self.memory_warning_threshold:
            messages.append(
                f"Memory warning: +{memory_delta_percent:.1f}% "
                f"({baseline.peak_memory_mb:.0f}MB → {current.peak_memory_mb:.0f}MB)"
            )
            if severity == "PASS":
                severity = "WARNING"

        # Match rate checks
        if (
            match_rate_delta_percent is not None
            and match_rate_delta_percent < self.match_rate_failure_threshold
        ):
            messages.append(
                f"Match rate regression: {baseline.match_rate:.1%} → {current.match_rate:.1%}"
            )
            severity = "FAILURE"

        return MetricComparison(
            baseline_metrics=baseline,
            current_metrics=current,
            time_delta_percent=round(time_delta_percent, 1),
            memory_delta_percent=round(memory_delta_percent, 1),
            match_rate_delta_percent=round(match_rate_delta_percent, 1)
            if match_rate_delta_percent
            else None,
            regression_severity=severity,
            regression_messages=messages,
        )

    def format_metrics_markdown(self, metrics: PerformanceMetrics) -> str:
        """Format metrics as Markdown table.

        Args:
            metrics: Performance metrics to format

        Returns:
            Markdown formatted table
        """
        lines = [
            "| Metric | Value |",
            "|--------|-------|",
            f"| Duration | {metrics.total_duration_seconds:.2f}s |",
            f"| Throughput | {metrics.records_per_second:.0f} records/sec |",
            f"| Peak Memory | {metrics.peak_memory_mb:.0f} MB |",
            f"| Avg Memory Delta | {metrics.avg_memory_delta_mb:.0f} MB |",
        ]

        if metrics.match_rate is not None:
            lines.append(f"| Match Rate | {metrics.match_rate:.1%} |")
        if metrics.total_records is not None:
            lines.append(f"| Records Processed | {metrics.total_records} |")
        if metrics.matched_records is not None:
            lines.append(f"| Matched Records | {metrics.matched_records} |")

        return "\n".join(lines)

    def format_comparison_markdown(self, comparison: MetricComparison) -> str:
        """Format comparison as Markdown report.

        Args:
            comparison: MetricComparison results

        Returns:
            Markdown formatted report
        """
        baseline = comparison.baseline_metrics
        current = comparison.current_metrics

        lines = [
            "## Performance Comparison Report",
            "",
            f"**Status:** `{comparison.regression_severity}`",
            "",
        ]

        if comparison.regression_messages:
            lines.append("### Issues Detected")
            lines.append("")
            for msg in comparison.regression_messages:
                lines.append(f"- {msg}")
            lines.append("")

        lines.extend(
            [
                "### Performance Metrics",
                "",
                "| Metric | Baseline | Current | Delta |",
                "|--------|----------|---------|-------|",
                f"| Duration | {baseline.total_duration_seconds:.2f}s | {current.total_duration_seconds:.2f}s | {comparison.time_delta_percent:+.1f}% |",
                f"| Throughput | {baseline.records_per_second:.0f} rec/s | {current.records_per_second:.0f} rec/s | {(current.records_per_second - baseline.records_per_second):+.0f} |",
                f"| Peak Memory | {baseline.peak_memory_mb:.0f} MB | {current.peak_memory_mb:.0f} MB | {comparison.memory_delta_percent:+.1f}% |",
                "",
            ]
        )

        if baseline.match_rate is not None and current.match_rate is not None:
            lines.extend(
                [
                    "### Quality Metrics",
                    "",
                    "| Metric | Baseline | Current | Delta |",
                    "|--------|----------|---------|-------|",
                    f"| Match Rate | {baseline.match_rate:.1%} | {current.match_rate:.1%} | {comparison.match_rate_delta_percent:+.1f}pp |",
                    "",
                ]
            )

        return "\n".join(lines)

    def format_benchmark_markdown(self, benchmark_data: dict[str, Any]) -> str:
        """Format benchmark results as Markdown report.

        Args:
            benchmark_data: Benchmark JSON data

        Returns:
            Markdown formatted report
        """
        metrics = PerformanceMetrics.from_benchmark(benchmark_data)

        lines = [
            "## Benchmark Report",
            "",
            f"**Generated:** {metrics.timestamp or datetime.now().isoformat()}",
            "",
            "### Performance Summary",
            "",
        ]

        lines.append(self.format_metrics_markdown(metrics))
        lines.extend(["", "### Enrichment Statistics", ""])

        stats = benchmark_data.get("enrichment_stats", {})
        if stats:
            lines.append("| Statistic | Value |")
            lines.append("|-----------|-------|")
            lines.append(f"| Total Awards | {stats.get('total_awards', 0)} |")
            lines.append(f"| Matched Awards | {stats.get('matched_awards', 0)} |")
            lines.append(f"| Exact Matches | {stats.get('exact_matches', 0)} |")
            lines.append(f"| Fuzzy Matches | {stats.get('fuzzy_matches', 0)} |")
            lines.append(f"| Match Rate | {stats.get('match_rate', 0):.1%} |")

        # Add regression analysis if present
        regressions = benchmark_data.get("regressions", {})
        if regressions:
            lines.extend(["", "### Regression Analysis", ""])
            analysis = regressions.get("analysis", {})
            lines.append("| Delta | Value |")
            lines.append("|-------|-------|")
            lines.append(f"| Time | {analysis.get('time_delta_percent', 0):+.1f}% |")
            lines.append(f"| Memory | {analysis.get('memory_delta_percent', 0):+.1f}% |")
            if "match_rate_delta_percent" in analysis:
                lines.append(
                    f"| Match Rate | {analysis.get('match_rate_delta_percent', 0):+.1f}pp |"
                )

            if regressions.get("failures"):
                lines.extend(["", "#### ❌ Failures", ""])
                for failure in regressions["failures"]:
                    lines.append(f"- {failure}")

            if regressions.get("warnings"):
                lines.extend(["", "#### ⚠️ Warnings", ""])
                for warning in regressions["warnings"]:
                    lines.append(f"- {warning}")

        return "\n".join(lines)

    def generate_html_report(
        self,
        benchmark_data: dict[str, Any],
        comparison: MetricComparison | None = None,
        title: str = "Performance Report",
    ) -> str:
        """Generate HTML report from benchmark data and optional comparison.

        Args:
            benchmark_data: Benchmark JSON data
            comparison: Optional MetricComparison for regression analysis
            title: Report title

        Returns:
            HTML formatted report
        """
        if HTMLReportBuilder is None:
            logger.warning("HTMLReportBuilder not available; returning Markdown instead")
            return self.format_benchmark_markdown(benchmark_data)

        metrics = PerformanceMetrics.from_benchmark(benchmark_data)
        stats = benchmark_data.get("enrichment_stats", {})
        regressions = benchmark_data.get("regressions", {})

        # Build status badge
        status = "PASS"
        status_color = "green"
        if regressions:
            if regressions.get("failures"):
                status = "FAILURE"
                status_color = "red"
            elif regressions.get("warnings"):
                status = "WARNING"
                status_color = "orange"

        # Build metric cards
        metric_cards = [
            HTMLReportBuilder.create_metric_card(
                "Duration", f"{metrics.total_duration_seconds:.2f}s"
            ),
            HTMLReportBuilder.create_metric_card(
                "Throughput", f"{metrics.records_per_second:.0f} rec/s"
            ),
            HTMLReportBuilder.create_metric_card(
                "Peak Memory", f"{metrics.peak_memory_mb:.0f} MB"
            ),
        ]
        if metrics.match_rate is not None:
            metric_cards.append(
                HTMLReportBuilder.create_metric_card(
                    "Match Rate", f"{metrics.match_rate:.1%}"
                )
            )
        metric_grid = HTMLReportBuilder.create_metric_grid(metric_cards)

        # Build alerts
        alerts = []
        for msg in regressions.get("failures", []):
            alerts.append(HTMLReportBuilder.create_alert(msg, "failure"))
        for msg in regressions.get("warnings", []):
            alerts.append(HTMLReportBuilder.create_alert(msg, "warning"))
        alerts_html = "\n".join(alerts)

        # Build performance metrics table
        perf_table_data = [
            {"Metric": "Total Duration", "Value": f"{metrics.total_duration_seconds:.2f} seconds"},
            {"Metric": "Throughput", "Value": f"{metrics.records_per_second:.0f} records/second"},
            {"Metric": "Peak Memory", "Value": f"{metrics.peak_memory_mb:.0f} MB"},
            {"Metric": "Avg Memory Delta", "Value": f"{metrics.avg_memory_delta_mb:.0f} MB"},
        ]
        perf_table = HTMLReportBuilder.create_table(perf_table_data, ["Metric", "Value"], "Performance Metrics")

        # Build enrichment statistics table
        enrich_table_data = [
            {"Statistic": "Total Awards", "Value": stats.get("total_awards", 0)},
            {"Statistic": "Matched Awards", "Value": stats.get("matched_awards", 0)},
            {"Statistic": "Match Rate", "Value": f"{stats.get('match_rate', 0):.1%}"},
            {"Statistic": "Exact Matches", "Value": stats.get("exact_matches", 0)},
            {"Statistic": "Fuzzy Matches", "Value": stats.get("fuzzy_matches", 0)},
        ]
        enrich_table = HTMLReportBuilder.create_table(enrich_table_data, ["Statistic", "Value"], "Enrichment Statistics")

        # Build regression section if present
        regression_section = ""
        if regressions:
            regression_section = f"<h2>Regression Analysis</h2>{self._html_regression_section(regressions)}"

        # Combine content
        content = f"""
{metric_grid}
{alerts_html}
{perf_table}
{enrich_table}
{regression_section}
"""

        # Generate full report
        html = HTMLReportBuilder.create_report_layout(
            title=title,
            content=content,
            status=status,
            timestamp=metrics.timestamp or datetime.now().isoformat(),
        )
        return html

    @staticmethod
    def _html_regression_section(regressions: dict[str, Any]) -> str:
        """Generate HTML regression analysis section."""
        analysis = regressions.get("analysis", {})
        html = "<table><tr><th>Delta</th><th>Value</th></tr>"
        html += f"<tr><td>Time</td><td class=\"delta-positive\">{analysis.get('time_delta_percent', 0):+.1f}%</td></tr>"
        html += f"<tr><td>Memory</td><td class=\"delta-positive\">{analysis.get('memory_delta_percent', 0):+.1f}%</td></tr>"
        if "match_rate_delta_percent" in analysis:
            html += f"<tr><td>Match Rate</td><td class=\"delta-positive\">{analysis.get('match_rate_delta_percent', 0):+.1f}pp</td></tr>"
        html += "</table>"
        return html

    def save_markdown_report(
        self,
        benchmark_data: dict[str, Any],
        output_path: Path | None = None,
    ) -> Path:
        """Save benchmark as Markdown report.

        Args:
            benchmark_data: Benchmark JSON data
            output_path: Output path (default: reports/benchmarks/report_<timestamp>.md)

        Returns:
            Path where report was saved
        """
        if output_path is None:
            reports_dir = Path("reports/benchmarks")
            reports_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = reports_dir / f"report_{timestamp}.md"

        markdown = self.format_benchmark_markdown(benchmark_data)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            f.write(markdown)

        logger.info(f"Markdown report saved to {output_path}")
        return output_path

    def save_html_report(
        self,
        benchmark_data: dict[str, Any],
        output_path: Path | None = None,
        title: str = "Performance Report",
    ) -> Path:
        """Save benchmark as HTML report.

        Args:
            benchmark_data: Benchmark JSON data
            output_path: Output path (default: reports/benchmarks/report_<timestamp>.html)
            title: Report title

        Returns:
            Path where report was saved
        """
        if output_path is None:
            reports_dir = Path("reports/benchmarks")
            reports_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = reports_dir / f"report_{timestamp}.html"

        html = self.generate_html_report(benchmark_data, title=title)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            f.write(html)

        logger.info(f"HTML report saved to {output_path}")
        return output_path


def load_historical_metrics(metrics_dir: Path) -> list[tuple[Path, PerformanceMetrics]]:
    """Load all historical benchmark metrics from a directory.

    Args:
        metrics_dir: Directory containing benchmark JSON files

    Returns:
        List of (file_path, metrics) tuples sorted by timestamp
    """
    metrics_list = []

    for json_file in sorted(metrics_dir.glob("benchmark_*.json")):
        try:
            with open(json_file) as f:
                data = json.load(f)
            metrics = PerformanceMetrics.from_benchmark(data)
            metrics_list.append((json_file, metrics))
        except Exception as e:
            logger.warning(f"Failed to load metrics from {json_file}: {e}")

    return metrics_list


def analyze_performance_trend(
    metrics_list: list[tuple[Path, PerformanceMetrics]],
) -> dict[str, Any]:
    """Analyze performance trend across multiple benchmark runs.

    Args:
        metrics_list: List of (file_path, metrics) tuples

    Returns:
        Analysis dict with trends, min/max, average
    """
    if not metrics_list:
        return {}

    durations = [m.total_duration_seconds for _, m in metrics_list]
    memories = [m.peak_memory_mb for _, m in metrics_list]
    match_rates = [m.match_rate for _, m in metrics_list if m.match_rate is not None]

    return {
        "run_count": len(metrics_list),
        "duration": {
            "min": min(durations),
            "max": max(durations),
            "avg": sum(durations) / len(durations),
            "trend": "improving" if durations[-1] < durations[0] else "degrading",
        },
        "memory": {
            "min": min(memories),
            "max": max(memories),
            "avg": sum(memories) / len(memories),
            "trend": "improving" if memories[-1] < memories[0] else "degrading",
        },
        "match_rate": {
            "min": min(match_rates) if match_rates else None,
            "max": max(match_rates) if match_rates else None,
            "avg": sum(match_rates) / len(match_rates) if match_rates else None,
        }
        if match_rates
        else None,
    }
