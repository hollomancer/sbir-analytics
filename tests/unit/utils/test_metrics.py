"""Unit tests for metrics collection and tracking.

Tests cover:
- PipelineMetrics creation and lifecycle
- Metrics completion and calculations
- Error tracking
- MetricsCollector management
- Metrics persistence
- Stage tracking
"""

import json
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.utils.metrics import MetricsCollector, PipelineMetrics

pytestmark = pytest.mark.fast


class TestPipelineMetrics:
    """Tests for PipelineMetrics dataclass."""

    def test_metrics_initialization(self):
        """Test creating pipeline metrics."""
        metrics = PipelineMetrics(run_id="test_run", stage="extraction")

        assert metrics.run_id == "test_run"
        assert metrics.stage == "extraction"
        assert metrics.records_processed == 0
        assert metrics.records_failed == 0
        assert metrics.errors == []
        assert metrics.end_time is None

    def test_metrics_complete(self):
        """Test completing metrics calculation."""
        metrics = PipelineMetrics(run_id="test_run", stage="extraction")
        metrics.records_processed = 1000

        # Simulate some work
        time.sleep(0.01)

        metrics.complete()

        assert metrics.end_time is not None
        assert metrics.duration_seconds is not None
        assert metrics.duration_seconds > 0
        assert metrics.throughput_records_per_second is not None
        assert metrics.throughput_records_per_second > 0

    def test_metrics_complete_zero_records(self):
        """Test completing metrics with zero records."""
        metrics = PipelineMetrics(run_id="test_run", stage="extraction")

        metrics.complete()

        assert metrics.end_time is not None
        assert metrics.duration_seconds is not None
        assert metrics.throughput_records_per_second is None

    def test_add_error(self):
        """Test adding error to metrics."""
        metrics = PipelineMetrics(run_id="test_run", stage="extraction")

        metrics.add_error("Test error message")

        assert len(metrics.errors) == 1
        assert metrics.errors[0] == "Test error message"
        assert metrics.records_failed == 1

    def test_add_multiple_errors(self):
        """Test adding multiple errors."""
        metrics = PipelineMetrics(run_id="test_run", stage="extraction")

        metrics.add_error("Error 1")
        metrics.add_error("Error 2")
        metrics.add_error("Error 3")

        assert len(metrics.errors) == 3
        assert metrics.records_failed == 3

    def test_increment_processed(self):
        """Test incrementing processed records."""
        metrics = PipelineMetrics(run_id="test_run", stage="extraction")

        metrics.increment_processed()
        metrics.increment_processed()
        metrics.increment_processed(5)

        assert metrics.records_processed == 7

    def test_increment_succeeded(self):
        """Test incrementing succeeded records."""
        metrics = PipelineMetrics(run_id="test_run", stage="extraction")

        metrics.increment_succeeded()
        metrics.increment_succeeded()
        metrics.increment_succeeded(3)

        assert metrics.records_succeeded == 5

    def test_to_dict(self):
        """Test converting metrics to dictionary."""
        metrics = PipelineMetrics(run_id="test_run", stage="extraction")
        metrics.records_processed = 100
        metrics.metadata = {"source": "test"}

        result = metrics.to_dict()

        assert isinstance(result, dict)
        assert result["run_id"] == "test_run"
        assert result["stage"] == "extraction"
        assert result["records_processed"] == 100
        assert result["metadata"]["source"] == "test"

    def test_throughput_calculation(self):
        """Test throughput calculation."""
        metrics = PipelineMetrics(run_id="test_run", stage="extraction")
        metrics.records_processed = 1000

        # Simulate 1 second of processing
        metrics.start_time = time.time() - 1.0
        metrics.complete()

        # Throughput should be approximately 1000 records/sec
        assert metrics.throughput_records_per_second is not None
        assert 900 < metrics.throughput_records_per_second < 1100

    def test_metadata_tracking(self):
        """Test metadata can be tracked."""
        metadata = {"pipeline": "sbir", "version": "1.0", "environment": "test"}
        metrics = PipelineMetrics(run_id="test_run", stage="extraction", metadata=metadata)

        assert metrics.metadata["pipeline"] == "sbir"
        assert metrics.metadata["version"] == "1.0"


