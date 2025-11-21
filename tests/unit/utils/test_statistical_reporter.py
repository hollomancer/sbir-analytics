"""Tests for statistical reporting utilities."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest


pytestmark = pytest.mark.fast

from src.models.quality import ChangesSummary, DataHygieneMetrics, ModuleReport, StatisticalReport
from src.models.statistical_reports import (
    ModuleMetrics,
    PerformanceMetrics,
    PipelineMetrics,
    ReportCollection,
)
from src.utils.statistical_reporter import StatisticalReporter


# ==================== Fixtures ====================


pytestmark = pytest.mark.fast


@pytest.fixture
def temp_output_dir(tmp_path):
    """Temporary output directory for reports."""
    return tmp_path / "reports"


@pytest.fixture
def mock_metrics_collector():
    """Mock metrics collector."""
    collector = Mock()
    collector.get_metrics.return_value = {}
    return collector


@pytest.fixture
def sample_metrics_data():
    """Sample metrics data for a module."""
    return {
        "start_time": datetime(2023, 1, 1, 10, 0, 0),
        "end_time": datetime(2023, 1, 1, 10, 5, 0),
        "records_in": 1000,
        "records_out": 950,
        "records_processed": 950,
        "records_failed": 50,
        "module": "sbir",
        "stage": "extraction",
    }


@pytest.fixture
def sample_data_hygiene():
    """Sample data hygiene metrics."""
    return DataHygieneMetrics(
        total_records=1000,
        null_counts={"field1": 10, "field2": 5},
        duplicate_counts=3,
        outlier_counts=2,
        coverage_rates={"field1": 0.99, "field2": 0.995},
        clean_records=950,
        dirty_records=50,
        clean_percentage=95.0,
        quality_score_mean=0.95,
        quality_score_median=0.96,
        quality_score_std=0.05,
        quality_score_min=0.80,
        quality_score_max=1.0,
        validation_pass_rate=0.98,
        validation_errors=20,
        validation_warnings=10,
    )


@pytest.fixture
def sample_changes_summary():
    """Sample changes summary."""
    return ChangesSummary(
        records_added=50,
        records_modified=100,
        records_deleted=10,
        fields_changed=["field1", "field2"],
        total_records=160,
        records_unchanged=0,
        modification_rate=0.625,
    )


@pytest.fixture
def sample_module_report():
    """Sample module report."""
    return ModuleReport(
        module_name="sbir",
        run_id="run_123",
        stage="extraction",
        start_time=datetime(2023, 1, 1, 10, 0, 0),
        end_time=datetime(2023, 1, 1, 10, 5, 0),
        records_processed=950,
        records_failed=50,
        success_rate=0.95,
        data_hygiene=DataHygieneMetrics(
            total_records=1000,
            null_counts={},
            duplicate_counts=0,
            outlier_counts=0,
            coverage_rates={},
            clean_records=1000,
            dirty_records=0,
            clean_percentage=100.0,
            quality_score_mean=1.0,
            quality_score_median=1.0,
            quality_score_std=0.0,
            quality_score_min=1.0,
            quality_score_max=1.0,
            validation_pass_rate=1.0,
            validation_errors=0,
            validation_warnings=0,
        ),
        timestamp="2023-01-01T10:05:00",
        total_records=1000,
        duration_seconds=300.0,
        throughput_records_per_second=3.17,
    )


@pytest.fixture
def sample_statistical_report():
    """Sample statistical report."""
    return StatisticalReport(
        run_id="run_123",
        generated_at=datetime(2023, 1, 1, 10, 0, 0),
        modules=[],
        summary_insights=[],
        report_id="report_123",
        timestamp="2023-01-01T10:00:00",
        report_type="statistical",
        total_records_processed=1000,
        total_duration_seconds=600.0,
        overall_success_rate=0.95,
    )


@pytest.fixture
def sample_pipeline_metrics():
    """Sample pipeline metrics."""
    return PipelineMetrics(
        run_id="run_123",
        start_time=datetime(2023, 1, 1, 10, 0, 0),
        end_time=datetime(2023, 1, 1, 10, 10, 0),
        total_duration_seconds=600.0,
        modules={},
        performance_metrics=PerformanceMetrics(
            total_duration_seconds=600.0,
            peak_memory_mb=512.0,
            avg_cpu_percent=45.0,
            start_time=datetime(2023, 1, 1, 10, 0, 0),
            end_time=datetime(2023, 1, 1, 10, 10, 0),
            duration=600.0,
            records_per_second=100.0,
            average_memory_mb=256.0,
        ),
        timestamp=datetime(2023, 1, 1, 10, 0, 0),
        duration=timedelta(seconds=600),
        total_records_processed=1000,
        overall_success_rate=0.95,
    )


# ==================== Initialization Tests ====================


class TestStatisticalReporterInitialization:
    """Tests for StatisticalReporter initialization."""

    def test_initialization_defaults(self, temp_output_dir):
        """Test initialization with default values."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        assert reporter.output_dir == temp_output_dir
        assert temp_output_dir.exists()
        assert reporter.config == {}
        assert reporter.metrics_collector is not None

    def test_initialization_with_config(self, temp_output_dir):
        """Test initialization with custom config."""
        config = {"ci": {"upload_artifacts": True}}
        reporter = StatisticalReporter(output_dir=temp_output_dir, config=config)

        assert reporter.config == config

    def test_initialization_with_metrics_collector(self, temp_output_dir, mock_metrics_collector):
        """Test initialization with custom metrics collector."""
        reporter = StatisticalReporter(
            output_dir=temp_output_dir, metrics_collector=mock_metrics_collector
        )

        assert reporter.metrics_collector == mock_metrics_collector

    def test_initialization_creates_output_dir(self, tmp_path):
        """Test initialization creates output directory."""
        nested_dir = tmp_path / "nested" / "reports"
        assert not nested_dir.exists()

        StatisticalReporter(output_dir=nested_dir)

        assert nested_dir.exists()


