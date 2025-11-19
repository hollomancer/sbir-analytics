"""Unit tests for reporting format processor modules.

Tests for base processor and all format-specific implementations:
- BaseReportProcessor: Common utilities and abstract methods
- ReportProcessorRegistry: Processor registration and lookup
- JsonReportProcessor: JSON report generation
- HtmlReportProcessor: HTML report with visualizations
- MarkdownProcessor: Markdown summaries
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest


pytestmark = pytest.mark.fast

import pytest

from src.models.statistical_reports import (
    ModuleMetrics,
    PerformanceMetrics,
    PipelineMetrics,
    ReportArtifact,
    ReportFormat,
)
from src.utils.reporting.formats.base import BaseReportProcessor, ReportProcessorRegistry
from src.utils.reporting.formats.html_processor import HtmlReportProcessor
from src.utils.reporting.formats.json_processor import JsonReportProcessor
from src.utils.reporting.formats.markdown_processor import MarkdownProcessor


pytestmark = pytest.mark.fast


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_pipeline_metrics() -> PipelineMetrics:
    """Create sample pipeline metrics for testing."""
    start_time = datetime(2025, 1, 1, 10, 0, 0)
    end_time = datetime(2025, 1, 1, 10, 30, 0)

    performance = PerformanceMetrics(
        start_time=start_time,
        end_time=end_time,
        duration=timedelta(minutes=30),
        peak_memory_mb=512.5,
        average_memory_mb=350.2,
        cpu_percent_average=75.3,
        records_per_second=100.5,
    )

    module1 = ModuleMetrics(
        module_name="extraction",
        stage="extract",
        records_in=1000,
        records_out=950,
        records_processed=950,
        records_failed=50,
        success_rate=0.95,
        execution_time=timedelta(minutes=10),
        throughput_records_per_second=95.0,
        start_time=start_time,
        end_time=start_time + timedelta(minutes=10),
    )

    module2 = ModuleMetrics(
        module_name="enrichment",
        stage="enrich",
        records_in=950,
        records_out=920,
        records_processed=920,
        records_failed=30,
        success_rate=0.97,
        execution_time=timedelta(minutes=15),
        throughput_records_per_second=61.3,
        start_time=start_time + timedelta(minutes=10),
        end_time=start_time + timedelta(minutes=25),
    )

    return PipelineMetrics(
        run_id="test_run_123",
        timestamp=start_time,
        duration=timedelta(minutes=30),
        total_records_processed=1870,
        overall_success_rate=0.96,
        performance_metrics=performance,
        module_metrics={"extraction": module1, "enrichment": module2},
        errors=[],
        warnings=[],
    )


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Create temporary output directory."""
    output_dir = tmp_path / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# =============================================================================
# Base Report Processor Tests
# =============================================================================


class ConcreteProcessor(BaseReportProcessor):
    """Concrete implementation for testing base processor."""

    def generate(
        self, pipeline_metrics: PipelineMetrics, output_dir: Path, **kwargs: Any
    ) -> ReportArtifact:
        """Implement abstract generate method."""
        output_path = self._create_output_path(pipeline_metrics, output_dir)
        self._ensure_output_directory(output_path)

        content = "Test report content"
        file_size, write_duration = self._write_file_with_metadata(content, output_path)

        return ReportArtifact(
            format=self.format_type,
            file_path=output_path,
            file_size_bytes=file_size,
            generated_at=pipeline_metrics.timestamp,
            generation_duration_seconds=1.0,
            contains_interactive_elements=False,
            contains_visualizations=False,
            is_public_safe=True,
            requires_authentication=False,
        )


