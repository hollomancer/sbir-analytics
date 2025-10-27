"""Performance reporting utilities for benchmarking and asset metrics.

This module provides utilities to format performance metrics into human-readable
reports (Markdown, HTML) and to compare metrics against historical baselines.

Features:
- Format benchmark metrics into Markdown tables and summaries
- Generate HTML reports with styling
- Compare current metrics to baseline with delta analysis
- Support for multi-run historical analysis
- Configurable thresholds for performance warnings/alerts
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class PerformanceMetrics:
    """Container for performance metrics from a benchmark or asset run."""

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
    regression_messages: list[str] = None

    def __post_init__(self):
        if self.regression_messages is None:
            self.regression_messages = []


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
        metrics = PerformanceMetrics.from_benchmark(benchmark_data)
        stats = benchmark_data.get("enrichment_stats", {})
        regressions = benchmark_data.get("regressions", {})

        # Build status badge
        status = "PASS"
        status_color = "green"
        if regressions:
            regressions.get("analysis", {})
            if regressions.get("failures"):
                status = "FAILURE"
                status_color = "red"
            elif regressions.get("warnings"):
                status = "WARNING"
                status_color = "orange"

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
            color: #333;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 30px;
            margin-bottom: 15px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
        }}
        .status-badge {{
            padding: 10px 20px;
            border-radius: 4px;
            color: white;
            font-weight: bold;
            background-color: {status_color};
        }}
        .timestamp {{
            color: #7f8c8d;
            font-size: 14px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }}
        th {{
            background-color: #ecf0f1;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #bdc3c7;
        }}
        td {{
            padding: 12px;
            border-bottom: 1px solid #ecf0f1;
        }}
        tr:hover {{
            background-color: #f9f9f9;
        }}
        .metric-value {{
            font-weight: 600;
            color: #2980b9;
        }}
        .delta-positive {{
            color: #e74c3c;
        }}
        .delta-negative {{
            color: #27ae60;
        }}
        .delta-neutral {{
            color: #95a5a6;
        }}
        .alert {{
            padding: 12px;
            margin-bottom: 15px;
            border-left: 4px solid;
            background-color: #f9f9f9;
        }}
        .alert-failure {{
            border-left-color: #e74c3c;
            background-color: #fadbd8;
        }}
        .alert-warning {{
            border-left-color: #f39c12;
            background-color: #fdebd0;
        }}
        .metric-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .metric-card {{
            background-color: #ecf0f1;
            padding: 20px;
            border-radius: 4px;
            border-left: 4px solid #3498db;
        }}
        .metric-card-label {{
            font-size: 12px;
            color: #7f8c8d;
            text-transform: uppercase;
            margin-bottom: 8px;
        }}
        .metric-card-value {{
            font-size: 24px;
            font-weight: bold;
            color: #2c3e50;
        }}
        .footer {{
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
            color: #95a5a6;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <div class="status-badge">{status}</div>
        </div>

        <div class="timestamp">Generated: {metrics.timestamp or datetime.now().isoformat()}</div>

        <div class="metric-grid">
            <div class="metric-card">
                <div class="metric-card-label">Duration</div>
                <div class="metric-card-value">{metrics.total_duration_seconds:.2f}s</div>
            </div>
            <div class="metric-card">
                <div class="metric-card-label">Throughput</div>
                <div class="metric-card-value">{metrics.records_per_second:.0f} rec/s</div>
            </div>
            <div class="metric-card">
                <div class="metric-card-label">Peak Memory</div>
                <div class="metric-card-value">{metrics.peak_memory_mb:.0f} MB</div>
            </div>
            <div class="metric-card">
                <div class="metric-card-label">Match Rate</div>
                <div class="metric-card-value">{metrics.match_rate:.1%}</div>
            </div>
        </div>

        {"".join([
            f'<div class="alert alert-failure"><strong>❌ Failure:</strong> {msg}</div>'
            for msg in regressions.get("failures", [])
        ])}

        {"".join([
            f'<div class="alert alert-warning"><strong>⚠️ Warning:</strong> {msg}</div>'
            for msg in regressions.get("warnings", [])
        ])}

        <h2>Performance Metrics</h2>
        <table>
            <tr>
                <th>Metric</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Total Duration</td>
                <td class="metric-value">{metrics.total_duration_seconds:.2f} seconds</td>
            </tr>
            <tr>
                <td>Throughput</td>
                <td class="metric-value">{metrics.records_per_second:.0f} records/second</td>
            </tr>
            <tr>
                <td>Peak Memory</td>
                <td class="metric-value">{metrics.peak_memory_mb:.0f} MB</td>
            </tr>
            <tr>
                <td>Avg Memory Delta</td>
                <td class="metric-value">{metrics.avg_memory_delta_mb:.0f} MB</td>
            </tr>
        </table>

        <h2>Enrichment Statistics</h2>
        <table>
            <tr>
                <th>Statistic</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>Total Awards</td>
                <td class="metric-value">{stats.get('total_awards', 0)}</td>
            </tr>
            <tr>
                <td>Matched Awards</td>
                <td class="metric-value">{stats.get('matched_awards', 0)}</td>
            </tr>
            <tr>
                <td>Match Rate</td>
                <td class="metric-value">{stats.get('match_rate', 0):.1%}</td>
            </tr>
            <tr>
                <td>Exact Matches</td>
                <td class="metric-value">{stats.get('exact_matches', 0)}</td>
            </tr>
            <tr>
                <td>Fuzzy Matches</td>
                <td class="metric-value">{stats.get('fuzzy_matches', 0)}</td>
            </tr>
        </table>

        {"<h2>Regression Analysis</h2>" + self._html_regression_section(regressions) if regressions else ""}

        <div class="footer">
            <p>Performance Report Generated by SBIR-ETL Enrichment Pipeline</p>
        </div>
    </div>
</body>
</html>"""
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
