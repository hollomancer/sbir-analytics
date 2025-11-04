"""HTML report processor with interactive visualizations.

This processor generates comprehensive HTML reports with Plotly charts
for statistical pipeline data. It supports both interactive visualizations
and fallback to simple HTML when Plotly is unavailable.
"""

import time
from pathlib import Path
from typing import Any

from src.models.statistical_reports import PipelineMetrics, ReportArtifact, ReportFormat
from src.utils.reporting.formats.base import BaseReportProcessor


# Optional Plotly imports
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


class HtmlReportProcessor(BaseReportProcessor):
    """HTML report processor with Plotly visualizations.

    Generates comprehensive HTML reports with interactive charts when Plotly
    is available, falling back to simple HTML tables when not.
    """

    def __init__(self, format_type: ReportFormat):
        """Initialize the HTML processor."""
        super().__init__(format_type)

    def generate(
        self, pipeline_metrics: PipelineMetrics, output_dir: Path, **kwargs: Any
    ) -> ReportArtifact:
        """Generate HTML report with visualizations.

        Args:
            pipeline_metrics: Pipeline statistics and metrics
            output_dir: Directory where the report file should be written
            **kwargs: Additional options (currently unused)

        Returns:
            ReportArtifact describing the generated HTML report
        """
        start_time = time.time()
        output_path = self._create_output_path(pipeline_metrics, output_dir)
        self._ensure_output_directory(output_path)

        # Generate HTML content
        if PLOTLY_AVAILABLE:
            html_content = self._generate_plotly_html(pipeline_metrics)
        else:
            html_content = self._generate_simple_html(pipeline_metrics)

        # Write file and collect metadata
        file_size, write_duration = self._write_file_with_metadata(html_content, output_path)
        generation_duration = time.time() - start_time

        # Create artifact
        artifact = ReportArtifact(
            format=self.format_type,
            file_path=output_path,
            file_size_bytes=file_size,
            generated_at=pipeline_metrics.timestamp,
            generation_duration_seconds=generation_duration,
            contains_interactive_elements=PLOTLY_AVAILABLE,
            contains_visualizations=True,
            is_public_safe=True,
            requires_authentication=False,
        )

        return artifact

    def _generate_plotly_html(self, pipeline_metrics: PipelineMetrics) -> str:
        """Generate HTML with interactive Plotly visualizations."""
        # Create dashboard with multiple sections
        fig = make_subplots(
            rows=2,
            cols=2,
            subplot_titles=(
                "Module Success Rates",
                "Processing Throughput",
                "Memory Usage Over Time",
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
                    hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
                ),
                row=1,
                col=1,
            )

            # Processing throughput
            throughputs = [
                m.throughput_records_per_second for m in pipeline_metrics.module_metrics.values()
            ]
            fig.add_trace(
                go.Bar(
                    x=modules,
                    y=throughputs,
                    name="Records/sec",
                    marker_color="blue",
                    hovertemplate="%{x}: %{y:.1f} records/sec<extra></extra>",
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
                    hovertemplate="%{label}: %{value:,} records<extra></extra>",
                ),
                row=2,
                col=2,
            )

        # Memory usage over time (simplified)
        if pipeline_metrics.performance_metrics:
            duration_seconds = pipeline_metrics.duration.total_seconds()
            peak_memory = pipeline_metrics.performance_metrics.peak_memory_mb

            fig.add_trace(
                go.Scatter(
                    x=[0, duration_seconds],
                    y=[0, peak_memory],
                    mode="lines+markers",
                    name="Memory Usage (MB)",
                    line={"color": "red"},
                    hovertemplate="Time: %{x:.1f}s<br>Memory: %{y:.1f} MB<extra></extra>",
                ),
                row=2,
                col=1,
            )

        # Update layout
        fig.update_layout(
            title={
                "text": f"Pipeline Statistical Report - {pipeline_metrics.run_id}",
                "x": 0.5,
                "xanchor": "center",
                "font": {"size": 20},
            },
            height=900,
            showlegend=True,
            template="plotly_white",
        )

        # Generate HTML with Plotly
        html_content = fig.to_html(
            full_html=True,
            include_plotlyjs=True,
            include_mathjax=False,
            config={
                "displayModeBar": True,
                "displaylogo": False,
                "modeBarButtonsToRemove": ["pan2d", "lasso2d"],
            },
        )

        # Add custom styling and metadata section
        html_content = self._enhance_plotly_html(html_content, pipeline_metrics)

        return html_content

    def _generate_simple_html(self, pipeline_metrics: PipelineMetrics) -> str:
        """Generate simple HTML report when Plotly is unavailable."""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Pipeline Report - {pipeline_metrics.run_id}</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                    color: #333;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background: white;
                    padding: 30px;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                h1, h2, h3 {{
                    color: #2c3e50;
                    margin-top: 30px;
                    margin-bottom: 15px;
                }}
                .metric-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 20px;
                    margin: 20px 0;
                }}
                .metric-card {{
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 6px;
                    border-left: 4px solid #3498db;
                }}
                .metric-value {{
                    font-size: 2em;
                    font-weight: bold;
                    color: #3498db;
                    margin: 5px 0;
                }}
                .metric-label {{
                    font-size: 0.9em;
                    color: #7f8c8d;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 20px 0;
                    background: white;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 12px;
                    text-align: left;
                }}
                th {{
                    background-color: #34495e;
                    color: white;
                    font-weight: 600;
                }}
                tr:nth-child(even) {{
                    background-color: #f8f9fa;
                }}
                tr:hover {{
                    background-color: #e8f4fd;
                }}
                .status-good {{ color: #27ae60; font-weight: bold; }}
                .status-warning {{ color: #f39c12; font-weight: bold; }}
                .status-error {{ color: #e74c3c; font-weight: bold; }}
                .note {{
                    background: #fff3cd;
                    border: 1px solid #ffeaa7;
                    border-radius: 4px;
                    padding: 15px;
                    margin: 20px 0;
                    color: #856404;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Pipeline Statistical Report</h1>
                <p><strong>Run ID:</strong> {pipeline_metrics.run_id}</p>
                <p><strong>Generated:</strong> {pipeline_metrics.timestamp.isoformat()}</p>
                <p><strong>Duration:</strong> {pipeline_metrics.duration.total_seconds():.2f} seconds</p>

                <h2>Overall Statistics</h2>
                <div class="metric-grid">
                    <div class="metric-card">
                        <div class="metric-label">Total Records Processed</div>
                        <div class="metric-value">{pipeline_metrics.total_records_processed:,}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Overall Success Rate</div>
                        <div class="metric-value">{pipeline_metrics.overall_success_rate:.1%}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Peak Memory Usage</div>
                        <div class="metric-value">{pipeline_metrics.performance_metrics.peak_memory_mb:.1f} MB</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-label">Processing Throughput</div>
                        <div class="metric-value">{pipeline_metrics.performance_metrics.records_per_second:.1f} rec/sec</div>
                    </div>
                </div>

                <h2>Module Performance</h2>
                <table>
                    <tr>
                        <th>Module</th>
                        <th>Stage</th>
                        <th>Records Processed</th>
                        <th>Success Rate</th>
                        <th>Duration</th>
                        <th>Throughput</th>
                    </tr>
        """

        for module_name, module in pipeline_metrics.module_metrics.items():
            success_class = (
                "status-good"
                if module.success_rate >= 0.95
                else "status-warning"
                if module.success_rate >= 0.85
                else "status-error"
            )
            html += f"""
                    <tr>
                        <td>{module_name}</td>
                        <td>{module.stage}</td>
                        <td>{module.records_processed:,} / {module.records_in:,}</td>
                        <td class="{success_class}">{module.success_rate:.1%}</td>
                        <td>{module.execution_time.total_seconds():.2f}s</td>
                        <td>{module.throughput_records_per_second:.1f} rec/sec</td>
                    </tr>
                """

        html += """
                </table>

                <div class="note">
                    <strong>Note:</strong> Interactive visualizations are not available because Plotly is not installed.
                    Install Plotly to enable interactive charts: <code>pip install plotly</code>
                </div>
            </div>
        </body>
        </html>
        """

        return html

    def _enhance_plotly_html(self, plotly_html: str, pipeline_metrics: PipelineMetrics) -> str:
        """Enhance Plotly HTML with additional metadata and styling."""
        # Extract the body content from Plotly HTML
        body_start = plotly_html.find("<body>")
        body_end = plotly_html.find("</body>")

        if body_start == -1 or body_end == -1:
            return plotly_html

        # Get the existing body content
        body_content = plotly_html[body_start + 6 : body_end]

        # Create enhanced body with metadata section
        enhanced_body = f"""
            <div style="max-width: 1200px; margin: 0 auto; padding: 20px;">
                <div style="background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                    <h1 style="color: #2c3e50; margin-bottom: 10px;">Pipeline Statistical Report</h1>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px;">
                        <div><strong>Run ID:</strong> {pipeline_metrics.run_id}</div>
                        <div><strong>Generated:</strong> {pipeline_metrics.timestamp.isoformat()}</div>
                        <div><strong>Total Duration:</strong> {pipeline_metrics.duration.total_seconds():.2f}s</div>
                        <div><strong>Records Processed:</strong> {pipeline_metrics.total_records_processed:,}</div>
                    </div>
                </div>

                {body_content}
            </div>
        """

        # Replace the body content
        enhanced_html = plotly_html[: body_start + 6] + enhanced_body + plotly_html[body_end:]

        return enhanced_html

    def _get_interactive_flag(self) -> bool:
        """HTML reports are interactive when Plotly is available."""
        return PLOTLY_AVAILABLE

    def _get_visualization_flag(self) -> bool:
        """HTML reports always contain visualizations."""
        return True
