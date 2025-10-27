"""Statistical reporting for pipeline runs.

This module provides comprehensive statistical reporting capabilities for
pipeline runs, including module-specific reports, unified summaries, and
multiple output formats (HTML, JSON, Markdown).

Features:
- Module-specific report generation
- Unified report aggregation
- HTML dashboards (leveraging Plotly)
- JSON reports (machine-readable)
- Markdown summaries (PR-friendly)
- Historical trend analysis
- Automated insights generation
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.models.quality import (
    ChangesSummary,
    DataHygieneMetrics,
    InsightRecommendation,
    ModuleReport,
    QualitySeverity,
    StatisticalReport,
)

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    logger.warning("Plotly not available; HTML reports will be limited")


class StatisticalReporter:
    """Orchestrator for generating statistical reports across pipeline modules."""

    def __init__(self, output_dir: Path | None = None):
        """Initialize statistical reporter.

        Args:
            output_dir: Directory for saving reports. Defaults to reports/statistical/
        """
        self.output_dir = output_dir or Path("reports/statistical")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Statistical reporter initialized with output dir: {self.output_dir}")

    def generate_module_report(
        self,
        module_name: str,
        run_id: str,
        stage: str,
        metrics: dict[str, Any],
        data_hygiene: DataHygieneMetrics | None = None,
        changes_summary: ChangesSummary | None = None,
    ) -> ModuleReport:
        """Generate a statistical report for a specific module.

        Args:
            module_name: Name of the module (sbir, patent, transition, cet)
            run_id: Pipeline run identifier
            stage: Pipeline stage
            metrics: Module-specific metrics dictionary
            data_hygiene: Optional data hygiene metrics
            changes_summary: Optional changes summary

        Returns:
            ModuleReport instance
        """
        logger.info(f"Generating module report for {module_name}")

        # Calculate success rate
        total_records = metrics.get("total_records", 0)
        records_processed = metrics.get("records_processed", total_records)
        records_failed = total_records - records_processed
        success_rate = records_processed / total_records if total_records > 0 else 0.0

        # Calculate throughput
        duration = metrics.get("duration_seconds", 0.0)
        throughput = records_processed / duration if duration > 0 else 0.0

        module_report = ModuleReport(
            module_name=module_name,
            run_id=run_id,
            timestamp=datetime.now().isoformat(),
            stage=stage,
            total_records=total_records,
            records_processed=records_processed,
            records_failed=records_failed,
            success_rate=success_rate,
            duration_seconds=duration,
            throughput_records_per_second=throughput,
            data_hygiene=data_hygiene,
            changes_summary=changes_summary,
            module_metrics=metrics.get("module_specific", {}),
        )

        logger.info(
            f"Module report generated for {module_name}: "
            f"{records_processed}/{total_records} records, "
            f"success rate: {success_rate:.1%}"
        )

        return module_report

    def aggregate_module_reports(
        self,
        run_id: str,
        module_reports: list[ModuleReport],
        insights: list[InsightRecommendation] | None = None,
    ) -> StatisticalReport:
        """Aggregate multiple module reports into a unified statistical report.

        Args:
            run_id: Pipeline run identifier
            module_reports: List of module reports to aggregate
            insights: Optional list of insights to include

        Returns:
            Unified StatisticalReport
        """
        logger.info(f"Aggregating {len(module_reports)} module reports for run {run_id}")

        # Calculate aggregate statistics
        total_records = sum(r.total_records for r in module_reports)
        total_duration = sum(r.duration_seconds for r in module_reports)

        # Weighted average of success rates
        total_processed = sum(r.records_processed for r in module_reports)
        overall_success_rate = total_processed / total_records if total_records > 0 else 0.0

        # Aggregate data hygiene if available
        aggregate_hygiene = self._aggregate_data_hygiene(module_reports)

        # Aggregate changes if available
        aggregate_changes = self._aggregate_changes(module_reports)

        report = StatisticalReport(
            report_id=f"{run_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            run_id=run_id,
            timestamp=datetime.now().isoformat(),
            report_type="unified",
            total_records_processed=total_records,
            total_duration_seconds=total_duration,
            overall_success_rate=overall_success_rate,
            module_reports=module_reports,
            aggregate_data_hygiene=aggregate_hygiene,
            aggregate_changes=aggregate_changes,
            insights=insights or [],
        )

        logger.info(
            f"Unified report generated: {total_records} records, "
            f"{overall_success_rate:.1%} success rate"
        )

        return report

    def _aggregate_data_hygiene(
        self, module_reports: list[ModuleReport]
    ) -> DataHygieneMetrics | None:
        """Aggregate data hygiene metrics from multiple modules.

        Args:
            module_reports: List of module reports

        Returns:
            Aggregated DataHygieneMetrics or None if no modules have hygiene data
        """
        hygiene_reports = [r.data_hygiene for r in module_reports if r.data_hygiene]

        if not hygiene_reports:
            return None

        total_records = sum(h.total_records for h in hygiene_reports)
        clean_records = sum(h.clean_records for h in hygiene_reports)
        dirty_records = sum(h.dirty_records for h in hygiene_reports)

        # Aggregate quality scores (weighted average)
        quality_mean = (
            sum(h.quality_score_mean * h.total_records for h in hygiene_reports) / total_records
            if total_records > 0
            else 0.0
        )

        return DataHygieneMetrics(
            total_records=total_records,
            clean_records=clean_records,
            dirty_records=dirty_records,
            clean_percentage=(clean_records / total_records * 100) if total_records > 0 else 0.0,
            quality_score_mean=quality_mean,
            quality_score_median=quality_mean,  # Approximation
            quality_score_std=0.0,  # Would need raw data to calculate
            quality_score_min=min(h.quality_score_min for h in hygiene_reports),
            quality_score_max=max(h.quality_score_max for h in hygiene_reports),
            validation_pass_rate=clean_records / total_records if total_records > 0 else 0.0,
            validation_errors=sum(h.validation_errors for h in hygiene_reports),
            validation_warnings=sum(h.validation_warnings for h in hygiene_reports),
        )

    def _aggregate_changes(self, module_reports: list[ModuleReport]) -> ChangesSummary | None:
        """Aggregate changes summary from multiple modules.

        Args:
            module_reports: List of module reports

        Returns:
            Aggregated ChangesSummary or None if no modules have changes data
        """
        changes_reports = [r.changes_summary for r in module_reports if r.changes_summary]

        if not changes_reports:
            return None

        total_records = sum(c.total_records for c in changes_reports)
        records_modified = sum(c.records_modified for c in changes_reports)
        records_unchanged = sum(c.records_unchanged for c in changes_reports)

        # Merge field lists
        all_fields_added = list(set().union(*[set(c.fields_added) for c in changes_reports]))
        all_fields_modified = list(set().union(*[set(c.fields_modified) for c in changes_reports]))

        # Aggregate enrichment sources
        enrichment_sources: dict[str, int] = {}
        for c in changes_reports:
            for source, count in c.enrichment_sources.items():
                enrichment_sources[source] = enrichment_sources.get(source, 0) + count

        return ChangesSummary(
            total_records=total_records,
            records_modified=records_modified,
            records_unchanged=records_unchanged,
            modification_rate=records_modified / total_records if total_records > 0 else 0.0,
            fields_added=all_fields_added,
            fields_modified=all_fields_modified,
            enrichment_sources=enrichment_sources,
        )

    def generate_json_report(self, report: StatisticalReport) -> Path:
        """Generate JSON report file.

        Args:
            report: StatisticalReport to export

        Returns:
            Path to generated JSON file
        """
        output_file = self.output_dir / f"{report.report_id}.json"

        with open(output_file, "w") as f:
            json.dump(report.model_dump(), f, indent=2, default=str)

        logger.info(f"Generated JSON report: {output_file}")
        return output_file

    def generate_markdown_summary(self, report: StatisticalReport) -> tuple[str, Path]:
        """Generate Markdown summary report (PR-friendly).

        Args:
            report: StatisticalReport to summarize

        Returns:
            Tuple of (markdown_content, file_path)
        """
        output_file = self.output_dir / f"{report.report_id}_summary.md"

        markdown = f"""# Pipeline Statistical Report