class TestBaseReportProcessor:
    """Tests for the base BaseReportProcessor class."""

    def test_initialization(self):
        """Test processor initialization with format type."""
        processor = ConcreteProcessor(ReportFormat.JSON)

        assert processor.format_type == ReportFormat.JSON

    def test_create_output_path(self, sample_pipeline_metrics, temp_output_dir):
        """Test creating standardized output path."""
        processor = ConcreteProcessor(ReportFormat.JSON)

        output_path = processor._create_output_path(sample_pipeline_metrics, temp_output_dir)

        assert output_path.parent.name == "test_run_123"
        assert output_path.name == "report.json"
        assert temp_output_dir in output_path.parents

    def test_ensure_output_directory(self, tmp_path):
        """Test ensuring output directory exists."""
        processor = ConcreteProcessor(ReportFormat.JSON)
        file_path = tmp_path / "subdir" / "report.json"

        processor._ensure_output_directory(file_path)

        assert file_path.parent.exists()
        assert file_path.parent.is_dir()

    def test_write_file_with_metadata(self, tmp_path):
        """Test writing file and collecting metadata."""
        processor = ConcreteProcessor(ReportFormat.JSON)
        file_path = tmp_path / "test.txt"
        content = "Test content for file writing"

        file_size, write_duration = processor._write_file_with_metadata(content, file_path)

        assert file_path.exists()
        assert file_path.read_text() == content
        assert file_size == len(content.encode("utf-8"))
        assert write_duration >= 0

    def test_get_interactive_flag_default(self):
        """Test default interactive flag is False."""
        processor = ConcreteProcessor(ReportFormat.JSON)

        assert processor._get_interactive_flag() is False

    def test_get_visualization_flag_default(self):
        """Test default visualization flag is False."""
        processor = ConcreteProcessor(ReportFormat.JSON)

        assert processor._get_visualization_flag() is False

    def test_generate_creates_artifact(self, sample_pipeline_metrics, temp_output_dir):
        """Test generate method creates valid artifact."""
        processor = ConcreteProcessor(ReportFormat.JSON)

        artifact = processor.generate(sample_pipeline_metrics, temp_output_dir)

        assert isinstance(artifact, ReportArtifact)
        assert artifact.format == ReportFormat.JSON
        assert artifact.file_path.exists()
        assert artifact.file_size_bytes > 0


# =============================================================================
# Report Processor Registry Tests
# =============================================================================


class TestReportProcessorRegistry:
    """Tests for the ReportProcessorRegistry."""

    def test_initialization(self):
        """Test registry initialization."""
        registry = ReportProcessorRegistry()

        assert registry._processors == {}

    def test_register_processor(self):
        """Test registering a processor class."""
        registry = ReportProcessorRegistry()

        registry.register(ReportFormat.JSON, JsonReportProcessor)

        assert ReportFormat.JSON in registry._processors
        assert registry._processors[ReportFormat.JSON] == JsonReportProcessor

    def test_get_processor(self):
        """Test retrieving a processor class."""
        registry = ReportProcessorRegistry()
        registry.register(ReportFormat.JSON, JsonReportProcessor)

        processor_class = registry.get_processor(ReportFormat.JSON)

        assert processor_class == JsonReportProcessor

    def test_get_processor_not_registered(self):
        """Test retrieving unregistered processor returns None."""
        registry = ReportProcessorRegistry()

        processor_class = registry.get_processor(ReportFormat.JSON)

        assert processor_class is None

    def test_create_processor(self):
        """Test creating a processor instance."""
        registry = ReportProcessorRegistry()
        registry.register(ReportFormat.JSON, JsonReportProcessor)

        processor = registry.create_processor(ReportFormat.JSON)

        assert isinstance(processor, JsonReportProcessor)
        assert processor.format_type == ReportFormat.JSON

    def test_create_processor_not_registered(self):
        """Test creating processor for unregistered format returns None."""
        registry = ReportProcessorRegistry()

        processor = registry.create_processor(ReportFormat.JSON)

        assert processor is None

    def test_get_supported_formats(self):
        """Test getting list of supported formats."""
        registry = ReportProcessorRegistry()
        registry.register(ReportFormat.JSON, JsonReportProcessor)
        registry.register(ReportFormat.HTML, HtmlReportProcessor)

        formats = registry.get_supported_formats()

        assert ReportFormat.JSON in formats
        assert ReportFormat.HTML in formats
        assert len(formats) == 2


# =============================================================================
# JSON Report Processor Tests
# =============================================================================


