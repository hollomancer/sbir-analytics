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
- Integration with existing performance monitoring utilities
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from src.models.quality import (
    ChangesSummary,
    DataHygieneMetrics,
    InsightRecommendation,
    QualitySeverity,
)
from src.models.statistical_reports import (
    ExecutiveSummary,
    ModuleMetrics,
    PerformanceMetrics,
    PipelineMetrics,
    ReportArtifact,
    ReportCollection,
    ReportFormat,
)
from src.utils.metrics import MetricsCollector
from src.utils.performance_monitor import performance_monitor

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    logger.warning("Plotly not available; HTML reports will be limited")


class StatisticalReporter:
    """Orchestrator for generating statistical reports across pipeline modules.

    Integrates with existing performance monitoring utilities and provides
    comprehensive reporting capabilities for pipeline runs.
    """

    def __init__(
        self,
        output_dir: Optional[Path] = None,
        config: Optional[Dict[str, Any]] = None,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        """Initialize statistical reporter.

        Args:
            output_dir: Directory for saving reports. Defaults to reports/statistical/
            config: Configuration dictionary for reporting settings
            metrics_collector: Optional metrics collector instance for integration
        """
        self.output_dir = output_dir or Path("reports/statistical")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.config = config or {}
        self.metrics_collector = metrics_collector or MetricsCollector()

        # CI/CD context detection
        self.ci_context = self._detect_ci_context()

        logger.info(f"Statistical reporter initialized with output dir: {self.output_dir}")
        if self.ci_context:
            logger.info(f"CI/CD context detected: {self.ci_context.get('provider', 'unknown')}")

    def _detect_ci_context(self) -> Optional[Dict[str, Any]]:
        """Detect CI/CD environment context.

        Returns:
            Dictionary with CI context information or None if not in CI
        """
        ci_context = {}

        # GitHub Actions
        if os.getenv("GITHUB_ACTIONS"):
            ci_context.update(
                {
                    "provider": "github_actions",
                    "repository": os.getenv("GITHUB_REPOSITORY"),
                    "ref": os.getenv("GITHUB_REF"),
                    "sha": os.getenv("GITHUB_SHA"),
                    "run_id": os.getenv("GITHUB_RUN_ID"),
                    "workflow": os.getenv("GITHUB_WORKFLOW"),
                    "is_pr": os.getenv("GITHUB_EVENT_NAME") == "pull_request",
                    "pr_number": os.getenv("GITHUB_PR_NUMBER"),
                }
            )

        # Add other CI providers as needed
        elif os.getenv("CI"):
            ci_context["provider"] = "unknown_ci"
            ci_context["detected"] = True

        return ci_context if ci_context else None

    def generate_reports(self, run_context: Dict[str, Any]) -> ReportCollection:
        """Generate comprehensive statistical reports for a pipeline run.

        Args:
            run_context: Context information including run_id, modules, etc.

        Returns:
            ReportCollection with all generated report artifacts
        """
        run_id = run_context.get("run_id", f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

        logger.info(f"Generating comprehensive statistical reports for run {run_id}")

        # Collect pipeline metrics
        pipeline_metrics = self._collect_pipeline_metrics(run_id, run_context)

        # Generate report collection
        collection = ReportCollection(
            collection_id=f"{run_id}_reports",
            run_id=run_id,
            generated_at=datetime.now(),
            output_directory=self.output_dir,
            ci_context=self.ci_context,
        )

        # Generate all report formats
        artifacts = self._generate_all_formats(pipeline_metrics, collection)
        collection.artifacts = artifacts
        collection.calculate_totals()

        # Handle CI/CD integration
        if self.ci_context and self.config.get("ci", {}).get("upload_artifacts", True):
            self._handle_ci_integration(collection)

        logger.info(f"Generated {len(artifacts)} report artifacts for run {run_id}")
        return collection

    def generate_module_report(
        self,
        module_name: str,
        run_id: str,
        stage: str,
        metrics_data: Dict[str, Any],
        data_hygiene: Optional[DataHygieneMetrics] = None,
        changes_summary: Optional[ChangesSummary] = None,
    ) -> ModuleMetrics:
        """Generate metrics for a specific pipeline module.

        Args:
            module_name: Name of the module (sbir, patent, transition, cet)
            run_id: Pipeline run identifier
            stage: Pipeline stage
            metrics_data: Module-specific metrics dictionary
            data_hygiene: Optional data hygiene metrics
            changes_summary: Optional changes summary

        Returns:
            ModuleMetrics instance
        """
        logger.info(f"Generating module metrics for {module_name}")

        # Extract timing information
        start_time = metrics_data.get("start_time", datetime.now())
        end_time = metrics_data.get("end_time", datetime.now())
        if isinstance(start_time, (int, float)):
            start_time = datetime.fromtimestamp(start_time)
        if isinstance(end_time, (int, float)):
            end_time = datetime.fromtimestamp(end_time)

        execution_time = end_time - start_time

        # Calculate record processing metrics
        records_in = metrics_data.get("records_in", 0)
        records_out = metrics_data.get("records_out", records_in)
        records_processed = metrics_data.get("records_processed", records_out)
        records_failed = metrics_data.get("records_failed", 0)

        # Calculate success rate
        total_input = max(records_in, records_processed + records_failed)
        success_rate = records_processed / total_input if total_input > 0 else 0.0

        # Calculate throughput
        duration_seconds = execution_time.total_seconds()
        throughput = records_processed / duration_seconds if duration_seconds > 0 else 0.0

        # Extract quality and enrichment metrics
        quality_metrics = metrics_data.get("quality_metrics", {})
        enrichment_coverage = metrics_data.get("enrichment_coverage")
        match_rates = metrics_data.get("match_rates")

        # Performance metrics
        peak_memory_mb = metrics_data.get("peak_memory_mb")
        average_cpu_percent = metrics_data.get("average_cpu_percent")

        module_metrics = ModuleMetrics(
            module_name=module_name,
            stage=stage,
            execution_time=execution_time,
            start_time=start_time,
            end_time=end_time,
            records_in=records_in,
            records_out=records_out,
            records_processed=records_processed,
            records_failed=records_failed,
            success_rate=success_rate,
            throughput_records_per_second=throughput,
            quality_metrics=quality_metrics,
            enrichment_coverage=enrichment_coverage,
            match_rates=match_rates,
            peak_memory_mb=peak_memory_mb,
            average_cpu_percent=average_cpu_percent,
            module_specific_metrics=metrics_data.get("module_specific", {}),
        )

        logger.info(
            f"Module metrics generated for {module_name}: "
            f"{records_processed}/{records_in} records, "
            f"success rate: {success_rate:.1%}"
        )

        return module_metrics

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

    def _collect_pipeline_metrics(
        self, run_id: str, run_context: Dict[str, Any]
    ) -> PipelineMetrics:
        """Collect comprehensive pipeline metrics from various sources.

        Args:
            run_id: Pipeline run identifier
            run_context: Context information for the run

        Returns:
            PipelineMetrics instance with aggregated data
        """
        logger.info(f"Collecting pipeline metrics for run {run_id}")

        # Get performance metrics from performance monitor
        perf_report = performance_monitor.get_performance_report()

        # Calculate overall timing
        start_time = run_context.get("start_time", datetime.now())
        end_time = run_context.get("end_time", datetime.now())
        if isinstance(start_time, (int, float)):
            start_time = datetime.fromtimestamp(start_time)
        if isinstance(end_time, (int, float)):
            end_time = datetime.fromtimestamp(end_time)

        duration = end_time - start_time

        # Aggregate module metrics
        module_metrics = {}
        total_records = 0
        total_processed = 0

        for module_name, module_data in run_context.get("modules", {}).items():
            module_metric = self.generate_module_report(
                module_name=module_name,
                run_id=run_id,
                stage=module_data.get("stage", "unknown"),
                metrics_data=module_data,
            )
            module_metrics[module_name] = module_metric
            total_records += module_metric.records_in
            total_processed += module_metric.records_processed

        # Calculate overall success rate
        overall_success_rate = total_processed / total_records if total_records > 0 else 0.0

        # Create performance metrics
        performance_metrics = PerformanceMetrics(
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            records_per_second=total_processed / duration.total_seconds()
            if duration.total_seconds() > 0
            else 0.0,
            peak_memory_mb=perf_report.get("overall", {}).get("max_peak_memory_mb", 0.0),
            average_memory_mb=0.0,  # Would need to calculate from detailed metrics
            total_retries=0,  # Would need to collect from modules
            failed_operations=sum(m.records_failed for m in module_metrics.values()),
        )

        # Create pipeline metrics
        pipeline_metrics = PipelineMetrics(
            run_id=run_id,
            pipeline_name=run_context.get("pipeline_name", "sbir-etl"),
            environment=run_context.get("environment", "development"),
            timestamp=start_time,
            duration=duration,
            total_records_processed=total_records,
            overall_success_rate=overall_success_rate,
            quality_scores=run_context.get("quality_scores", {}),
            module_metrics=module_metrics,
            performance_metrics=performance_metrics,
            data_coverage_metrics=run_context.get("data_coverage_metrics", {}),
            transition_metrics=run_context.get("transition_metrics"),
            ecosystem_metrics=run_context.get("ecosystem_metrics"),
        )

        return pipeline_metrics

    def _generate_all_formats(
        self, pipeline_metrics: PipelineMetrics, collection: ReportCollection
    ) -> List[ReportArtifact]:
        """Generate reports in all configured formats.

        Args:
            pipeline_metrics: Pipeline metrics to report on
            collection: Report collection to populate

        Returns:
            List of generated report artifacts
        """
        artifacts = []
        enabled_formats = self.config.get("output_formats", ["html", "json", "markdown"])

        for format_name in enabled_formats:
            try:
                format_enum = ReportFormat(format_name)
                artifact = self._generate_format_artifact(pipeline_metrics, format_enum, collection)
                if artifact:
                    artifacts.append(artifact)
            except ValueError:
                logger.warning(f"Unknown report format: {format_name}")
                continue

        return artifacts

    def _generate_format_artifact(
        self, pipeline_metrics: PipelineMetrics, format: ReportFormat, collection: ReportCollection
    ) -> Optional[ReportArtifact]:
        """Generate a single report artifact in the specified format.

        Args:
            pipeline_metrics: Pipeline metrics to report on
            format: Report format to generate
            collection: Report collection context

        Returns:
            ReportArtifact if successful, None otherwise
        """
        start_time = datetime.now()

        try:
            if format == ReportFormat.JSON:
                file_path = self._generate_json_artifact(pipeline_metrics, collection)
            elif format == ReportFormat.HTML:
                file_path = self._generate_html_artifact(pipeline_metrics, collection)
            elif format == ReportFormat.MARKDOWN:
                file_path = self._generate_markdown_artifact(pipeline_metrics, collection)
            elif format == ReportFormat.EXECUTIVE:
                file_path = self._generate_executive_artifact(pipeline_metrics, collection)
            else:
                logger.warning(f"Unsupported format: {format}")
                return None

            # Calculate file size
            file_size = file_path.stat().st_size if file_path.exists() else 0

            # Calculate generation time
            generation_time = (datetime.now() - start_time).total_seconds()

            artifact = ReportArtifact(
                format=format,
                file_path=file_path,
                file_size_bytes=file_size,
                generated_at=start_time,
                generation_duration_seconds=generation_time,
                contains_interactive_elements=(format == ReportFormat.HTML),
                contains_visualizations=(format in [ReportFormat.HTML, ReportFormat.EXECUTIVE]),
            )

            logger.info(f"Generated {format.value} report: {file_path} ({file_size} bytes)")
            return artifact

        except Exception as e:
            logger.error(f"Failed to generate {format.value} report: {e}")
            return None

    def _generate_json_artifact(
        self, pipeline_metrics: PipelineMetrics, collection: ReportCollection
    ) -> Path:
        """Generate JSON report artifact."""
        output_file = self.output_dir / f"{collection.collection_id}.json"

        with open(output_file, "w") as f:
            json.dump(pipeline_metrics.model_dump(), f, indent=2, default=str)

        return output_file

    def _generate_html_artifact(
        self, pipeline_metrics: PipelineMetrics, collection: ReportCollection
    ) -> Path:
        """Generate HTML report artifact."""
        output_file = self.output_dir / f"{collection.collection_id}.html"

        if PLOTLY_AVAILABLE:
            return self._generate_plotly_html(pipeline_metrics, output_file)
        else:
            return self._generate_simple_html_artifact(pipeline_metrics, output_file)

    def _generate_markdown_artifact(
        self, pipeline_metrics: PipelineMetrics, collection: ReportCollection
    ) -> Path:
        """Generate Markdown report artifact."""
        output_file = self.output_dir / f"{collection.collection_id}_summary.md"

        markdown_content = self._create_markdown_content(pipeline_metrics)

        with open(output_file, "w") as f:
            f.write(markdown_content)

        return output_file

    def _generate_executive_artifact(
        self, pipeline_metrics: PipelineMetrics, collection: ReportCollection
    ) -> Path:
        """Generate executive summary artifact."""
        output_file = self.output_dir / f"{collection.collection_id}_executive.json"

        executive_summary = self._create_executive_summary(pipeline_metrics)

        with open(output_file, "w") as f:
            json.dump(executive_summary.model_dump(), f, indent=2, default=str)

        return output_file

    def _create_markdown_content(self, pipeline_metrics: PipelineMetrics) -> str:
        """Create Markdown content for the report."""
        content = f"""# Pipeline Statistical Report

**Run ID:** `{pipeline_metrics.run_id}`
**Generated:** {pipeline_metrics.timestamp.isoformat()}
**Environment:** {pipeline_metrics.environment}

## Overall Statistics

| Metric | Value |
|--------|-------|
| Total Records Processed | {pipeline_metrics.total_records_processed:,} |
| Overall Success Rate | {pipeline_metrics.overall_success_rate:.1%} |
| Total Duration | {pipeline_metrics.duration.total_seconds():.2f}s |
| Average Throughput | {pipeline_metrics.performance_metrics.records_per_second:.0f} records/sec |
| Peak Memory Usage | {pipeline_metrics.performance_metrics.peak_memory_mb:.1f} MB |

"""

        # Add module summaries
        if pipeline_metrics.module_metrics:
            content += "## Module Reports\n\n"
            for module_name, module in pipeline_metrics.module_metrics.items():
                content += f"### {module_name.upper()}\n\n"
                content += f"- **Records:** {module.records_processed:,} / {module.records_in:,}\n"
                content += f"- **Success Rate:** {module.success_rate:.1%}\n"
                content += f"- **Duration:** {module.execution_time.total_seconds():.2f}s\n"
                content += (
                    f"- **Throughput:** {module.throughput_records_per_second:.0f} records/sec\n"
                )

                if module.enrichment_coverage is not None:
                    content += f"- **Enrichment Coverage:** {module.enrichment_coverage:.1%}\n"

                content += "\n"

        return content

    def _create_executive_summary(self, pipeline_metrics: PipelineMetrics) -> ExecutiveSummary:
        """Create executive summary from pipeline metrics."""
        # Calculate high-level metrics
        total_funding = 0.0  # Would need to be calculated from actual data
        companies_tracked = 0  # Would need to be calculated from actual data
        patents_linked = 0  # Would need to be calculated from actual data

        # Extract from ecosystem metrics if available
        if pipeline_metrics.ecosystem_metrics:
            total_funding = pipeline_metrics.ecosystem_metrics.get("total_funding_analyzed", 0.0)
            companies_tracked = pipeline_metrics.ecosystem_metrics.get("companies_tracked", 0)
            patents_linked = pipeline_metrics.ecosystem_metrics.get("patents_linked", 0)

        return ExecutiveSummary(
            summary_id=f"{pipeline_metrics.run_id}_executive",
            run_id=pipeline_metrics.run_id,
            generated_at=datetime.now(),
            total_funding_analyzed=total_funding,
            companies_tracked=companies_tracked,
            patents_linked=patents_linked,
            technology_areas_covered=len(pipeline_metrics.quality_scores),
            kpis={
                "overall_success_rate": pipeline_metrics.overall_success_rate,
                "processing_throughput": pipeline_metrics.performance_metrics.records_per_second,
                "data_quality_score": sum(pipeline_metrics.quality_scores.values())
                / len(pipeline_metrics.quality_scores)
                if pipeline_metrics.quality_scores
                else 0.0,
            },
        )

    def _generate_plotly_html(self, pipeline_metrics: PipelineMetrics, output_file: Path) -> Path:
        """Generate HTML report with Plotly visualizations."""
        # Create dashboard with multiple sections
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "Module Success Rates",
                "Processing Throughput",
                "Memory Usage",
                "Records Processed by Module",
            ),
            specs=[
                [{"type": "bar"}, {"type": "bar"}],
                [{"type": "scatter"}, {"type": "pie"}],
            ],
        )

        # Module success rates
        if pipeline_metrics.module_metrics:
            modules = list(pipeline_metrics.module_metrics.keys())
            success_rates = [m.success_rate * 100 for m in pipeline_metrics.module_metrics.values()]

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
            throughputs = [
                m.throughput_records_per_second for m in pipeline_metrics.module_metrics.values()
            ]
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
            records = [m.records_processed for m in pipeline_metrics.module_metrics.values()]
            fig.add_trace(
                go.Pie(
                    labels=modules,
                    values=records,
                    name="Records Processed",
                ),
                row=2,
                col=2,
            )

        # Memory usage over time (placeholder)
        fig.add_trace(
            go.Scatter(
                x=[0, pipeline_metrics.duration.total_seconds()],
                y=[0, pipeline_metrics.performance_metrics.peak_memory_mb],
                mode="lines+markers",
                name="Memory Usage",
                line=dict(color="red"),
            ),
            row=2,
            col=1,
        )

        # Update layout
        fig.update_layout(
            title=f"Pipeline Statistical Report - {pipeline_metrics.run_id}",
            height=900,
            showlegend=True,
        )

        fig.write_html(output_file)
        return output_file

    def _generate_simple_html_artifact(
        self, pipeline_metrics: PipelineMetrics, output_file: Path
    ) -> Path:
        """Generate simple HTML report when Plotly is unavailable."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Pipeline Report - {pipeline_metrics.run_id}</title>
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
            <p><strong>Run ID:</strong> {pipeline_metrics.run_id}</p>
            <p><strong>Generated:</strong> {pipeline_metrics.timestamp.isoformat()}</p>

            <h2>Overall Statistics</h2>
            <p class="metric">Total Records: {pipeline_metrics.total_records_processed:,}</p>
            <p class="metric">Success Rate: {pipeline_metrics.overall_success_rate:.1%}</p>
            <p class="metric">Duration: {pipeline_metrics.duration.total_seconds():.2f}s</p>

            <h2>Module Reports</h2>
            <table>
                <tr>
                    <th>Module</th>
                    <th>Records Processed</th>
                    <th>Success Rate</th>
                    <th>Duration (s)</th>
                </tr>
        """

        for module_name, module in pipeline_metrics.module_metrics.items():
            html += f"""
                <tr>
                    <td>{module_name}</td>
                    <td>{module.records_processed:,} / {module.records_in:,}</td>
                    <td>{module.success_rate:.1%}</td>
                    <td>{module.execution_time.total_seconds():.2f}</td>
                </tr>
            """

        html += """
            </table>
        </body>
        </html>
        """

        with open(output_file, "w") as f:
            f.write(html)

        return output_file

    def _handle_ci_integration(self, collection: ReportCollection) -> None:
        """Handle CI/CD integration tasks.

        Args:
            collection: Report collection to integrate with CI/CD
        """
        if not self.ci_context:
            return

        logger.info("Handling CI/CD integration for statistical reports")

        # Generate PR comment if in PR context
        if self.ci_context.get("is_pr") and self.config.get("ci", {}).get("post_pr_comments", True):
            self._generate_pr_comment(collection)

        # Mark artifacts as uploaded (actual upload would be handled by CI workflow)
        collection.artifacts_uploaded = True

        logger.info("CI/CD integration completed")

    def _generate_pr_comment(self, collection: ReportCollection) -> None:
        """Generate PR comment with statistical summary.

        Args:
            collection: Report collection to summarize
        """
        # Find markdown artifact
        markdown_artifact = collection.get_artifact_by_format(ReportFormat.MARKDOWN)
        if not markdown_artifact:
            logger.warning("No markdown artifact found for PR comment")
            return

        # Read markdown content
        with open(markdown_artifact.file_path, "r") as f:
            markdown_content = f.read()

        # Truncate if too long
        max_length = self.config.get("markdown", {}).get("max_length", 2000)
        if len(markdown_content) > max_length:
            markdown_content = markdown_content[:max_length] + "\n\n... (truncated)"

        # Add artifact links
        markdown_content += "\n\n## Report Artifacts\n\n"
        for artifact in collection.artifacts:
            markdown_content += (
                f"- [{artifact.format.value.upper()} Report]({artifact.file_path})\n"
            )

        collection.pr_comment_generated = True
        logger.info("PR comment content generated")
