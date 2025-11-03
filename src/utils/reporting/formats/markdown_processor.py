"""Markdown report processor for concise PR-friendly summaries.

This processor generates markdown reports with key metrics highlights,
quality indicators, and artifact links suitable for PR comments and documentation.
"""

import time
from pathlib import Path
from typing import Any

from src.models.statistical_reports import PipelineMetrics, ReportArtifact, ReportFormat
from src.utils.reporting.formats.base import BaseReportProcessor


class MarkdownProcessor(BaseReportProcessor):
    """Markdown report processor for concise PR-friendly summaries.

    Generates markdown reports with key metrics, quality indicators, and
    links to detailed reports. Designed to fit within PR comment limits.
    """

    def __init__(self, format_type: ReportFormat, max_length: int = 2000):
        """Initialize the Markdown processor.

        Args:
            format_type: The report format (should be MARKDOWN)
            max_length: Maximum length of markdown content (default 2000)
        """
        super().__init__(format_type)
        self.max_length = max_length

    def generate(
        self,
        pipeline_metrics: PipelineMetrics,
        output_dir: Path,
        max_length: int | None = None,
        include_links: bool = True,
        **kwargs: Any,
    ) -> ReportArtifact:
        """Generate concise markdown report summary.

        Args:
            pipeline_metrics: Pipeline statistics and metrics
            output_dir: Directory where the report file should be written
            max_length: Override default max length for content
            include_links: Whether to include links to other reports
            **kwargs: Additional options (currently unused)

        Returns:
            ReportArtifact describing the generated markdown report
        """
        start_time = time.time()
        output_path = self._create_output_path(pipeline_metrics, output_dir)
        self._ensure_output_directory(output_path)

        # Use provided max_length or instance default
        content_max_length = max_length if max_length is not None else self.max_length

        # Generate markdown content
        markdown_content = self._generate_markdown_content(
            pipeline_metrics, include_links=include_links
        )

        # Truncate if too long
        if len(markdown_content) > content_max_length:
            markdown_content = self._truncate_markdown(markdown_content, content_max_length)

        # Write file and collect metadata
        file_size, write_duration = self._write_file_with_metadata(markdown_content, output_path)
        generation_duration = time.time() - start_time

        # Create artifact
        artifact = ReportArtifact(
            format=self.format_type,
            file_path=output_path,
            file_size_bytes=file_size,
            generated_at=pipeline_metrics.timestamp,
            generation_duration_seconds=generation_duration,
            contains_interactive_elements=False,
            contains_visualizations=False,
            is_public_safe=True,
            requires_authentication=False,
        )

        return artifact

    def _generate_markdown_content(
        self, pipeline_metrics: PipelineMetrics, include_links: bool = True
    ) -> str:
        """Generate markdown content with key metrics and insights.

        Args:
            pipeline_metrics: Pipeline statistics and metrics
            include_links: Whether to include artifact links

        Returns:
            Markdown content string
        """
        lines = []

        # Header
        lines.append("# Pipeline Statistical Report")
        lines.append("")
        lines.append(f"**Run ID:** {pipeline_metrics.run_id}")
        lines.append(f"**Generated:** {pipeline_metrics.timestamp.isoformat()}")
        lines.append(f"**Duration:** {pipeline_metrics.duration.total_seconds():.2f}s")
        lines.append("")

        # Overall metrics
        lines.append("## 📊 Overall Metrics")
        lines.append("")
        lines.append(f"- **Total Records Processed:** {pipeline_metrics.total_records_processed:,}")
        lines.append(f"- **Overall Success Rate:** {pipeline_metrics.overall_success_rate:.1%}")
        lines.append(
            f"- **Peak Memory Usage:** {pipeline_metrics.performance_metrics.peak_memory_mb:.1f} MB"
        )
        lines.append(
            f"- **Processing Throughput:** {pipeline_metrics.performance_metrics.records_per_second:.1f} records/sec"
        )
        lines.append("")

        # Module performance summary
        if pipeline_metrics.module_metrics:
            lines.append("## 🔧 Module Performance")
            lines.append("")
            lines.append("| Module | Records | Success Rate | Duration | Throughput |")
            lines.append("|--------|---------|--------------|----------|------------|")

            for module_name, module in sorted(pipeline_metrics.module_metrics.items()):
                status_emoji = self._get_status_emoji(module.success_rate)
                lines.append(
                    f"| {module_name} | {module.records_processed:,}/{module.records_in:,} | "
                    f"{status_emoji} {module.success_rate:.1%} | "
                    f"{module.execution_time.total_seconds():.2f}s | "
                    f"{module.throughput_records_per_second:.1f} rec/sec |"
                )
            lines.append("")

        # Quality indicators
        quality_issues = self._identify_quality_issues(pipeline_metrics)
        if quality_issues:
            lines.append("## ⚠️ Quality Indicators")
            lines.append("")
            for issue in quality_issues:
                lines.append(f"- {issue}")
            lines.append("")

        # Key insights (placeholder for future enhancement)
        insights = self._generate_key_insights(pipeline_metrics)
        if insights:
            lines.append("## 💡 Key Insights")
            lines.append("")
            for insight in insights:
                lines.append(f"- {insight}")
            lines.append("")

        # Artifact links
        if include_links:
            lines.append("## 📁 Report Artifacts")
            lines.append("")
            run_dir = f"reports/statistical/{pipeline_metrics.run_id}/"
            lines.append(
                f"- **[📊 HTML Report]({run_dir}report.html)** - Interactive dashboard with charts"
            )
            lines.append(
                f"- **[📋 JSON Report]({run_dir}report.json)** - Machine-readable complete data"
            )
            lines.append(f"- **[📝 Markdown Summary]({run_dir}report.md)** - This summary")
            lines.append("")

        # Footer
        lines.append("---")
        lines.append("*Generated by SBIR-ETL Statistical Reporter*")

        return "\n".join(lines)

    def _get_status_emoji(self, success_rate: float) -> str:
        """Get status emoji based on success rate.

        Args:
            success_rate: Success rate between 0.0 and 1.0

        Returns:
            Status emoji string
        """
        if success_rate >= 0.95:
            return "✅"
        elif success_rate >= 0.85:
            return "⚠️"
        else:
            return "❌"

    def _identify_quality_issues(self, pipeline_metrics: PipelineMetrics) -> list[str]:
        """Identify potential quality issues from pipeline metrics.

        Args:
            pipeline_metrics: Pipeline statistics and metrics

        Returns:
            List of quality issue descriptions
        """
        issues = []

        # Check overall success rate
        if pipeline_metrics.overall_success_rate < 0.90:
            issues.append(
                f"Overall success rate ({pipeline_metrics.overall_success_rate:.1%}) "
                "is below 90% threshold"
            )

        # Check for failed modules
        failed_modules = []
        for module_name, module in pipeline_metrics.module_metrics.items():
            if module.success_rate < 0.80:
                failed_modules.append(f"{module_name} ({module.success_rate:.1%})")

        if failed_modules:
            issues.append(f"Low success rate modules: {', '.join(failed_modules)}")

        # Check memory usage (rough heuristic)
        if pipeline_metrics.performance_metrics.peak_memory_mb > 1000:  # 1GB
            issues.append(
                f"High memory usage detected: "
                f"{pipeline_metrics.performance_metrics.peak_memory_mb:.1f} MB"
            )

        return issues

    def _generate_key_insights(self, pipeline_metrics: PipelineMetrics) -> list[str]:
        """Generate key insights from pipeline metrics.

        Args:
            pipeline_metrics: Pipeline statistics and metrics

        Returns:
            List of insight descriptions
        """
        insights = []

        # Performance insights
        if pipeline_metrics.performance_metrics.records_per_second > 1000:
            insights.append("High throughput achieved - excellent performance!")

        # Module insights
        if pipeline_metrics.module_metrics:
            best_performer = max(
                pipeline_metrics.module_metrics.items(), key=lambda x: x[1].success_rate
            )
            if best_performer[1].success_rate >= 0.95:
                insights.append(f"Excellent performance from {best_performer[0]} module")

            slowest_module = max(
                pipeline_metrics.module_metrics.items(),
                key=lambda x: x[1].execution_time.total_seconds(),
            )
            if slowest_module[1].execution_time.total_seconds() > 60:  # 1 minute
                insights.append(f"Consider optimizing {slowest_module[0]} module performance")

        return insights

    def _truncate_markdown(self, content: str, max_length: int) -> str:
        """Truncate markdown content while preserving structure.

        Args:
            content: Markdown content to truncate
            max_length: Maximum length allowed

        Returns:
            Truncated markdown content
        """
        if len(content) <= max_length:
            return content

        # Find a good truncation point (end of a section)
        lines = content.split("\n")
        truncated_lines = []
        current_length = 0

        for line in lines:
            if current_length + len(line) + 1 > max_length - 50:  # Leave room for truncation note
                break
            truncated_lines.append(line)
            current_length += len(line) + 1

        # Add truncation indicator
        truncated_lines.append("")
        truncated_lines.append("*... (truncated due to length)*")

        return "\n".join(truncated_lines)

    def _get_interactive_flag(self) -> bool:
        """Markdown reports are not interactive."""
        return False

    def _get_visualization_flag(self) -> bool:
        """Markdown reports do not contain visualizations."""
        return False
