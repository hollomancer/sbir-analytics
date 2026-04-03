"""Report format processors for statistical reporting.

This package contains pluggable processors for generating reports in different
formats (HTML, JSON, Markdown) from PipelineMetrics data.
"""

from .base import BaseReportProcessor
from .html_processor import HtmlReportProcessor
from .json_processor import JsonReportProcessor
from .markdown_processor import MarkdownProcessor

__all__ = [
    "BaseReportProcessor",
    "HtmlReportProcessor",
    "JsonReportProcessor",
    "MarkdownProcessor",
]
