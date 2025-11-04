"""Report format processors for statistical reporting.

This package contains pluggable processors for generating reports in different
formats (HTML, JSON, Markdown) from PipelineMetrics data.
"""

# Register processors
from src.models.statistical_reports import ReportFormat

from .base import BaseReportProcessor, ReportProcessorRegistry, registry
from .html_processor import HtmlReportProcessor
from .json_processor import JsonReportProcessor
from .markdown_processor import MarkdownProcessor


registry.register(ReportFormat.HTML, HtmlReportProcessor)
registry.register(ReportFormat.JSON, JsonReportProcessor)
registry.register(ReportFormat.MARKDOWN, MarkdownProcessor)

__all__ = [
    "BaseReportProcessor",
    "ReportProcessorRegistry",
    "registry",
    "HtmlReportProcessor",
    "JsonReportProcessor",
    "MarkdownProcessor",
]