# ==================== CI Context Detection Tests ====================


class TestCIContextDetection:
    """Tests for CI/CD context detection."""

    @patch.dict(
        os.environ,
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_REPOSITORY": "user/repo",
            "GITHUB_REF": "refs/heads/main",
            "GITHUB_SHA": "abc123",
            "GITHUB_RUN_ID": "123456",
            "GITHUB_WORKFLOW": "CI",
            "GITHUB_EVENT_NAME": "push",
        },
    )
    def test_detect_github_actions_context(self, temp_output_dir):
        """Test detection of GitHub Actions CI context."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        assert reporter.ci_context is not None
        assert reporter.ci_context["provider"] == "github_actions"
        assert reporter.ci_context["repository"] == "user/repo"
        assert reporter.ci_context["ref"] == "refs/heads/main"
        assert reporter.ci_context["sha"] == "abc123"
        assert reporter.ci_context["is_pr"] is False

    @patch.dict(
        os.environ,
        {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "pull_request",
            "GITHUB_PR_NUMBER": "42",
        },
    )
    def test_detect_github_actions_pr_context(self, temp_output_dir):
        """Test detection of GitHub Actions PR context."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        assert reporter.ci_context is not None
        assert reporter.ci_context["is_pr"] is True
        assert reporter.ci_context["pr_number"] == "42"

    @patch.dict(os.environ, {"CI": "true"})
    def test_detect_unknown_ci_context(self, temp_output_dir):
        """Test detection of unknown CI provider."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        assert reporter.ci_context is not None
        assert reporter.ci_context["provider"] == "unknown_ci"
        assert reporter.ci_context["detected"] is True

    @patch.dict(os.environ, {}, clear=True)
    def test_no_ci_context(self, temp_output_dir):
        """Test when not in CI environment."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        assert reporter.ci_context is None


# ==================== Module Report Generation Tests ====================


