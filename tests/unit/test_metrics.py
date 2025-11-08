"""Unit tests for metrics collection system."""

import json
import tempfile
import time
from pathlib import Path

import pytest

from src.exceptions import ValidationError
from src.utils.metrics import MetricsCollector, PipelineMetrics


pytestmark = pytest.mark.fast


class TestPipelineMetrics:
    """Test PipelineMetrics dataclass functionality."""

    def test_create_metrics(self):
        """Test creating metrics with default values."""
        metrics = PipelineMetrics(run_id="run-123", stage="extract")

        assert metrics.run_id == "run-123"
        assert metrics.stage == "extract"
        assert metrics.records_processed == 0
        assert metrics.records_failed == 0
        assert metrics.records_succeeded == 0
        assert metrics.duration_seconds is None
        assert metrics.throughput_records_per_second is None
        assert metrics.metadata == {}
        assert metrics.errors == []

    def test_complete_metrics(self):
        """Test completing metrics calculates duration and throughput."""
        metrics = PipelineMetrics(run_id="run-123", stage="extract")
        metrics.records_processed = 1000

        # Simulate some processing time
        time.sleep(0.1)
        metrics.complete()

        assert metrics.end_time is not None
        assert metrics.duration_seconds is not None
        assert metrics.duration_seconds > 0
        assert metrics.throughput_records_per_second is not None
        assert metrics.throughput_records_per_second > 0

    def test_complete_metrics_zero_records(self):
        """Test completing metrics with zero records."""
        metrics = PipelineMetrics(run_id="run-123", stage="extract")
        metrics.complete()

        assert metrics.end_time is not None
        assert metrics.duration_seconds is not None
        assert metrics.throughput_records_per_second is None

    def test_add_error(self):
        """Test adding error increments failed count."""
        metrics = PipelineMetrics(run_id="run-123", stage="extract")

        metrics.add_error("Connection timeout")
        assert len(metrics.errors) == 1
        assert metrics.errors[0] == "Connection timeout"
        assert metrics.records_failed == 1

        metrics.add_error("Invalid data format")
        assert len(metrics.errors) == 2
        assert metrics.records_failed == 2

    def test_increment_processed(self):
        """Test incrementing processed records count."""
        metrics = PipelineMetrics(run_id="run-123", stage="extract")

        metrics.increment_processed()
        assert metrics.records_processed == 1

        metrics.increment_processed(5)
        assert metrics.records_processed == 6

    def test_increment_succeeded(self):
        """Test incrementing succeeded records count."""
        metrics = PipelineMetrics(run_id="run-123", stage="extract")

        metrics.increment_succeeded()
        assert metrics.records_succeeded == 1

        metrics.increment_succeeded(10)
        assert metrics.records_succeeded == 11

    def test_to_dict(self):
        """Test converting metrics to dictionary."""
        metrics = PipelineMetrics(run_id="run-123", stage="extract", metadata={"source": "csv"})
        metrics.records_processed = 100
        metrics.complete()

        result = metrics.to_dict()

        assert isinstance(result, dict)
        assert result["run_id"] == "run-123"
        assert result["stage"] == "extract"
        assert result["records_processed"] == 100
        assert result["metadata"] == {"source": "csv"}
        assert "duration_seconds" in result
        assert "throughput_records_per_second" in result


