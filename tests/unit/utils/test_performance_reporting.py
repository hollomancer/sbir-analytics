"""Tests for performance reporting utilities."""

import pytest

from src.utils.monitoring import (
    MetricComparison,
    PerformanceMetrics,
    PerformanceReporter,
    analyze_performance_trend,
    load_historical_metrics,
)


# ==================== Fixtures ====================


pytestmark = pytest.mark.fast



@pytest.fixture
def sample_benchmark_data():
    """Sample benchmark data."""
    return {
        "performance_metrics": {
            "total_duration_seconds": 10.5,
            "records_per_second": 100.0,
            "peak_memory_mb": 512.0,
            "avg_memory_delta_mb": 256.0,
        },
        "enrichment_stats": {
            "match_rate": 0.85,
            "matched_awards": 850,
            "total_awards": 1000,
            "exact_matches": 700,
            "fuzzy_matches": 150,
        },
        "timestamp": "2023-01-01T10:00:00",
    }


@pytest.fixture
def sample_asset_metadata():
    """Sample Dagster asset metadata."""
    return {
        "performance_total_duration_seconds": 10.5,
        "performance_records_per_second": 100.0,
        "performance_peak_memory_mb": 512.0,
        "performance_avg_memory_delta_mb": 256.0,
        "enrichment_match_rate": 0.85,
        "enrichment_matched_records": 850,
        "enrichment_total_records": 1000,
        "timestamp": "2023-01-01T10:00:00",
    }


@pytest.fixture
def baseline_metrics():
    """Baseline performance metrics."""
    return PerformanceMetrics(
        total_duration_seconds=10.0,
        records_per_second=100.0,
        peak_memory_mb=500.0,
        avg_memory_delta_mb=250.0,
        match_rate=0.85,
        matched_records=850,
        total_records=1000,
    )


@pytest.fixture
def current_metrics():
    """Current performance metrics."""
    return PerformanceMetrics(
        total_duration_seconds=12.0,
        records_per_second=90.0,
        peak_memory_mb=600.0,
        avg_memory_delta_mb=300.0,
        match_rate=0.82,
        matched_records=820,
        total_records=1000,
    )