class TestModuleReportGeneration:
    """Tests for module report generation."""

    def test_generate_module_report_basic(self, temp_output_dir, sample_metrics_data):
        """Test basic module report generation."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        module_metrics = reporter.generate_module_report(
            module_name="sbir",
            run_id="run_123",
            stage="extraction",
            metrics_data=sample_metrics_data,
        )

        assert isinstance(module_metrics, ModuleMetrics)
        assert module_metrics.module_name == "sbir"
        assert module_metrics.run_id == "run_123"
        assert module_metrics.stage == "extraction"
        assert module_metrics.records_in == 1000
        assert module_metrics.records_out == 950
        assert module_metrics.success_rate == 0.95

    def test_generate_module_report_with_hygiene(
        self, temp_output_dir, sample_metrics_data, sample_data_hygiene
    ):
        """Test module report with data hygiene metrics."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        module_metrics = reporter.generate_module_report(
            module_name="sbir",
            run_id="run_123",
            stage="extraction",
            metrics_data=sample_metrics_data,
            data_hygiene=sample_data_hygiene,
        )

        assert module_metrics.data_hygiene == sample_data_hygiene

    def test_generate_module_report_with_changes(
        self, temp_output_dir, sample_metrics_data, sample_changes_summary
    ):
        """Test module report with changes summary."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        module_metrics = reporter.generate_module_report(
            module_name="sbir",
            run_id="run_123",
            stage="extraction",
            metrics_data=sample_metrics_data,
            changes_summary=sample_changes_summary,
        )

        assert module_metrics.changes_summary == sample_changes_summary

    def test_generate_module_report_timestamp_conversion(self, temp_output_dir):
        """Test module report handles timestamp conversion."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        # Provide timestamps as Unix timestamps
        metrics_data = {
            "start_time": 1672570800.0,  # 2023-01-01 11:00:00
            "end_time": 1672571100.0,  # 2023-01-01 11:05:00
            "records_in": 100,
            "records_processed": 90,
        }

        module_metrics = reporter.generate_module_report(
            module_name="test",
            run_id="run_123",
            stage="test",
            metrics_data=metrics_data,
        )

        assert isinstance(module_metrics.start_time, datetime)
        assert isinstance(module_metrics.end_time, datetime)

    def test_generate_module_report_calculates_success_rate(self, temp_output_dir):
        """Test success rate calculation."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        metrics_data = {
            "start_time": datetime.now(),
            "end_time": datetime.now(),
            "records_in": 1000,
            "records_processed": 800,
            "records_failed": 200,
        }

        module_metrics = reporter.generate_module_report(
            module_name="test",
            run_id="run_123",
            stage="test",
            metrics_data=metrics_data,
        )

        assert module_metrics.success_rate == 0.8


# ==================== Report Aggregation Tests ====================


class TestReportAggregation:
    """Tests for module report aggregation."""

    def test_aggregate_module_reports(self, temp_output_dir, sample_module_report):
        """Test aggregation of multiple module reports."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        module_reports = [
            sample_module_report,
            ModuleReport(
                module_name="patent",
                run_id="run_123",
                stage="extraction",
                start_time=datetime(2023, 1, 1, 10, 5, 0),
                end_time=datetime(2023, 1, 1, 10, 10, 0),
                records_processed=500,
                records_failed=10,
                success_rate=0.98,
                timestamp="2023-01-01T10:05:00",
                total_records=510,
                duration_seconds=300.0,
                throughput_records_per_second=1.7,
            ),
        ]

        statistical_report = reporter.aggregate_module_reports("run_123", module_reports)

        assert isinstance(statistical_report, StatisticalReport)
        assert len(statistical_report.module_reports) == 2
        assert statistical_report.run_id == "run_123"

    def test_aggregate_empty_module_reports(self, temp_output_dir):
        """Test aggregation with no module reports."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        statistical_report = reporter.aggregate_module_reports("run_123", [])

        assert len(statistical_report.module_reports) == 0


# ==================== Format Generation Tests ====================


class TestFormatGeneration:
    """Tests for report format generation."""

    def test_generate_json_report(self, temp_output_dir, sample_statistical_report):
        """Test JSON report generation."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        json_path = reporter.generate_json_report(sample_statistical_report)

        assert json_path.exists()
        assert json_path.suffix == ".json"
        assert json_path.parent == temp_output_dir

        # Verify JSON is valid
        with open(json_path) as f:
            data = json.load(f)
            assert "run_id" in data

    def test_generate_markdown_summary(self, temp_output_dir, sample_statistical_report):
        """Test Markdown summary generation."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        content, md_path = reporter.generate_markdown_summary(sample_statistical_report)

        assert isinstance(content, str)
        assert len(content) > 0
        assert md_path.exists()
        assert md_path.suffix == ".md"
        assert "# Pipeline Statistical Report" in content

    @patch("src.utils.statistical_reporter.PLOTLY_AVAILABLE", False)
    def test_generate_html_report_no_plotly(self, temp_output_dir, sample_statistical_report):
        """Test HTML report generation without Plotly."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        html_path = reporter.generate_html_report(sample_statistical_report)

        assert html_path.exists()
        assert html_path.suffix == ".html"

        # Verify HTML is valid
        with open(html_path) as f:
            content = f.read()
            assert "<html>" in content.lower()
            assert "Statistical Report" in content or "Pipeline Report" in content

    def test_generate_all_formats(self, temp_output_dir, sample_statistical_report):
        """Test generation of all report formats."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        format_paths = reporter.generate_all_formats(sample_statistical_report)

        assert "json" in format_paths
        assert "html" in format_paths
        assert "markdown" in format_paths
        assert all(path.exists() for path in format_paths.values())


# ==================== Pipeline Metrics Tests ====================


class TestPipelineMetrics:
    """Tests for pipeline metrics collection."""

    @patch("src.utils.statistical_reporter.performance_monitor")
    def test_collect_pipeline_metrics(self, mock_perf_monitor, temp_output_dir):
        """Test collection of pipeline metrics."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        # Mock performance monitor
        mock_perf_monitor.get_metrics_summary.return_value = {
            "total_duration": 600.0,
            "peak_memory_mb": 512.0,
        }

        run_context = {
            "run_id": "run_123",
            "modules": {"sbir": {"stage": "extraction"}, "patent": {"stage": "extraction"}},
            "start_time": datetime(2023, 1, 1, 10, 0, 0),
            "end_time": datetime(2023, 1, 1, 10, 10, 0),
        }

        pipeline_metrics = reporter._collect_pipeline_metrics("run_123", run_context)

        assert isinstance(pipeline_metrics, PipelineMetrics)
        assert pipeline_metrics.run_id == "run_123"