class TestMetricsCollector:
    """Test MetricsCollector class functionality."""

    def test_create_collector(self):
        """Test creating metrics collector with default output dir."""
        collector = MetricsCollector()
        assert collector.output_dir == Path("./metrics")
        assert collector.metrics == {}

    def test_create_collector_custom_dir(self):
        """Test creating metrics collector with custom output dir."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = MetricsCollector(output_dir=Path(tmpdir))
            assert collector.output_dir == Path(tmpdir)

    def test_start_stage(self):
        """Test starting metrics tracking for a stage."""
        collector = MetricsCollector()
        metadata = {"source": "csv", "filename": "data.csv"}

        metrics = collector.start_stage("run-123", "extract", metadata)

        assert isinstance(metrics, PipelineMetrics)
        assert metrics.run_id == "run-123"
        assert metrics.stage == "extract"
        assert metrics.metadata == metadata
        assert "run-123:extract" in collector.metrics

    def test_start_stage_overwrites_existing(self):
        """Test starting stage with same key overwrites previous."""
        collector = MetricsCollector()

        metrics1 = collector.start_stage("run-123", "extract")
        metrics1.records_processed = 100

        metrics2 = collector.start_stage("run-123", "extract")

        assert metrics2.records_processed == 0
        assert collector.metrics["run-123:extract"] is metrics2

    def test_complete_stage(self):
        """Test completing metrics tracking for a stage."""
        collector = MetricsCollector()
        metrics = collector.start_stage("run-123", "extract")
        metrics.records_processed = 500

        time.sleep(0.05)
        completed = collector.complete_stage("run-123", "extract")

        assert completed is not None
        assert completed.duration_seconds is not None
        assert completed.duration_seconds > 0

    def test_complete_stage_not_found(self):
        """Test completing stage that doesn't exist returns None."""
        collector = MetricsCollector()
        result = collector.complete_stage("run-123", "nonexistent")
        assert result is None

    def test_get_metrics(self):
        """Test retrieving metrics for a specific stage."""
        collector = MetricsCollector()
        metrics = collector.start_stage("run-123", "extract")

        retrieved = collector.get_metrics("run-123", "extract")

        assert retrieved is metrics
        assert retrieved.run_id == "run-123"
        assert retrieved.stage == "extract"

    def test_get_metrics_not_found(self):
        """Test retrieving metrics that don't exist returns None."""
        collector = MetricsCollector()
        result = collector.get_metrics("run-123", "nonexistent")
        assert result is None

    def test_persist_metrics(self):
        """Test persisting metrics to JSON file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = MetricsCollector(output_dir=Path(tmpdir))
            metrics = collector.start_stage("run-123", "extract")
            metrics.records_processed = 100
            metrics.complete()

            filepath = collector.persist_metrics("run-123", "extract")

            assert filepath.exists()
            assert filepath.parent == Path(tmpdir)
            assert "run-123_extract" in filepath.name
            assert filepath.suffix == ".json"

            # Verify JSON content
            with open(filepath) as f:
                data = json.load(f)
                assert data["run_id"] == "run-123"
                assert data["stage"] == "extract"
                assert data["records_processed"] == 100

    def test_persist_metrics_not_found_raises(self):
        """Test persisting metrics that don't exist raises ValidationError."""
        collector = MetricsCollector()

        with pytest.raises(ValidationError, match="No metrics found"):
            collector.persist_metrics("run-123", "nonexistent")

    def test_persist_all_metrics(self):
        """Test persisting all metrics for a run."""
        with tempfile.TemporaryDirectory() as tmpdir:
            collector = MetricsCollector(output_dir=Path(tmpdir))

            # Create multiple stages
            collector.start_stage("run-123", "extract")
            collector.start_stage("run-123", "validate")
            collector.start_stage("run-123", "load")
            collector.start_stage("run-456", "extract")  # Different run

            filepaths = collector.persist_all_metrics("run-123")

            assert len(filepaths) == 3
            assert all(fp.exists() for fp in filepaths)
            assert all("run-123" in fp.name for fp in filepaths)

    def test_get_summary(self):
        """Test getting summary of all metrics for a run."""
        collector = MetricsCollector()

        # Create and complete multiple stages
        m1 = collector.start_stage("run-123", "extract")
        m1.records_processed = 100
        m1.records_succeeded = 95
        m1.records_failed = 5
        m1.complete()

        m2 = collector.start_stage("run-123", "validate")
        m2.records_processed = 95
        m2.records_succeeded = 90
        m2.records_failed = 5
        m2.complete()

        summary = collector.get_summary("run-123")

        assert summary["run_id"] == "run-123"
        assert summary["stages"] == 2
        assert summary["total_records_processed"] == 195
        assert summary["total_records_succeeded"] == 185
        assert summary["total_records_failed"] == 10
        assert summary["total_duration_seconds"] > 0
        assert len(summary["stages_detail"]) == 2

    def test_get_summary_no_metrics(self):
        """Test getting summary when no metrics exist."""
        collector = MetricsCollector()
        summary = collector.get_summary("run-123")

        assert summary["run_id"] == "run-123"
        assert summary["stages"] == 0
        assert summary["total_records"] == 0

    def test_multiple_runs(self):
        """Test tracking metrics for multiple pipeline runs."""
        collector = MetricsCollector()

        # Run 1
        collector.start_stage("run-123", "extract")
        collector.start_stage("run-123", "validate")

        # Run 2
        collector.start_stage("run-456", "extract")

        summary1 = collector.get_summary("run-123")
        summary2 = collector.get_summary("run-456")

        assert summary1["stages"] == 2
        assert summary2["stages"] == 1