class TestJsonReportProcessor:
    """Tests for the JSON report processor."""

    def test_initialization(self):
        """Test JSON processor initialization."""
        processor = JsonReportProcessor(ReportFormat.JSON)

        assert processor.format_type == ReportFormat.JSON

    def test_generate_creates_json_file(self, sample_pipeline_metrics, temp_output_dir):
        """Test JSON generation creates valid file."""
        processor = JsonReportProcessor(ReportFormat.JSON)

        artifact = processor.generate(sample_pipeline_metrics, temp_output_dir)

        assert artifact.file_path.exists()
        assert artifact.file_path.suffix == ".json"

    def test_generated_json_is_valid(self, sample_pipeline_metrics, temp_output_dir):
        """Test generated JSON is valid and parseable."""
        processor = JsonReportProcessor(ReportFormat.JSON)

        artifact = processor.generate(sample_pipeline_metrics, temp_output_dir)

        # Read and parse JSON
        json_data = json.loads(artifact.file_path.read_text())

        assert "run_id" in json_data
        assert json_data["run_id"] == "test_run_123"
        assert "timestamp" in json_data
        assert "total_records_processed" in json_data

    def test_serialize_pipeline_metrics(self, sample_pipeline_metrics):
        """Test serializing pipeline metrics to dictionary."""
        processor = JsonReportProcessor(ReportFormat.JSON)

        data = processor._serialize_pipeline_metrics(sample_pipeline_metrics)

        assert data["run_id"] == "test_run_123"
        assert "timestamp" in data
        assert "duration" in data
        assert "performance_metrics" in data
        assert "module_metrics" in data
        assert "_metadata" in data

    def test_serialize_handles_datetime(self, sample_pipeline_metrics):
        """Test datetime serialization in JSON."""
        processor = JsonReportProcessor(ReportFormat.JSON)

        data = processor._serialize_pipeline_metrics(sample_pipeline_metrics)

        # Timestamp should be ISO format string
        assert isinstance(data["timestamp"], str)
        assert "T" in data["timestamp"]  # ISO format indicator

    def test_serialize_handles_timedelta(self, sample_pipeline_metrics):
        """Test timedelta serialization in JSON."""
        processor = JsonReportProcessor(ReportFormat.JSON)

        data = processor._serialize_pipeline_metrics(sample_pipeline_metrics)

        # Duration should have both seconds and human readable
        assert "duration" in data
        assert "seconds" in data["duration"]
        assert "human_readable" in data["duration"]

    def test_json_serializer_handles_path(self):
        """Test custom JSON serializer handles Path objects."""
        processor = JsonReportProcessor(ReportFormat.JSON)
        path = Path("/test/path")

        result = processor._json_serializer(path)

        assert result == str(path)

    def test_json_serializer_handles_set(self):
        """Test custom JSON serializer handles set objects."""
        processor = JsonReportProcessor(ReportFormat.JSON)
        test_set = {1, 2, 3}

        result = processor._json_serializer(test_set)

        assert isinstance(result, list)
        assert set(result) == test_set

    def test_json_serializer_handles_bytes(self):
        """Test custom JSON serializer handles bytes objects."""
        processor = JsonReportProcessor(ReportFormat.JSON)
        test_bytes = b"test data"

        result = processor._json_serializer(test_bytes)

        assert result == "test data"

    def test_json_serializer_raises_for_unknown_type(self):
        """Test custom JSON serializer raises for unknown types."""
        processor = JsonReportProcessor(ReportFormat.JSON)

        # Create an object without __str__
        class UnserializableObject:
            def __init__(self):
                pass

            def __str__(self):
                raise NotImplementedError

        obj = UnserializableObject()

        from src.exceptions import ValidationError

        with pytest.raises(ValidationError):
            processor._json_serializer(obj)

    def test_validate_json_schema_basic(self, sample_pipeline_metrics):
        """Test basic JSON schema validation."""
        processor = JsonReportProcessor(ReportFormat.JSON)

        data = processor._serialize_pipeline_metrics(sample_pipeline_metrics)

        # Should not raise
        processor._validate_json_schema(data)

    def test_validate_json_schema_missing_field(self):
        """Test JSON schema validation with missing field."""
        processor = JsonReportProcessor(ReportFormat.JSON)

        from src.exceptions import ValidationError

        with pytest.raises(ValidationError):
            processor._validate_json_schema({"run_id": "test"})  # Missing required fields

    def test_generate_with_schema_validation(self, sample_pipeline_metrics, temp_output_dir):
        """Test generation with schema validation enabled."""
        processor = JsonReportProcessor(ReportFormat.JSON)

        artifact = processor.generate(
            sample_pipeline_metrics, temp_output_dir, validate_schema=True
        )

        assert artifact.file_path.exists()

    def test_interactive_and_visualization_flags(self):
        """Test JSON processor flags."""
        processor = JsonReportProcessor(ReportFormat.JSON)

        assert processor._get_interactive_flag() is False
        assert processor._get_visualization_flag() is False


