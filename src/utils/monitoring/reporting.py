"""Performance reporting utilities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from .metrics import MetricComparison, PerformanceMetrics


try:
    from src.utils.reporting.formats.html_templates import HTMLReportBuilder
except Exception:
    HTMLReportBuilder = None  # type: ignore[assignment, unused-ignore]


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

    def format_comparison_markdown(self, comparison: MetricComparison, title: str = "Performance Comparison Report") -> str:
        """Format comparison as Markdown report.

        Args:
            comparison: MetricComparison results
            title: Report title

        Returns:
            Markdown formatted report
        """
        baseline = comparison.baseline_metrics
        current = comparison.current_metrics

        lines = [
            f"## {title}",
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
        if regressions:
            if regressions.get("failures"):
                status = "FAILURE"
            elif regressions.get("warnings"):
                status = "WARNING"

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
        <div class="header">
            <h1>{title}</h1>
            <div class="status-badge status-{status.lower()}">{status}</div>
        </div>

        {alerts_html}

        {metric_grid}

        <div class="section">
            <h2>Performance Details</h2>
            {perf_table}
        </div>

        <div class="section">
            <h2>Enrichment Statistics</h2>
            {enrich_table}
        </div>

        {regression_section}

        <div class="footer">
            Generated at {datetime.now().isoformat()}
        </div>
        """

        return HTMLReportBuilder.create_report_layout(title, content, status)

    def _html_regression_section(self, regressions: dict[str, Any]) -> str:
        """Generate HTML for regression analysis section."""
        if HTMLReportBuilder is None:
            return ""

        analysis = regressions.get("analysis", {})

        # Create comparison table
        table_data = [
            {"Metric": "Time Delta", "Value": f"{analysis.get('time_delta_percent', 0):+.1f}%"},
            {"Metric": "Memory Delta", "Value": f"{analysis.get('memory_delta_percent', 0):+.1f}%"},
        ]
        if "match_rate_delta_percent" in analysis:
            table_data.append({
                "Metric": "Match Rate Delta",
                "Value": f"{analysis.get('match_rate_delta_percent', 0):+.1f}pp"
            })

        return HTMLReportBuilder.create_table(table_data, ["Metric", "Value"], "Regression Analysis")

    def save_markdown_report(
        self,
        comparison: MetricComparison,
        output_path: Any,
        title: str = "Performance Comparison Report",
    ) -> None:
        """Save comparison report as Markdown file.

        Args:
            comparison: MetricComparison results
            output_path: Path to save report to
            title: Report title
        """
        from pathlib import Path

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        markdown = self.format_comparison_markdown(comparison, title)
        path.write_text(markdown)
        logger.info(f"Saved Markdown report to {path}")

    def save_html_report(
        self,
        comparison: MetricComparison,
        output_path: Any,
        title: str = "Performance Report",
    ) -> None:
        """Save comparison report as HTML file.

        Args:
            comparison: MetricComparison results
            output_path: Path to save report to
            title: Report title
        """
        from pathlib import Path

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Create benchmark data from comparison for HTML generation
        benchmark_data = {
            "performance_metrics": {
                "total_duration_seconds": comparison.current_metrics.total_duration_seconds,
                "records_per_second": comparison.current_metrics.records_per_second,
                "peak_memory_mb": comparison.current_metrics.peak_memory_mb,
                "avg_memory_delta_mb": comparison.current_metrics.avg_memory_delta_mb,
            },
            "enrichment_stats": {},
            "regressions": {
                "analysis": {
                    "time_delta_percent": comparison.time_delta_percent,
                    "memory_delta_percent": comparison.memory_delta_percent,
                    "match_rate_delta_percent": comparison.match_rate_delta_percent,
                },
                "failures": [msg for msg in comparison.regression_messages if comparison.regression_severity == "FAILURE"],
                "warnings": [msg for msg in comparison.regression_messages if comparison.regression_severity == "WARNING"],
            },
        }

        if comparison.current_metrics.match_rate is not None:
            benchmark_data["enrichment_stats"]["match_rate"] = comparison.current_metrics.match_rate
            benchmark_data["enrichment_stats"]["matched_awards"] = comparison.current_metrics.matched_records or 0
            benchmark_data["enrichment_stats"]["total_awards"] = comparison.current_metrics.total_records or 0

        html = self.generate_html_report(benchmark_data, comparison, title)
        path.write_text(html)
        logger.info(f"Saved HTML report to {path}")


def load_historical_metrics(metrics_dir: str | Any) -> list[tuple[str, PerformanceMetrics]]:
    """Load historical metrics from a directory.

    Args:
        metrics_dir: Directory containing JSON metric files

    Returns:
        List of (filename, PerformanceMetrics) tuples, sorted by timestamp
    """
    import json
    from pathlib import Path

    path = Path(metrics_dir)
    if not path.exists():
        return []

    metrics_list = []
    for file_path in path.glob("*.json"):
        try:
            with open(file_path) as f:
                data = json.load(f)
                # Check if it's a valid benchmark file
                if "performance_metrics" in data:
                    metrics = PerformanceMetrics.from_benchmark(data)
                    metrics_list.append((file_path.name, metrics))
        except Exception as e:
            logger.warning(f"Failed to load metrics from {file_path}: {e}")

    # Sort by timestamp if available
    metrics_list.sort(key=lambda x: x[1].timestamp or "")
    return metrics_list


def analyze_performance_trend(metrics_list: list[PerformanceMetrics]) -> dict[str, Any]:
    """Analyze performance trend from a list of metrics.

    Args:
        metrics_list: List of PerformanceMetrics

    Returns:
        Dictionary with trend analysis
    """
    if not metrics_list:
        return {}

    # Extract time series (not currently used but kept for potential future analysis)
    # durations = [m.total_duration_seconds for m in metrics_list]
    # memory_usage = [m.peak_memory_mb for m in metrics_list]

    # Simple trend analysis (compare first vs last)
    if len(metrics_list) >= 2:
        first = metrics_list[0]
        last = metrics_list[-1]

        time_delta = (last.total_duration_seconds - first.total_duration_seconds) / first.total_duration_seconds * 100 if first.total_duration_seconds > 0 else 0
        memory_delta = (last.peak_memory_mb - first.peak_memory_mb) / first.peak_memory_mb * 100 if first.peak_memory_mb > 0 else 0

        trend = {
            "time_delta_percent": time_delta,
            "memory_delta_percent": memory_delta,
            "trend_direction": "degrading" if time_delta > 10 or memory_delta > 10 else "stable"
        }
    else:
        trend = {"status": "insufficient_data"}

    return trend
