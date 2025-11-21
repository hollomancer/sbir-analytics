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

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.models.quality import (
    ChangesSummary,
    DataHygieneMetrics,
    InsightRecommendation,
    ModuleReport,
    StatisticalReport,
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
from src.utils.monitoring import performance_monitor
from src.utils.reporting.formats.html_processor import HtmlReportProcessor
from src.utils.reporting.formats.json_processor import JsonReportProcessor
from src.utils.reporting.formats.markdown_processor import MarkdownProcessor


class StatisticalReporter:
    """Orchestrator for generating statistical reports across pipeline modules.

    Integrates with existing performance monitoring utilities and provides
    comprehensive reporting capabilities for pipeline runs.
    """

    def __init__(
        self,
        output_dir: Path | None = None,
        config: dict[str, Any] | None = None,
        metrics_collector: MetricsCollector | None = None,
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

        # Initialize report processors
        self.processors = {
            ReportFormat.JSON: JsonReportProcessor(ReportFormat.JSON),
            ReportFormat.HTML: HtmlReportProcessor(ReportFormat.HTML),
            ReportFormat.MARKDOWN: MarkdownProcessor(ReportFormat.MARKDOWN),
        }

        # CI/CD context detection
        self.ci_context = self._detect_ci_context()

        logger.info(f"Statistical reporter initialized with output dir: {self.output_dir}")
        if self.ci_context:
            logger.info(f"CI/CD context detected: {self.ci_context.get('provider', 'unknown')}")

    def _detect_ci_context(self) -> dict[str, Any] | None:
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

    def generate_reports(self, run_context: dict[str, Any]) -> ReportCollection:
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
        metrics_data: dict[str, Any],
        data_hygiene: DataHygieneMetrics | None = None,
        changes_summary: ChangesSummary | None = None,
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
        if isinstance(start_time, int | float):
            start_time = datetime.fromtimestamp(start_time)
        if isinstance(end_time, int | float):
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
            run_id=run_id,
            data_hygiene=data_hygiene,
            changes_summary=changes_summary,
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

    def _collect_pipeline_metrics(
        self, run_id: str, run_context: dict[str, Any]
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
        if isinstance(start_time, int | float):
            start_time = datetime.fromtimestamp(start_time)
        if isinstance(end_time, int | float):
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
            pipeline_name=run_context.get("pipeline_name", "sbir-analytics"),
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
    ) -> list[ReportArtifact]:
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
    ) -> ReportArtifact | None:
        """Generate a single report artifact in the specified format.

        Args:
            pipeline_metrics: Pipeline metrics to report on
            format: Report format to generate
            collection: Report collection context

        Returns:
            ReportArtifact if successful, None otherwise
        """
        try:
            if format == ReportFormat.EXECUTIVE:
                # Handle executive summary separately as it doesn't have a processor yet
                file_path = self._generate_executive_artifact(pipeline_metrics, collection)
                file_size = file_path.stat().st_size if file_path.exists() else 0

                return ReportArtifact(
                    format=format,
                    file_path=file_path,
                    file_size_bytes=file_size,
                    generated_at=datetime.now(),
                    generation_duration_seconds=0.0,  # Not tracked for now
                    contains_interactive_elements=False,
                    contains_visualizations=True,
                )

            processor = self.processors.get(format)
            if not processor:
                logger.warning(f"No processor found for format: {format}")
                return None

            return processor.generate(
                pipeline_metrics=pipeline_metrics,
                output_dir=self.output_dir,
            )

        except Exception as e:
            logger.error(f"Failed to generate {format.value} report: {e}")
            return None

    def _generate_executive_artifact(
        self, pipeline_metrics: PipelineMetrics, collection: ReportCollection
    ) -> Path:
        """Generate executive summary artifact."""
        output_file = self.output_dir / f"{collection.collection_id}_executive.json"

        executive_summary = self._create_executive_summary(pipeline_metrics)

        with open(output_file, "w") as f:
            json.dump(executive_summary.model_dump(), f, indent=2, default=str)

        return output_file

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
        with open(markdown_artifact.file_path) as f:
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
