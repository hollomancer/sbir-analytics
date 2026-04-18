"""Base classes and interfaces for report format processors.

This module provides the foundation for pluggable report processors that can
generate statistical reports in different formats (HTML, JSON, Markdown, etc.).
"""

import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from sbir_etl.models.statistical_reports import PipelineMetrics, ReportArtifact, ReportFormat


class BaseReportProcessor(ABC):
    """Base class for report format processors.

    Processors are responsible for generating reports in specific formats
    from PipelineMetrics data. They handle file creation, content generation,
    and metadata collection.
    """

    def __init__(self, format_type: ReportFormat):
        """Initialize the report processor.

        Args:
            format_type: The report format this processor generates
        """
        self.format_type = format_type

    @abstractmethod
    def generate(
        self, pipeline_metrics: PipelineMetrics, output_dir: Path, **kwargs: Any
    ) -> ReportArtifact:
        """Generate a report artifact.

        Args:
            pipeline_metrics: Pipeline statistics and metrics to report on
            output_dir: Directory where the report file should be written
            **kwargs: Additional format-specific options

        Returns:
            ReportArtifact describing the generated report file
        """
        pass

    def _create_output_path(self, pipeline_metrics: PipelineMetrics, output_dir: Path) -> Path:
        """Create a standardized output path for the report.

        Args:
            pipeline_metrics: Pipeline metrics containing run_id
            output_dir: Base output directory

        Returns:
            Path for the report file
        """
        # Map format types to file extensions
        extension_map = {
            "markdown": "md",
            "html": "html",
            "json": "json",
        }
        extension = extension_map.get(self.format_type.value, self.format_type.value)
        filename = f"report.{extension}"
        return output_dir / pipeline_metrics.run_id / filename

    def _ensure_output_directory(self, file_path: Path) -> None:
        """Ensure the output directory exists.

        Args:
            file_path: Path to the file that will be created
        """
        file_path.parent.mkdir(parents=True, exist_ok=True)

    def _write_file_with_metadata(self, content: str, file_path: Path) -> tuple[int, float]:
        """Write content to file and return metadata.

        Args:
            content: File content to write
            file_path: Path where to write the file

        Returns:
            Tuple of (file_size_bytes, write_duration_seconds)
        """
        start_time = time.time()

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        end_time = time.time()
        file_size = file_path.stat().st_size

        return file_size, end_time - start_time

    def _get_interactive_flag(self) -> bool:
        """Get whether this format supports interactive elements.

        Returns:
            True if the format supports interactive elements
        """
        # Override in subclasses that support interactivity
        return False

    def _get_visualization_flag(self) -> bool:
        """Get whether this format contains visualizations.

        Returns:
            True if the format contains charts/graphs
        """
        # Override in subclasses that include visualizations
        return False