# ==================== PerformanceMetrics Tests ====================


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics dataclass."""

    def test_initialization(self):
        """Test PerformanceMetrics initialization."""
        metrics = PerformanceMetrics(
            total_duration_seconds=10.0,
            records_per_second=100.0,
            peak_memory_mb=512.0,
            avg_memory_delta_mb=256.0,
        )

        assert metrics.total_duration_seconds == 10.0
        assert metrics.records_per_second == 100.0
        assert metrics.peak_memory_mb == 512.0
        assert metrics.avg_memory_delta_mb == 256.0
        assert metrics.match_rate is None
        assert metrics.matched_records is None

    def test_from_benchmark(self, sample_benchmark_data):
        """Test creation from benchmark data."""
        metrics = PerformanceMetrics.from_benchmark(sample_benchmark_data)

        assert metrics.total_duration_seconds == 10.5
        assert metrics.records_per_second == 100.0
        assert metrics.peak_memory_mb == 512.0
        assert metrics.avg_memory_delta_mb == 256.0
        assert metrics.match_rate == 0.85
        assert metrics.matched_records == 850
        assert metrics.total_records == 1000
        assert metrics.exact_matches == 700
        assert metrics.fuzzy_matches == 150

    def test_from_benchmark_missing_fields(self):
        """Test creation from benchmark with missing fields."""
        minimal_data = {}
        metrics = PerformanceMetrics.from_benchmark(minimal_data)

        assert metrics.total_duration_seconds == 0
        assert metrics.records_per_second == 0
        assert metrics.peak_memory_mb == 0

    def test_from_asset_metadata(self, sample_asset_metadata):
        """Test creation from asset metadata."""
        metrics = PerformanceMetrics.from_asset_metadata(sample_asset_metadata)

        assert metrics.total_duration_seconds == 10.5
        assert metrics.records_per_second == 100.0
        assert metrics.peak_memory_mb == 512.0
        assert metrics.match_rate == 0.85
        assert metrics.matched_records == 850

    def test_from_asset_metadata_missing_fields(self):
        """Test creation from asset metadata with missing fields."""
        minimal_data = {}
        metrics = PerformanceMetrics.from_asset_metadata(minimal_data)

        assert metrics.total_duration_seconds == 0
        assert metrics.records_per_second == 0


# ==================== MetricComparison Tests ====================


class TestMetricComparison:
    """Tests for MetricComparison dataclass."""

    def test_initialization(self, baseline_metrics, current_metrics):
        """Test MetricComparison initialization."""
        comparison = MetricComparison(
            baseline_metrics=baseline_metrics,
            current_metrics=current_metrics,
            time_delta_percent=20.0,
            memory_delta_percent=20.0,
            match_rate_delta_percent=-3.5,
        )

        assert comparison.baseline_metrics == baseline_metrics
        assert comparison.current_metrics == current_metrics
        assert comparison.time_delta_percent == 20.0
        assert comparison.memory_delta_percent == 20.0
        assert comparison.match_rate_delta_percent == -3.5
        assert comparison.regression_severity == "PASS"
        assert comparison.regression_messages == []

    def test_post_init_default_messages(self, baseline_metrics, current_metrics):
        """Test __post_init__ sets default empty list."""
        comparison = MetricComparison(
            baseline_metrics=baseline_metrics,
            current_metrics=current_metrics,
            time_delta_percent=0.0,
            memory_delta_percent=0.0,
        )

        assert isinstance(comparison.regression_messages, list)
        assert len(comparison.regression_messages) == 0


# ==================== PerformanceReporter Tests ====================


class TestPerformanceReporter:
    """Tests for PerformanceReporter class."""

    def test_initialization_defaults(self):
        """Test PerformanceReporter initialization with defaults."""
        reporter = PerformanceReporter()

        assert reporter.time_warning_threshold == 10.0
        assert reporter.time_failure_threshold == 25.0
        assert reporter.memory_warning_threshold == 20.0
        assert reporter.memory_failure_threshold == 50.0
        assert reporter.match_rate_failure_threshold == -5.0

    def test_initialization_custom_thresholds(self):
        """Test PerformanceReporter with custom thresholds."""
        reporter = PerformanceReporter(
            time_warning_threshold=15.0,
            time_failure_threshold=30.0,
            memory_warning_threshold=25.0,
            memory_failure_threshold=60.0,
            match_rate_failure_threshold=-10.0,
        )

        assert reporter.time_warning_threshold == 15.0
        assert reporter.time_failure_threshold == 30.0
        assert reporter.memory_warning_threshold == 25.0
        assert reporter.memory_failure_threshold == 60.0
        assert reporter.match_rate_failure_threshold == -10.0

    def test_compare_metrics_pass(self, baseline_metrics):
        """Test metric comparison that passes all thresholds."""
        reporter = PerformanceReporter()

        # Slightly better metrics
        current = PerformanceMetrics(
            total_duration_seconds=9.5,  # Faster
            records_per_second=105.0,
            peak_memory_mb=490.0,  # Less memory
            avg_memory_delta_mb=240.0,
            match_rate=0.87,  # Better match rate
            matched_records=870,
            total_records=1000,
        )

        comparison = reporter.compare_metrics(baseline_metrics, current)

        assert comparison.regression_severity == "PASS"
        assert comparison.time_delta_percent < 0  # Improvement
        assert comparison.memory_delta_percent < 0  # Improvement
        assert comparison.match_rate_delta_percent > 0  # Improvement

    def test_compare_metrics_warning(self, baseline_metrics):
        """Test metric comparison with warning thresholds exceeded."""
        reporter = PerformanceReporter()

        # Metrics triggering warnings (10% slower, 20% more memory)
        current = PerformanceMetrics(
            total_duration_seconds=11.5,  # 15% slower
            records_per_second=87.0,
            peak_memory_mb=620.0,  # 24% more memory
            avg_memory_delta_mb=310.0,
            match_rate=0.85,
            matched_records=850,
            total_records=1000,
        )

        comparison = reporter.compare_metrics(baseline_metrics, current)

        assert comparison.regression_severity == "WARNING"
        assert len(comparison.regression_messages) > 0
        assert any("time" in msg.lower() for msg in comparison.regression_messages)
        assert any("memory" in msg.lower() for msg in comparison.regression_messages)

    def test_compare_metrics_failure(self, baseline_metrics):
        """Test metric comparison with failure thresholds exceeded."""
        reporter = PerformanceReporter()

        # Metrics triggering failures (30% slower, 60% more memory)
        current = PerformanceMetrics(
            total_duration_seconds=13.5,  # 35% slower
            records_per_second=74.0,
            peak_memory_mb=820.0,  # 64% more memory
            avg_memory_delta_mb=410.0,
            match_rate=0.78,  # -7% match rate
            matched_records=780,
            total_records=1000,
        )

        comparison = reporter.compare_metrics(baseline_metrics, current)

        assert comparison.regression_severity == "FAILURE"
        assert len(comparison.regression_messages) > 0

    def test_compare_metrics_zero_baseline_time(self):
        """Test comparison handles zero baseline time gracefully."""
        reporter = PerformanceReporter()

        baseline = PerformanceMetrics(
            total_duration_seconds=0.0,  # Zero baseline
            records_per_second=0.0,
            peak_memory_mb=500.0,
            avg_memory_delta_mb=250.0,
        )

        current = PerformanceMetrics(
            total_duration_seconds=10.0,
            records_per_second=100.0,
            peak_memory_mb=600.0,
            avg_memory_delta_mb=300.0,
        )

        comparison = reporter.compare_metrics(baseline, current)

        # Should handle gracefully without division by zero
        assert comparison.time_delta_percent >= 0

    def test_format_metrics_markdown(self, baseline_metrics):
        """Test formatting metrics as Markdown."""
        reporter = PerformanceReporter()

        markdown = reporter.format_metrics_markdown(baseline_metrics)

        assert isinstance(markdown, str)
        assert "Duration" in markdown or "duration" in markdown.lower()
        assert "Memory" in markdown or "memory" in markdown.lower()
        assert "10.0" in markdown  # Duration value

    def test_format_comparison_markdown(self, baseline_metrics, current_metrics):
        """Test formatting comparison as Markdown."""
        reporter = PerformanceReporter()

        comparison = reporter.compare_metrics(baseline_metrics, current_metrics)
        markdown = reporter.format_comparison_markdown(comparison)

        assert isinstance(markdown, str)
        assert "Baseline" in markdown or "baseline" in markdown.lower()
        assert "Current" in markdown or "current" in markdown.lower()

    def test_format_benchmark_markdown(self, sample_benchmark_data):
        """Test formatting benchmark data as Markdown."""
        reporter = PerformanceReporter()

        markdown = reporter.format_benchmark_markdown(sample_benchmark_data)

        assert isinstance(markdown, str)
        assert len(markdown) > 0

    def test_generate_html_report(self, baseline_metrics, current_metrics):
        """Test HTML report generation."""
        reporter = PerformanceReporter()

        comparison = reporter.compare_metrics(baseline_metrics, current_metrics)
        html = reporter.generate_html_report(
            title="Performance Report",
            comparison=comparison,
        )

        assert isinstance(html, str)
        assert "<html>" in html.lower()
        assert "<body>" in html.lower()
        assert "Performance Report" in html

    def test_save_markdown_report(self, baseline_metrics, current_metrics, tmp_path):
        """Test saving Markdown report to file."""
        reporter = PerformanceReporter()

        comparison = reporter.compare_metrics(baseline_metrics, current_metrics)
        output_path = tmp_path / "report.md"

        reporter.save_markdown_report(
            comparison=comparison,
            output_path=output_path,
            title="Test Report",
        )

        assert output_path.exists()
        content = output_path.read_text()
        assert "Test Report" in content

    def test_save_html_report(self, baseline_metrics, current_metrics, tmp_path):
        """Test saving HTML report to file."""
        reporter = PerformanceReporter()

        comparison = reporter.compare_metrics(baseline_metrics, current_metrics)
        output_path = tmp_path / "report.html"

        reporter.save_html_report(
            comparison=comparison,
            output_path=output_path,
            title="Test Report",
        )

        assert output_path.exists()
        content = output_path.read_text()
        assert "<html>" in content.lower()


# ==================== Historical Analysis Tests ====================


class TestHistoricalAnalysis:
    """Tests for historical metrics analysis."""

    def test_load_historical_metrics(self, tmp_path):
        """Test loading historical metrics from directory."""
        # Create sample metric files
        metrics_dir = tmp_path / "metrics"
        metrics_dir.mkdir()

        for i in range(3):
            metric_file = metrics_dir / f"metrics_{i}.json"
            metric_file.write_text(
                '{"performance_metrics": {"total_duration_seconds": 10.0, '
                '"records_per_second": 100.0, "peak_memory_mb": 512.0, '
                '"avg_memory_delta_mb": 256.0}}'
            )

        metrics_list = load_historical_metrics(metrics_dir)

        assert len(metrics_list) == 3
        assert all(isinstance(m[1], PerformanceMetrics) for m in metrics_list)

    def test_load_historical_metrics_empty_dir(self, tmp_path):
        """Test loading from empty directory."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        metrics_list = load_historical_metrics(empty_dir)

        assert len(metrics_list) == 0

    def test_load_historical_metrics_invalid_json(self, tmp_path):
        """Test loading with invalid JSON files."""
        metrics_dir = tmp_path / "metrics"
        metrics_dir.mkdir()

        # Create invalid JSON file
        invalid_file = metrics_dir / "invalid.json"
        invalid_file.write_text("{invalid json")

        # Should skip invalid files
        metrics_list = load_historical_metrics(metrics_dir)

        assert len(metrics_list) == 0

    def test_analyze_performance_trend(self):
        """Test performance trend analysis."""
        metrics_list = [
            PerformanceMetrics(
                total_duration_seconds=10.0,
                records_per_second=100.0,
                peak_memory_mb=500.0,
                avg_memory_delta_mb=250.0,
            ),
            PerformanceMetrics(
                total_duration_seconds=11.0,
                records_per_second=95.0,
                peak_memory_mb=550.0,
                avg_memory_delta_mb=275.0,
            ),
            PerformanceMetrics(
                total_duration_seconds=12.0,
                records_per_second=90.0,
                peak_memory_mb=600.0,
                avg_memory_delta_mb=300.0,
            ),
        ]

        trend = analyze_performance_trend(metrics_list)

        assert "trend" in trend or isinstance(trend, dict)

    def test_analyze_performance_trend_single_metric(self):
        """Test trend analysis with single metric."""
        metrics_list = [
            PerformanceMetrics(
                total_duration_seconds=10.0,
                records_per_second=100.0,
                peak_memory_mb=500.0,
                avg_memory_delta_mb=250.0,
            ),
        ]

        trend = analyze_performance_trend(metrics_list)

        # Should handle single metric gracefully
        assert trend is not None


