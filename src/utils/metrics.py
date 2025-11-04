"""Metrics collection and tracking for ETL pipeline operations."""

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from ..exceptions import ValidationError


@dataclass
class PipelineMetrics:
    """Metrics for a complete pipeline execution."""

    run_id: str
    stage: str
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None
    duration_seconds: float | None = None
    records_processed: int = 0
    records_failed: int = 0
    records_succeeded: int = 0
    throughput_records_per_second: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def complete(self) -> None:
        """Mark the metrics collection as complete and calculate final values."""
        self.end_time = time.time()
        self.duration_seconds = self.end_time - self.start_time

        if self.duration_seconds > 0 and self.records_processed > 0:
            self.throughput_records_per_second = self.records_processed / self.duration_seconds

        # Prepare throughput display safely (avoid formatting None)
        if self.throughput_records_per_second is None:
            throughput_display = "N/A"
        else:
            throughput_display = f"{self.throughput_records_per_second:.2f} records/sec"

        logger.info(
            f"Pipeline stage '{self.stage}' completed: "
            f"{self.records_processed} records in {self.duration_seconds:.2f}s "
            f"({throughput_display})"
        )

    def add_error(self, error_message: str) -> None:
        """Add an error message to the metrics.

        Args:
            error_message: Description of the error
        """
        self.errors.append(error_message)
        self.records_failed += 1
        logger.error(f"Error in {self.stage}: {error_message}")

    def increment_processed(self, count: int = 1) -> None:
        """Increment the number of records processed.

        Args:
            count: Number of records to add (default: 1)
        """
        self.records_processed += count

    def increment_succeeded(self, count: int = 1) -> None:
        """Increment the number of successfully processed records.

        Args:
            count: Number of records to add (default: 1)
        """
        self.records_succeeded += count

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary.

        Returns:
            Dictionary representation of metrics
        """
        return asdict(self)


class MetricsCollector:
    """Collector for pipeline metrics with persistence support."""

    def __init__(self, output_dir: Path | None = None) -> None:
        """Initialize metrics collector.

        Args:
            output_dir: Directory for persisting metrics (default: ./metrics)
        """
        self.output_dir = output_dir or Path("./metrics")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.metrics: dict[str, PipelineMetrics] = {}
        logger.info(f"Metrics collector initialized with output dir: {self.output_dir}")

    def start_stage(
        self, run_id: str, stage: str, metadata: dict[str, Any] | None = None
    ) -> PipelineMetrics:
        """Start tracking metrics for a pipeline stage.

        Args:
            run_id: Unique identifier for this pipeline run
            stage: Name of the pipeline stage
            metadata: Optional metadata to attach to metrics

        Returns:
            PipelineMetrics instance for this stage
        """
        key = f"{run_id}:{stage}"

        if key in self.metrics:
            logger.warning(f"Metrics already exist for {key}, overwriting")

        metrics = PipelineMetrics(
            run_id=run_id,
            stage=stage,
            metadata=metadata or {},
        )

        self.metrics[key] = metrics
        logger.info(f"Started metrics collection for {key}")

        return metrics

    def complete_stage(self, run_id: str, stage: str) -> PipelineMetrics | None:
        """Complete metrics tracking for a pipeline stage.

        Args:
            run_id: Pipeline run identifier
            stage: Pipeline stage name

        Returns:
            Completed PipelineMetrics instance, or None if not found
        """
        key = f"{run_id}:{stage}"
        metrics = self.metrics.get(key)

        if metrics is None:
            logger.warning(f"No metrics found for {key}")
            return None

        metrics.complete()
        return metrics

    def get_metrics(self, run_id: str, stage: str) -> PipelineMetrics | None:
        """Retrieve metrics for a specific stage.

        Args:
            run_id: Pipeline run identifier
            stage: Pipeline stage name

        Returns:
            PipelineMetrics instance, or None if not found
        """
        key = f"{run_id}:{stage}"
        return self.metrics.get(key)

    def persist_metrics(self, run_id: str, stage: str) -> Path:
        """Persist metrics to a JSON file.

        Args:
            run_id: Pipeline run identifier
            stage: Pipeline stage name

        Returns:
            Path to the persisted metrics file

        Raises:
            ValueError: If metrics not found for the specified run_id and stage
        """
        key = f"{run_id}:{stage}"
        metrics = self.metrics.get(key)

        if metrics is None:
            raise ValidationError(
                f"No metrics found for {key}",
                component="utils.metrics",
                operation="export_to_json",
                details={"run_id": run_id, "stage": stage, "available_keys": list(self.metrics.keys())},
            )

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{run_id}_{stage}_{timestamp}.json"
        filepath = self.output_dir / filename

        with open(filepath, "w") as f:
            json.dump(metrics.to_dict(), f, indent=2)

        logger.info(f"Persisted metrics to {filepath}")
        return filepath

    def persist_all_metrics(self, run_id: str) -> list[Path]:
        """Persist all metrics for a given run_id.

        Args:
            run_id: Pipeline run identifier

        Returns:
            List of paths to persisted metrics files
        """
        filepaths = []

        for metrics in self.metrics.values():
            if metrics.run_id == run_id:
                stage = metrics.stage
                filepath = self.persist_metrics(run_id, stage)
                filepaths.append(filepath)

        logger.info(f"Persisted {len(filepaths)} metrics files for run {run_id}")
        return filepaths

    def get_summary(self, run_id: str) -> dict[str, Any]:
        """Get a summary of all metrics for a pipeline run.

        Args:
            run_id: Pipeline run identifier

        Returns:
            Dictionary containing aggregated metrics
        """
        run_metrics = [m for m in self.metrics.values() if m.run_id == run_id]

        if not run_metrics:
            return {"run_id": run_id, "stages": 0, "total_records": 0}

        total_records = sum(m.records_processed for m in run_metrics)
        total_failed = sum(m.records_failed for m in run_metrics)
        total_succeeded = sum(m.records_succeeded for m in run_metrics)
        total_duration = sum(m.duration_seconds or 0 for m in run_metrics)

        summary = {
            "run_id": run_id,
            "stages": len(run_metrics),
            "total_records_processed": total_records,
            "total_records_failed": total_failed,
            "total_records_succeeded": total_succeeded,
            "total_duration_seconds": total_duration,
            "stages_detail": [
                {
                    "stage": m.stage,
                    "records": m.records_processed,
                    "duration": m.duration_seconds,
                    "errors": len(m.errors),
                }
                for m in run_metrics
            ],
        }

        return summary