**Run ID:** `{report.run_id}`
**Generated:** {report.timestamp}
**Type:** {report.report_type}

## Overall Statistics

| Metric | Value |
|--------|-------|
| Total Records Processed | {report.total_records_processed:,} |
| Overall Success Rate | {report.overall_success_rate:.1%} |
| Total Duration | {report.total_duration_seconds:.2f}s |
| Average Throughput | {report.total_records_processed / report.total_duration_seconds:.0f} records/sec |

"""

        # Add module summaries
        if report.module_reports:
            markdown += "## Module Reports\n\n"
            for module in report.module_reports:
                markdown += f"### {module.module_name.upper()}\n\n"
                markdown += (
                    f"- **Records:** {module.records_processed:,} / {module.total_records:,}\n"
                )
                markdown += f"- **Success Rate:** {module.success_rate:.1%}\n"
                markdown += f"- **Duration:** {module.duration_seconds:.2f}s\n"
                markdown += (
                    f"- **Throughput:** {module.throughput_records_per_second:.0f} records/sec\n"
                )
                markdown += "\n"

        # Add data hygiene summary
        if report.aggregate_data_hygiene:
            hygiene = report.aggregate_data_hygiene
            markdown += "## Data Hygiene\n\n"
            markdown += f"- **Clean Records:** {hygiene.clean_records:,} ({hygiene.clean_percentage:.1f}%)\n"
            markdown += f"- **Dirty Records:** {hygiene.dirty_records:,}\n"
            markdown += f"- **Quality Score:** {hygiene.quality_score_mean:.2f}\n"
            markdown += f"- **Validation Pass Rate:** {hygiene.validation_pass_rate:.1%}\n"
            markdown += "\n"

        # Add insights
        if report.insights:
            markdown += "## Insights & Recommendations\n\n"
            for insight in report.insights:
                icon = (
                    "🔴"
                    if insight.priority == QualitySeverity.CRITICAL
                    else "🟡"
                    if insight.priority == QualitySeverity.HIGH
                    else "🟢"
                )
                markdown += f"{icon} **{insight.title}** ({insight.priority})\n\n"
                markdown += f"{insight.message}\n\n"
                if insight.recommendations:
                    markdown += "Recommended actions:\n"
                    for rec in insight.recommendations:
                        markdown += f"- {rec}\n"
                    markdown += "\n"

        with open(output_file, "w") as f:
            f.write(markdown)

        logger.info(f"Generated Markdown summary: {output_file}")
        return markdown, output_file

    def generate_html_report(self, report: StatisticalReport) -> Path:
        """Generate HTML dashboard report using Plotly.

        Args:
            report: StatisticalReport to visualize

        Returns:
            Path to generated HTML file
        """
        output_file = self.output_dir / f"{report.report_id}.html"

        if not PLOTLY_AVAILABLE:
            logger.warning("Plotly not available, generating simple HTML")
            return self._generate_simple_html(report, output_file)

        # Create dashboard with multiple sections
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "Module Success Rates",
                "Processing Throughput",
                "Data Quality Distribution",
                "Records Processed by Module",
            ),
            specs=[
                [{"type": "bar"}, {"type": "bar"}],
                [{"type": "indicator"}, {"type": "pie"}],
            ],
        )

        # Module success rates
        if report.module_reports:
            modules = [m.module_name for m in report.module_reports]
            success_rates = [m.success_rate * 100 for m in report.module_reports]

            fig.add_trace(
                go.Bar(
                    x=modules,
                    y=success_rates,
                    name="Success Rate %",
                    marker_color="green",
                ),
                row=1,
                col=1,
            )

            # Throughput
            throughputs = [m.throughput_records_per_second for m in report.module_reports]
            fig.add_trace(
                go.Bar(
                    x=modules,
                    y=throughputs,
                    name="Records/sec",
                    marker_color="blue",
                ),
                row=1,
                col=2,
            )

            # Records processed pie chart
            records = [m.records_processed for m in report.module_reports]
            fig.add_trace(
                go.Pie(
                    labels=modules,
                    values=records,
                    name="Records Processed",
                ),
                row=2,
                col=2,
            )

        # Quality score indicator
        if report.aggregate_data_hygiene:
            quality_score = report.aggregate_data_hygiene.quality_score_mean * 100

            fig.add_trace(
                go.Indicator(
                    mode="gauge+number",
                    value=quality_score,
                    title={"text": "Overall Quality Score"},
                    gauge={
                        "axis": {"range": [0, 100]},
                        "bar": {"color": "darkblue"},
                        "steps": [
                            {"range": [0, 50], "color": "lightgray"},
                            {"range": [50, 80], "color": "lightyellow"},
                            {"range": [80, 100], "color": "lightgreen"},
                        ],
                    },
                ),
                row=2,
                col=1,
            )

        # Update layout
        fig.update_xaxes(title_text="Module", row=1, col=1)
        fig.update_yaxes(title_text="Success Rate %", row=1, col=1)
        fig.update_xaxes(title_text="Module", row=1, col=2)
        fig.update_yaxes(title_text="Throughput (records/sec)", row=1, col=2)

        fig.update_layout(
            title=f"Pipeline Statistical Report - {report.run_id}",
            height=900,
            showlegend=True,
        )

        fig.write_html(output_file)
        logger.info(f"Generated HTML report: {output_file}")

        return output_file

    def _generate_simple_html(self, report: StatisticalReport, output_file: Path) -> Path:
        """Generate simple HTML report when Plotly is unavailable.

        Args:
            report: StatisticalReport to export
            output_file: Path to save HTML file

        Returns:
            Path to generated file
        """
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Pipeline Report - {report.run_id}</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1, h2, h3 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                .metric {{ font-size: 1.2em; font-weight: bold; color: #4CAF50; }}
            </style>
        </head>
        <body>
            <h1>Pipeline Statistical Report</h1>
            <p><strong>Run ID:</strong> {report.run_id}</p>
            <p><strong>Generated:</strong> {report.timestamp}</p>

            <h2>Overall Statistics</h2>
            <p class="metric">Total Records: {report.total_records_processed:,}</p>
            <p class="metric">Success Rate: {report.overall_success_rate:.1%}</p>
            <p class="metric">Duration: {report.total_duration_seconds:.2f}s</p>

            <h2>Module Reports</h2>
            <table>
                <tr>
                    <th>Module</th>
                    <th>Records Processed</th>
                    <th>Success Rate</th>
                    <th>Duration (s)</th>
                </tr>
        """

        for module in report.module_reports:
            html += f"""
                <tr>
                    <td>{module.module_name}</td>
                    <td>{module.records_processed:,} / {module.total_records:,}</td>
                    <td>{module.success_rate:.1%}</td>
                    <td>{module.duration_seconds:.2f}</td>
                </tr>
            """

        html += """
            </table>
        </body>
        </html>
        """

        with open(output_file, "w") as f:
            f.write(html)

        logger.info(f"Generated simple HTML report: {output_file}")
        return output_file

    def generate_all_formats(self, report: StatisticalReport) -> dict[str, Path]:
        """Generate report in all supported formats.

        Args:
            report: StatisticalReport to export

        Returns:
            Dictionary mapping format names to file paths
        """
        logger.info(f"Generating report in all formats for run {report.run_id}")

        paths = {
            "json": self.generate_json_report(report),
            "html": self.generate_html_report(report),
        }

        markdown_content, markdown_path = self.generate_markdown_summary(report)
        paths["markdown"] = markdown_path

        # Update report with generated paths
        report.report_formats = list(paths.keys())
        report.report_paths = {fmt: str(path) for fmt, path in paths.items()}

        logger.info(f"Generated all report formats: {list(paths.keys())}")
        return paths