class TestMetricsCollector:
    """Tests for MetricsCollector class."""

    def test_collector_initialization(self, tmp_path):
        """Test initializing metrics collector."""
        output_dir = tmp_path / "metrics"
        collector = MetricsCollector(output_dir=output_dir)

        assert collector.output_dir == output_dir
        assert output_dir.exists()
        assert isinstance(collector.metrics, dict)

    def test_collector_default_output_dir(self):
        """Test collector with default output directory."""
        collector = MetricsCollector()

        assert collector.output_dir == Path("./metrics")

    def test_start_stage(self, tmp_path):
        """Test starting a stage."""
        collector = MetricsCollector(output_dir=tmp_path)

        metrics = collector.start_stage("run_001", "extraction", metadata={"test": "value"})

        assert metrics is not None
        assert metrics.run_id == "run_001"
        assert metrics.stage == "extraction"
        assert metrics.metadata["test"] == "value"
        assert "run_001:extraction" in collector.metrics

    def test_start_stage_overwrites_existing(self, tmp_path):
        """Test that starting a stage twice overwrites."""
        collector = MetricsCollector(output_dir=tmp_path)

        metrics1 = collector.start_stage("run_001", "extraction")
        metrics2 = collector.start_stage("run_001", "extraction")

        assert metrics1 is not metrics2
        assert collector.metrics["run_001:extraction"] is metrics2

    def test_complete_stage(self, tmp_path):
        """Test completing a stage."""
        collector = MetricsCollector(output_dir=tmp_path)

        collector.start_stage("run_001", "extraction")
        time.sleep(0.01)
        completed_metrics = collector.complete_stage("run_001", "extraction")

        assert completed_metrics is not None
        assert completed_metrics.end_time is not None
        assert completed_metrics.duration_seconds is not None

    def test_complete_stage_not_found(self, tmp_path):
        """Test completing non-existent stage."""
        collector = MetricsCollector(output_dir=tmp_path)

        result = collector.complete_stage("run_001", "nonexistent")

        assert result is None

    def test_get_metrics(self, tmp_path):
        """Test retrieving metrics for a stage."""
        collector = MetricsCollector(output_dir=tmp_path)

        collector.start_stage("run_001", "extraction")
        metrics = collector.get_metrics("run_001", "extraction")

        assert metrics is not None
        assert metrics.run_id == "run_001"
        assert metrics.stage == "extraction"

    def test_get_metrics_not_found(self, tmp_path):
        """Test retrieving non-existent metrics."""
        collector = MetricsCollector(output_dir=tmp_path)

        metrics = collector.get_metrics("run_001", "nonexistent")

        assert metrics is None

    def test_persist_metrics(self, tmp_path):
        """Test persisting metrics to disk."""
        collector = MetricsCollector(output_dir=tmp_path)

        metrics = collector.start_stage("run_001", "extraction")
        metrics.records_processed = 1000
        metrics.complete()

        filepath = collector.persist_metrics("run_001", "extraction")

        # Verify file was created
        assert filepath.exists()
        assert "run_001_extraction" in str(filepath)

        # Verify contents
        with open(filepath) as f:
            data = json.load(f)

        assert data["run_id"] == "run_001"
        assert data["stage"] == "extraction"
        assert data["records_processed"] == 1000

    def test_persist_metrics_not_found(self, tmp_path):
        """Test persisting non-existent metrics."""
        from src.exceptions import ValidationError

        collector = MetricsCollector(output_dir=tmp_path)

        with pytest.raises(ValidationError):
            collector.persist_metrics("run_001", "nonexistent")

    def test_persist_all_metrics(self, tmp_path):
        """Test persisting all metrics for a run."""
        collector = MetricsCollector(output_dir=tmp_path)

        collector.start_stage("run_001", "extraction")
        collector.start_stage("run_001", "loading")
        collector.start_stage("run_002", "extraction")

        filepaths = collector.persist_all_metrics("run_001")

        assert len(filepaths) == 2
        for filepath in filepaths:
            assert filepath.exists()
            assert "run_001" in str(filepath)

    def test_metrics_workflow(self, tmp_path):
        """Test complete metrics workflow."""
        collector = MetricsCollector(output_dir=tmp_path)

        # Start stage
        metrics = collector.start_stage("run_001", "extraction")

        # Simulate processing
        for i in range(100):
            metrics.increment_processed()
            if i % 10 == 0:
                metrics.add_error(f"Error {i}")
            else:
                metrics.increment_succeeded()

        # Complete stage
        completed = collector.complete_stage("run_001", "extraction")

        assert completed.records_processed == 100
        assert completed.records_succeeded == 90
        assert completed.records_failed == 10
        assert len(completed.errors) == 10
        assert completed.throughput_records_per_second is not None

        # Persist to disk
        filepath = collector.persist_metrics("run_001", "extraction")

        # Verify file
        assert filepath.exists()

    def test_get_summary(self, tmp_path):
        """Test getting summary for a run."""
        collector = MetricsCollector(output_dir=tmp_path)

        # Create metrics for multiple stages of the same run
        metrics1 = collector.start_stage("run_001", "extraction")
        metrics1.records_processed = 100
        metrics1.complete()

        metrics2 = collector.start_stage("run_001", "loading")
        metrics2.records_processed = 100
        metrics2.complete()

        summary = collector.get_summary("run_001")

        assert summary["run_id"] == "run_001"
        assert summary["stages"] == 2
        assert summary["total_records_processed"] == 200

    def test_get_summary_empty(self, tmp_path):
        """Test getting summary for non-existent run."""
        collector = MetricsCollector(output_dir=tmp_path)

        summary = collector.get_summary("nonexistent")

        assert summary["run_id"] == "nonexistent"
        assert summary["stages"] == 0
        assert summary["total_records"] == 0