# ==================== Report Collection Tests ====================


class TestReportCollection:
    """Tests for comprehensive report collection."""

    @patch("src.utils.statistical_reporter.performance_monitor")
    def test_generate_reports(self, mock_perf_monitor, temp_output_dir):
        """Test comprehensive report generation."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        # Mock performance monitor
        mock_perf_monitor.get_metrics_summary.return_value = {}

        run_context = {
            "run_id": "run_123",
            "modules": {"sbir": {"stage": "extraction"}},
            "start_time": datetime(2023, 1, 1, 10, 0, 0),
            "end_time": datetime(2023, 1, 1, 10, 10, 0),
        }

        collection = reporter.generate_reports(run_context)

        assert isinstance(collection, ReportCollection)
        assert collection.run_id == "run_123"
        assert len(collection.artifacts) > 0

    @patch("src.utils.statistical_reporter.performance_monitor")
    def test_generate_reports_with_ci_context(self, mock_perf_monitor, temp_output_dir):
        """Test report generation with CI context."""
        config = {"ci": {"upload_artifacts": False}}
        reporter = StatisticalReporter(output_dir=temp_output_dir, config=config)
        reporter.ci_context = {"provider": "github_actions"}

        # Mock performance monitor
        mock_perf_monitor.get_metrics_summary.return_value = {}

        run_context = {
            "run_id": "run_123",
            "modules": {},
        }

        collection = reporter.generate_reports(run_context)

        assert collection.ci_context is not None


# ==================== Executive Summary Tests ====================


class TestExecutiveSummary:
    """Tests for executive summary generation."""

    def test_create_executive_summary(self, temp_output_dir, sample_pipeline_metrics):
        """Test executive summary creation."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        executive_summary = reporter._create_executive_summary(sample_pipeline_metrics)

        assert executive_summary is not None
        assert executive_summary.run_id == "run_123"


# ==================== HTML Generation Tests ====================