# =============================================================================
# HTML Report Processor Tests
# =============================================================================


class TestHtmlReportProcessor:
    """Tests for the HTML report processor."""

    def test_initialization(self):
        """Test HTML processor initialization."""
        processor = HtmlReportProcessor(ReportFormat.HTML)

        assert processor.format_type == ReportFormat.HTML

    def test_generate_creates_html_file(self, sample_pipeline_metrics, temp_output_dir):
        """Test HTML generation creates valid file."""
        processor = HtmlReportProcessor(ReportFormat.HTML)

        artifact = processor.generate(sample_pipeline_metrics, temp_output_dir)

        assert artifact.file_path.exists()
        assert artifact.file_path.suffix == ".html"

    def test_generated_html_is_valid(self, sample_pipeline_metrics, temp_output_dir):
        """Test generated HTML has valid structure."""
        processor = HtmlReportProcessor(ReportFormat.HTML)

        artifact = processor.generate(sample_pipeline_metrics, temp_output_dir)

        html_content = artifact.file_path.read_text()

        assert "<!DOCTYPE html>" in html_content
        assert "<html>" in html_content
        assert "</html>" in html_content
        assert "test_run_123" in html_content

    def test_generate_simple_html(self, sample_pipeline_metrics):
        """Test generating simple HTML without Plotly."""
        processor = HtmlReportProcessor(ReportFormat.HTML)

        html = processor._generate_simple_html(sample_pipeline_metrics)

        assert "Pipeline Report" in html
        assert "test_run_123" in html
        assert "<table>" in html
        assert "extraction" in html
        assert "enrichment" in html

    def test_simple_html_includes_module_metrics(self, sample_pipeline_metrics):
        """Test simple HTML includes module performance table."""
        processor = HtmlReportProcessor(ReportFormat.HTML)

        html = processor._generate_simple_html(sample_pipeline_metrics)

        assert "Module Performance" in html
        assert "extraction" in html
        assert "enrichment" in html
        assert "95" in html or "0.95" in html  # Success rate

    def test_enhance_plotly_html(self, sample_pipeline_metrics):
        """Test enhancing Plotly HTML with metadata."""
        processor = HtmlReportProcessor(ReportFormat.HTML)

        base_html = "<html><body><div>Chart</div></body></html>"

        enhanced = processor._enhance_plotly_html(base_html, sample_pipeline_metrics)

        assert "test_run_123" in enhanced
        assert "Pipeline Statistical Report" in enhanced

    def test_enhance_plotly_html_handles_missing_body(self, sample_pipeline_metrics):
        """Test enhancing HTML when body tags are missing."""
        processor = HtmlReportProcessor(ReportFormat.HTML)

        base_html = "<html>No body tags</html>"

        enhanced = processor._enhance_plotly_html(base_html, sample_pipeline_metrics)

        # Should return original when body not found
        assert enhanced == base_html

    def test_visualization_flag_always_true(self):
        """Test HTML processor always has visualizations."""
        processor = HtmlReportProcessor(ReportFormat.HTML)

        assert processor._get_visualization_flag() is True


# =============================================================================
# Markdown Processor Tests
# =============================================================================


