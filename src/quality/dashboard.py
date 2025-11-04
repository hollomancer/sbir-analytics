"""Quality metrics dashboard generation for enrichment pipeline.

This module generates interactive HTML dashboards showing enrichment quality
metrics over time, including match rate trends, fuzzy score distributions,
match method breakdowns, and unmatched award analysis.

Features:
- HTML/Plotly-based interactive dashboards
- Historical trend visualization
- Match method breakdown charts
- Fuzzy score distribution histograms
- Unmatched awards analysis by phase
- Exportable reports
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from loguru import logger


try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


@dataclass
class DashboardMetrics:
    """Container for metrics used in dashboard generation."""

    timestamp: datetime
    match_rate: float
    matched_records: int
    total_records: int
    exact_matches: int
    fuzzy_matches: int
    unmatched_records: int
    fuzzy_scores: list[float] | None = None
    match_methods: dict[str, int] | None = None
    by_phase: dict[str, float] | None = None
    by_company_size: dict[str, float] | None = None


class QualityDashboard:
    """Generates quality metrics dashboards."""

    def __init__(self, output_dir: Path | None = None):
        """Initialize dashboard generator.

        Args:
            output_dir: Directory to save dashboards. Defaults to reports/dashboards/
        """
        self.output_dir = output_dir or Path("reports/dashboards")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not PLOTLY_AVAILABLE:
            logger.warning("Plotly not available; dashboards will be generated as JSON only")

    def load_metrics_history(
        self, history_file: Path, limit: int | None = None
    ) -> list[DashboardMetrics]:
        """Load historical metrics from file.

        Args:
            history_file: Path to metrics history file (JSONL format)
            limit: Maximum number of records to load (most recent first)

        Returns:
            List of DashboardMetrics objects
        """
        metrics_list = []

        if not history_file.exists():
            logger.warning(f"History file not found: {history_file}")
            return metrics_list

        with open(history_file) as f:
            for line in f:
                try:
                    data = json.loads(line)
                    metrics = DashboardMetrics(
                        timestamp=datetime.fromisoformat(
                            data.get("timestamp", datetime.now().isoformat())
                        ),
                        match_rate=data.get("match_rate", 0),
                        matched_records=data.get("matched_records", 0),
                        total_records=data.get("total_records", 0),
                        exact_matches=data.get("exact_matches", 0),
                        fuzzy_matches=data.get("fuzzy_matches", 0),
                        unmatched_records=data.get("unmatched_records", 0),
                        fuzzy_scores=data.get("fuzzy_scores"),
                        match_methods=data.get("match_methods"),
                        by_phase=data.get("by_phase"),
                        by_company_size=data.get("by_company_size"),
                    )
                    metrics_list.append(metrics)
                except (json.JSONDecodeError, ValueError) as e:
                    logger.warning(f"Failed to parse metrics line: {e}")
                    continue

        # Return most recent first
        metrics_list.reverse()

        if limit:
            metrics_list = metrics_list[:limit]

        return metrics_list

    def generate_trend_dashboard(
        self, metrics_history: list[DashboardMetrics], title: str = "Enrichment Quality Trends"
    ) -> Path:
        """Generate dashboard showing quality trends over time.

        Args:
            metrics_history: List of DashboardMetrics objects
            title: Dashboard title

        Returns:
            Path to generated HTML file
        """
        if not metrics_history:
            logger.warning("No metrics history provided")
            return self.output_dir / "empty_dashboard.html"

        output_file = (
            self.output_dir / f"quality_trends_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )

        if not PLOTLY_AVAILABLE:
            return self._generate_json_dashboard(metrics_history, output_file)

        # Create figure with secondary y-axis
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "Match Rate Trend",
                "Records Processed",
                "Match Method Distribution",
                "Unmatched Records Trend",
            ),
            specs=[
                [{"secondary_y": False}, {"secondary_y": False}],
                [{"secondary_y": False}, {"secondary_y": False}],
            ],
        )

        # Extract data
        timestamps = [m.timestamp for m in metrics_history]
        match_rates = [m.match_rate * 100 for m in metrics_history]
        total_records_list = [m.total_records for m in metrics_history]
        matched_records_list = [m.matched_records for m in metrics_history]
        unmatched_records_list = [m.unmatched_records for m in metrics_history]

        # Match rate trend
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=match_rates,
                mode="lines+markers",
                name="Match Rate %",
                line={"color": "green", "width": 2},
            ),
            row=1,
            col=1,
        )
        fig.add_hline(
            y=70, line_dash="dash", line_color="red", row=1, col=1, annotation_text="Threshold"
        )

        # Records processed
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=total_records_list,
                mode="lines+markers",
                name="Total Records",
                line={"color": "blue", "width": 2},
            ),
            row=1,
            col=2,
        )
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=matched_records_list,
                mode="lines+markers",
                name="Matched Records",
                line={"color": "green", "width": 2},
            ),
            row=1,
            col=2,
        )

        # Match method distribution (latest)
        if metrics_history[0].match_methods:
            methods = list(metrics_history[0].match_methods.keys())
            values = list(metrics_history[0].match_methods.values())
            fig.add_trace(
                go.Pie(
                    labels=methods,
                    values=values,
                    name="Match Methods",
                ),
                row=2,
                col=1,
            )

        # Unmatched records trend
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=unmatched_records_list,
                mode="lines+markers",
                name="Unmatched Records",
                line={"color": "red", "width": 2},
            ),
            row=2,
            col=2,
        )

        # Update layout
        fig.update_xaxes(title_text="Timestamp", row=1, col=1)
        fig.update_yaxes(title_text="Match Rate %", row=1, col=1)
        fig.update_xaxes(title_text="Timestamp", row=1, col=2)
        fig.update_yaxes(title_text="Records", row=1, col=2)
        fig.update_xaxes(title_text="Timestamp", row=2, col=2)
        fig.update_yaxes(title_text="Unmatched", row=2, col=2)

        fig.update_layout(
            title=title,
            height=1000,
            showlegend=True,
            hovermode="x unified",
        )

        fig.write_html(output_file)
        logger.info(f"Generated quality trends dashboard: {output_file}")

        return output_file

    def generate_distribution_dashboard(
        self, metrics: DashboardMetrics, title: str = "Enrichment Quality Distribution"
    ) -> Path:
        """Generate dashboard showing distribution metrics for a single run.

        Args:
            metrics: DashboardMetrics object for current run
            title: Dashboard title

        Returns:
            Path to generated HTML file
        """
        output_file = (
            self.output_dir
            / f"quality_distribution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )

        if not PLOTLY_AVAILABLE:
            return self._generate_json_dashboard([metrics], output_file)

        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "Match Rate Summary",
                "Fuzzy Score Distribution",
                "Match Method Breakdown",
                "Quality Metrics Table",
            ),
            specs=[
                [{"type": "indicator"}, {"type": "histogram"}],
                [{"type": "pie"}, {"type": "table"}],
            ],
        )

        # Match rate indicator
        fig.add_trace(
            go.Indicator(
                mode="gauge+number+delta",
                value=metrics.match_rate * 100,
                title={"text": "Match Rate %"},
                delta={"reference": 70},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"color": "darkblue"},
                    "steps": [
                        {"range": [0, 50], "color": "lightgray"},
                        {"range": [50, 70], "color": "lightyellow"},
                        {"range": [70, 100], "color": "lightgreen"},
                    ],
                    "threshold": {
                        "line": {"color": "red", "width": 4},
                        "thickness": 0.75,
                        "value": 70,
                    },
                },
            ),
            row=1,
            col=1,
        )

        # Fuzzy score distribution
        if metrics.fuzzy_scores:
            fig.add_trace(
                go.Histogram(
                    x=metrics.fuzzy_scores,
                    nbinsx=20,
                    name="Fuzzy Scores",
                    marker_color="rgba(0,100,200,0.7)",
                ),
                row=1,
                col=2,
            )
            fig.update_xaxes(title_text="Fuzzy Score", row=1, col=2)
            fig.update_yaxes(title_text="Count", row=1, col=2)

        # Match method breakdown
        if metrics.match_methods:
            methods = list(metrics.match_methods.keys())
            values = list(metrics.match_methods.values())
            fig.add_trace(
                go.Pie(
                    labels=methods,
                    values=values,
                    name="Match Methods",
                ),
                row=2,
                col=1,
            )

        # Quality metrics table
        table_data = {
            "Metric": [
                "Total Records",
                "Matched Records",
                "Unmatched Records",
                "Exact Matches",
                "Fuzzy Matches",
                "Match Rate",
            ],
            "Value": [
                f"{metrics.total_records:,}",
                f"{metrics.matched_records:,}",
                f"{metrics.unmatched_records:,}",
                f"{metrics.exact_matches:,}",
                f"{metrics.fuzzy_matches:,}",
                f"{metrics.match_rate:.1%}",
            ],
        }

        fig.add_trace(
            go.Table(
                header={
                    "values": list(table_data.keys()),
                    "fill_color": "paleturquoise",
                    "align": "left",
                },
                cells={
                    "values": [table_data[k] for k in table_data.keys()],
                    "fill_color": "lavender",
                    "align": "left",
                },
            ),
            row=2,
            col=2,
        )

        fig.update_layout(
            title=title,
            height=900,
            showlegend=True,
        )

        fig.write_html(output_file)
        logger.info(f"Generated quality distribution dashboard: {output_file}")

        return output_file

    def generate_comparison_dashboard(
        self,
        current: DashboardMetrics,
        baseline: DashboardMetrics,
        title: str = "Enrichment Quality Comparison",
    ) -> Path:
        """Generate dashboard comparing current metrics to baseline.

        Args:
            current: Current DashboardMetrics
            baseline: Baseline DashboardMetrics for comparison
            title: Dashboard title

        Returns:
            Path to generated HTML file
        """
        output_file = (
            self.output_dir / f"quality_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )

        if not PLOTLY_AVAILABLE:
            return self._generate_json_dashboard([current, baseline], output_file)

        # Create comparison data
        metrics_names = ["Match Rate", "Exact Matches", "Fuzzy Matches", "Total Records"]
        baseline_values = [
            baseline.match_rate * 100,
            baseline.exact_matches,
            baseline.fuzzy_matches,
            baseline.total_records,
        ]
        current_values = [
            current.match_rate * 100,
            current.exact_matches,
            current.fuzzy_matches,
            current.total_records,
        ]

        fig = go.Figure(
            data=[
                go.Bar(name="Baseline", x=metrics_names, y=baseline_values),
                go.Bar(name="Current", x=metrics_names, y=current_values),
            ]
        )

        fig.update_layout(
            title=title,
            barmode="group",
            xaxis_title="Metric",
            yaxis_title="Value",
            height=600,
        )

        fig.write_html(output_file)
        logger.info(f"Generated quality comparison dashboard: {output_file}")

        return output_file

    def _generate_json_dashboard(
        self, metrics_list: list[DashboardMetrics], output_file: Path
    ) -> Path:
        """Generate JSON-based dashboard (fallback when Plotly unavailable).

        Args:
            metrics_list: List of DashboardMetrics
            output_file: Output file path

        Returns:
            Path to generated file
        """
        dashboard_data = {
            "generated_at": datetime.now().isoformat(),
            "metrics": [
                {
                    "timestamp": m.timestamp.isoformat(),
                    "match_rate": f"{m.match_rate:.1%}",
                    "matched_records": m.matched_records,
                    "total_records": m.total_records,
                    "exact_matches": m.exact_matches,
                    "fuzzy_matches": m.fuzzy_matches,
                    "unmatched_records": m.unmatched_records,
                }
                for m in metrics_list
            ],
        }

        with open(output_file, "w") as f:
            json.dump(dashboard_data, f, indent=2, default=str)

        logger.info(f"Generated JSON dashboard: {output_file}")
        return output_file

    def generate_summary_report(self, metrics_history: list[DashboardMetrics]) -> tuple[str, Path]:
        """Generate Markdown summary report of quality metrics.

        Args:
            metrics_history: List of historical DashboardMetrics

        Returns:
            Tuple of (markdown_content, file_path)
        """
        if not metrics_history:
            return "", self.output_dir / "empty_report.md"

        output_file = (
            self.output_dir / f"quality_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        )

        # Calculate statistics
        latest = metrics_history[0]
        oldest = metrics_history[-1] if len(metrics_history) > 1 else latest

        match_rate_trend = (
            (latest.match_rate - oldest.match_rate) / oldest.match_rate * 100
            if oldest.match_rate > 0
            else 0
        )
        avg_match_rate = sum(m.match_rate for m in metrics_history) / len(metrics_history)
        min_match_rate = min(m.match_rate for m in metrics_history)
        max_match_rate = max(m.match_rate for m in metrics_history)

        # Generate report
        report = f"""# Enrichment Quality Summary Report