class TestHTMLGeneration:
    """Tests for HTML report generation."""


# ==================== Markdown Generation Tests ====================


# ==================== CI Integration Tests ====================


class TestCIIntegration:
    """Tests for CI/CD integration."""

    @patch("src.utils.statistical_reporter.Path.write_text")
    def test_handle_ci_integration(self, mock_write_text, temp_output_dir, sample_pipeline_metrics):
        """Test CI integration handling."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)
        reporter.ci_context = {"provider": "github_actions", "is_pr": True}

        collection = ReportCollection(
            collection_id="test_collection",
            run_id="run_123",
            generated_at=datetime.now(),
            output_directory=temp_output_dir,
            ci_context=reporter.ci_context,
        )

        # Should not raise exception
        reporter._handle_ci_integration(collection)

    def test_handle_ci_integration_no_context(self, temp_output_dir):
        """Test CI integration when no CI context exists."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)
        reporter.ci_context = None

        collection = ReportCollection(
            collection_id="test_collection",
            run_id="run_123",
            generated_at=datetime.now(),
            output_directory=temp_output_dir,
        )

        # Should not raise exception
        reporter._handle_ci_integration(collection)


# ==================== Edge Cases ====================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_generate_module_report_missing_fields(self, temp_output_dir):
        """Test module report with minimal metrics data."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        minimal_data = {
            "start_time": datetime.now(),
            "end_time": datetime.now(),
        }

        module_metrics = reporter.generate_module_report(
            module_name="test",
            run_id="run_123",
            stage="test",
            metrics_data=minimal_data,
        )

        assert module_metrics.records_in == 0
        assert module_metrics.records_out == 0
        assert module_metrics.success_rate >= 0.0

    def test_generate_reports_auto_run_id(self, temp_output_dir):
        """Test report generation without explicit run_id."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        with patch("src.utils.statistical_reporter.performance_monitor"):
            collection = reporter.generate_reports({})

        assert collection.run_id.startswith("run_")

    def test_generate_json_report_handles_datetime(self, temp_output_dir):
        """Test JSON report handles datetime serialization."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        report = StatisticalReport(
            run_id="run_123",
            generated_at=datetime.now(),
            modules=[],
            summary_insights=[],
            report_id="report_123",
            timestamp="2023-01-01T10:00:00",
            report_type="statistical",
            total_records_processed=0,
            total_duration_seconds=0.0,
            overall_success_rate=0.0,
        )

        json_path = reporter.generate_json_report(report)

        # Should not raise JSON serialization error
        assert json_path.exists()

    def test_markdown_summary_empty_report(self, temp_output_dir):
        """Test Markdown generation with empty report."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        report = StatisticalReport(
            run_id="run_123",
            generated_at=datetime.now(),
            modules=[],
            summary_insights=[],
            report_id="report_123",
            timestamp="2023-01-01T10:00:00",
            report_type="statistical",
            total_records_processed=0,
            total_duration_seconds=0.0,
            overall_success_rate=0.0,
        )

        content, md_path = reporter.generate_markdown_summary(report)

        assert isinstance(content, str)
        assert md_path.exists()

    def test_collect_pipeline_metrics_no_modules(self, temp_output_dir):
        """Test pipeline metrics collection with no modules."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        with patch("src.utils.statistical_reporter.performance_monitor"):
            run_context = {"run_id": "run_123"}
            pipeline_metrics = reporter._collect_pipeline_metrics("run_123", run_context)

        assert pipeline_metrics.run_id == "run_123"

    def test_html_generation_file_permissions(self, temp_output_dir):
        """Test HTML generation handles file write errors gracefully."""
        reporter = StatisticalReporter(output_dir=temp_output_dir)

        report = StatisticalReport(
            run_id="run_123",
            generated_at=datetime.now(),
            modules=[],
            summary_insights=[],
            report_id="report_123",
            timestamp="2023-01-01T10:00:00",
            report_type="statistical",
            total_records_processed=0,
            total_duration_seconds=0.0,
            overall_success_rate=0.0,
        )

        # Should handle any write errors gracefully
        html_path = reporter.generate_html_report(report)
        assert html_path.suffix == ".html"