class TestMarkdownProcessor:
    """Tests for the Markdown report processor."""

    def test_initialization(self):
        """Test Markdown processor initialization."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        assert processor.format_type == ReportFormat.MARKDOWN
        assert processor.max_length == 2000

    def test_initialization_with_custom_max_length(self):
        """Test Markdown processor with custom max length."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN, max_length=5000)

        assert processor.max_length == 5000

    def test_generate_creates_markdown_file(self, sample_pipeline_metrics, temp_output_dir):
        """Test Markdown generation creates valid file."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        artifact = processor.generate(sample_pipeline_metrics, temp_output_dir)

        assert artifact.file_path.exists()
        assert artifact.file_path.suffix == ".md"

    def test_generated_markdown_has_headers(self, sample_pipeline_metrics, temp_output_dir):
        """Test generated Markdown has proper headers."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        artifact = processor.generate(sample_pipeline_metrics, temp_output_dir)

        content = artifact.file_path.read_text()

        assert "# Pipeline Statistical Report" in content
        assert "## 📊 Overall Metrics" in content
        assert "## 🔧 Module Performance" in content

    def test_generate_markdown_content(self, sample_pipeline_metrics):
        """Test generating Markdown content."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        content = processor._generate_markdown_content(sample_pipeline_metrics)

        assert "test_run_123" in content
        assert "Overall Metrics" in content
        assert "extraction" in content
        assert "enrichment" in content

    def test_generate_markdown_content_has_table(self, sample_pipeline_metrics):
        """Test Markdown content includes module performance table."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        content = processor._generate_markdown_content(sample_pipeline_metrics)

        assert "| Module |" in content
        assert "extraction" in content
        assert "enrichment" in content

    def test_generate_markdown_content_without_links(self, sample_pipeline_metrics):
        """Test generating Markdown without artifact links."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        content = processor._generate_markdown_content(sample_pipeline_metrics, include_links=False)

        assert "Report Artifacts" not in content

    def test_get_status_emoji_success(self):
        """Test status emoji for successful rate."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        emoji = processor._get_status_emoji(0.96)

        assert emoji == "✅"

    def test_get_status_emoji_warning(self):
        """Test status emoji for warning rate."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        emoji = processor._get_status_emoji(0.90)

        assert emoji == "⚠️"

    def test_get_status_emoji_error(self):
        """Test status emoji for error rate."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        emoji = processor._get_status_emoji(0.75)

        assert emoji == "❌"

    def test_identify_quality_issues(self, sample_pipeline_metrics):
        """Test identifying quality issues from metrics."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        issues = processor._identify_quality_issues(sample_pipeline_metrics)

        # With 96% success rate, no issues
        assert len(issues) == 0

    def test_identify_quality_issues_low_success_rate(self, sample_pipeline_metrics):
        """Test identifying low success rate issue."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        # Modify metrics to have low success rate
        sample_pipeline_metrics.overall_success_rate = 0.85

        issues = processor._identify_quality_issues(sample_pipeline_metrics)

        assert len(issues) > 0
        assert any("success rate" in issue.lower() for issue in issues)

    def test_generate_key_insights(self, sample_pipeline_metrics):
        """Test generating key insights."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        insights = processor._generate_key_insights(sample_pipeline_metrics)

        # May or may not have insights depending on metrics
        assert isinstance(insights, list)

    def test_truncate_markdown_no_truncation_needed(self):
        """Test truncating Markdown when under max length."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        content = "Short content"

        truncated = processor._truncate_markdown(content, 1000)

        assert truncated == content

    def test_truncate_markdown_performs_truncation(self):
        """Test truncating Markdown when over max length."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        content = "Long content\n" * 100

        truncated = processor._truncate_markdown(content, 100)

        assert len(truncated) <= 150  # Some margin for truncation message
        assert "truncated" in truncated.lower()

    def test_generate_with_custom_max_length(self, sample_pipeline_metrics, temp_output_dir):
        """Test generation with custom max length parameter."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        artifact = processor.generate(
            sample_pipeline_metrics, temp_output_dir, max_length=500, include_links=False
        )

        content = artifact.file_path.read_text()

        # Content should be truncated
        assert len(content) <= 600  # Some margin for truncation message

    def test_interactive_and_visualization_flags(self):
        """Test Markdown processor flags."""
        processor = MarkdownProcessor(ReportFormat.MARKDOWN)

        assert processor._get_interactive_flag() is False
        assert processor._get_visualization_flag() is False