**Generated:** {datetime.now().isoformat()}

## Current Metrics

| Metric | Value |
|--------|-------|
| Match Rate | {latest.match_rate:.1%} |
| Matched Records | {latest.matched_records:,} |
| Total Records | {latest.total_records:,} |
| Exact Matches | {latest.exact_matches:,} |
| Fuzzy Matches | {latest.fuzzy_matches:,} |
| Unmatched Records | {latest.unmatched_records:,} |

## Historical Trends (Last {len(metrics_history)} Runs)

| Metric | Value |
|--------|-------|
| Average Match Rate | {avg_match_rate:.1%} |
| Min Match Rate | {min_match_rate:.1%} |
| Max Match Rate | {max_match_rate:.1%} |
| Trend | {match_rate_trend:+.1f}% |

## Match Method Distribution

"""

        if latest.match_methods:
            for method, count in latest.match_methods.items():
                pct = count / latest.matched_records * 100 if latest.matched_records > 0 else 0
                report += f"- **{method}**: {count:,} records ({pct:.1f}%)\n"

        report += "\n## Recommendations\n\n"

        if latest.match_rate < 0.70:
            report += "- ⚠️ **CRITICAL**: Match rate below 70% threshold. Review matching logic.\n"
        elif latest.match_rate < 0.80:
            report += "- ⚠️ **WARNING**: Match rate below 80%. Consider improving matching rules.\n"
        else:
            report += "- ✓ **HEALTHY**: Match rate at or above target.\n"

        if match_rate_trend < -5:
            report += "- ⚠️ Quality declining. Investigate recent changes.\n"
        elif match_rate_trend > 5:
            report += "- ✓ Quality improving. Consider documenting improvements.\n"

        # Save report
        with open(output_file, "w") as f:
            f.write(report)

        logger.info(f"Generated summary report: {output_file}")
        return report, output_file