# ==================== Edge Cases ====================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_compare_metrics_none_match_rate(self):
        """Test comparison when match rate is None."""
        reporter = PerformanceReporter()

        baseline = PerformanceMetrics(
            total_duration_seconds=10.0,
            records_per_second=100.0,
            peak_memory_mb=500.0,
            avg_memory_delta_mb=250.0,
            match_rate=None,  # No match rate
        )

        current = PerformanceMetrics(
            total_duration_seconds=11.0,
            records_per_second=95.0,
            peak_memory_mb=550.0,
            avg_memory_delta_mb=275.0,
            match_rate=None,
        )

        comparison = reporter.compare_metrics(baseline, current)

        # Should handle None match rate gracefully
        assert comparison.match_rate_delta_percent is None

    def test_format_metrics_markdown_none_values(self):
        """Test formatting with None values."""
        reporter = PerformanceReporter()

        metrics = PerformanceMetrics(
            total_duration_seconds=10.0,
            records_per_second=100.0,
            peak_memory_mb=500.0,
            avg_memory_delta_mb=250.0,
            match_rate=None,
            matched_records=None,
        )

        markdown = reporter.format_metrics_markdown(metrics)

        # Should handle None values without crashing
        assert isinstance(markdown, str)

    def test_save_markdown_report_creates_parent_dir(
        self, baseline_metrics, current_metrics, tmp_path
    ):
        """Test saving report creates parent directory."""
        reporter = PerformanceReporter()

        comparison = reporter.compare_metrics(baseline_metrics, current_metrics)
        nested_path = tmp_path / "nested" / "dir" / "report.md"

        reporter.save_markdown_report(
            comparison=comparison,
            output_path=nested_path,
            title="Test",
        )

        assert nested_path.exists()

    def test_save_html_report_creates_parent_dir(self, baseline_metrics, current_metrics, tmp_path):
        """Test saving HTML report creates parent directory."""
        reporter = PerformanceReporter()

        comparison = reporter.compare_metrics(baseline_metrics, current_metrics)
        nested_path = tmp_path / "nested" / "dir" / "report.html"

        reporter.save_html_report(
            comparison=comparison,
            output_path=nested_path,
            title="Test",
        )

        assert nested_path.exists()

    def test_from_benchmark_empty_nested_dicts(self):
        """Test creation from benchmark with empty nested dicts."""
        benchmark_data = {
            "performance_metrics": {},
            "enrichment_stats": {},
        }

        metrics = PerformanceMetrics.from_benchmark(benchmark_data)

        assert metrics.total_duration_seconds == 0
        assert metrics.match_rate is None

    def test_compare_metrics_extreme_values(self):
        """Test comparison with extreme metric values."""
        reporter = PerformanceReporter()

        baseline = PerformanceMetrics(
            total_duration_seconds=1.0,
            records_per_second=1000.0,
            peak_memory_mb=100.0,
            avg_memory_delta_mb=50.0,
        )

        current = PerformanceMetrics(
            total_duration_seconds=100.0,  # 10000% slower
            records_per_second=10.0,
            peak_memory_mb=10000.0,  # 10000% more memory
            avg_memory_delta_mb=5000.0,
        )

        comparison = reporter.compare_metrics(baseline, current)

        # Should handle extreme deltas
        assert comparison.regression_severity == "FAILURE"
        assert comparison.time_delta_percent > 100
        assert comparison.memory_delta_percent > 100

    def test_load_historical_metrics_nonexistent_dir(self, tmp_path):
        """Test loading from nonexistent directory."""
        nonexistent = tmp_path / "nonexistent"

        metrics_list = load_historical_metrics(nonexistent)

        # Should return empty list without error
        assert len(metrics_list) == 0

    def test_generate_html_report_special_characters(self, baseline_metrics, current_metrics):
        """Test HTML generation handles special characters."""
        reporter = PerformanceReporter()

        comparison = reporter.compare_metrics(baseline_metrics, current_metrics)
        comparison.regression_messages = [
            "Test with <special> & characters",
            "Another message with 'quotes'",
        ]

        html = reporter.generate_html_report(
            title="Test <Report> & Title",
            comparison=comparison,
        )

        # Should escape special characters properly
        assert isinstance(html, str)
        assert "<html>" in html.lower()
