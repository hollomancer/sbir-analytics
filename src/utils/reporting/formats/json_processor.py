"""JSON report processor for machine-readable statistical reports.

This processor generates JSON reports with complete PipelineMetrics data
for programmatic consumption, automation, and integration with other tools.
"""

import json
import time
from pathlib import Path
from typing import Any

from src.exceptions import ValidationError
from src.models.statistical_reports import PipelineMetrics, ReportArtifact, ReportFormat
from src.utils.reporting.formats.base import BaseReportProcessor


class JsonReportProcessor(BaseReportProcessor):
    """JSON report processor for machine-readable statistical reports.

    Generates comprehensive JSON reports containing all PipelineMetrics data
    with proper serialization and optional schema validation.
    """

    def __init__(self, format_type: ReportFormat):
        """Initialize the JSON processor."""
        super().__init__(format_type)

    def generate(
        self,
        pipeline_metrics: PipelineMetrics,
        output_dir: Path,
        validate_schema: bool = False,
        **kwargs: Any,
    ) -> ReportArtifact:
        """Generate JSON report with complete pipeline metrics.

        Args:
            pipeline_metrics: Pipeline statistics and metrics
            output_dir: Directory where the report file should be written
            validate_schema: Whether to validate JSON against schema (optional)
            **kwargs: Additional options (currently unused)

        Returns:
            ReportArtifact describing the generated JSON report
        """
        start_time = time.time()
        output_path = self._create_output_path(pipeline_metrics, output_dir)
        self._ensure_output_directory(output_path)

        # Serialize pipeline metrics to JSON
        json_data = self._serialize_pipeline_metrics(pipeline_metrics)

        # Optional schema validation
        if validate_schema:
            self._validate_json_schema(json_data)

        # Convert to formatted JSON string
        json_content = json.dumps(json_data, indent=2, default=self._json_serializer)

        # Write file and collect metadata
        file_size, write_duration = self._write_file_with_metadata(json_content, output_path)
        generation_duration = time.time() - start_time

        # Create artifact
        artifact = ReportArtifact(
            format=self.format_type,
            file_path=output_path,
            file_size_bytes=file_size,
            generated_at=pipeline_metrics.timestamp,
            generation_duration_seconds=generation_duration,
            contains_interactive_elements=False,
            contains_visualizations=False,
            is_public_safe=True,
            requires_authentication=False,
        )

        return artifact

    def _serialize_pipeline_metrics(self, pipeline_metrics: PipelineMetrics) -> dict[str, Any]:
        """Serialize PipelineMetrics to a dictionary suitable for JSON.

        Args:
            pipeline_metrics: Pipeline metrics to serialize

        Returns:
            Dictionary representation suitable for JSON serialization
        """
        # Convert to dict and handle datetime/timedelta serialization
        data = pipeline_metrics.model_dump()

        # Ensure proper serialization of complex types
        data["timestamp"] = pipeline_metrics.timestamp.isoformat()
        data["duration"] = {
            "seconds": pipeline_metrics.duration.total_seconds(),
            "human_readable": str(pipeline_metrics.duration),
        }

        # Handle performance metrics
        if pipeline_metrics.performance_metrics:
            perf_data = data["performance_metrics"]
            perf_data["start_time"] = pipeline_metrics.performance_metrics.start_time.isoformat()
            perf_data["end_time"] = pipeline_metrics.performance_metrics.end_time.isoformat()
            perf_data["duration"] = {
                "seconds": pipeline_metrics.performance_metrics.duration.total_seconds(),
                "human_readable": str(pipeline_metrics.performance_metrics.duration),
            }

        # Handle module metrics
        if pipeline_metrics.module_metrics:
            for module_name, module in data["module_metrics"].items():
                if "execution_time" in module:
                    module["execution_time_seconds"] = module["execution_time"]
                    module["execution_time"] = str(
                        pipeline_metrics.module_metrics[module_name].execution_time
                    )
                if "start_time" in module:
                    module["start_time"] = pipeline_metrics.module_metrics[
                        module_name
                    ].start_time.isoformat()
                if "end_time" in module:
                    module["end_time"] = pipeline_metrics.module_metrics[
                        module_name
                    ].end_time.isoformat()

        # Add metadata
        data["_metadata"] = {
            "generated_by": "sbir-analytics statistical reporter",
            "version": "1.0",
            "format": "pipeline_metrics_json",
            "schema_version": "1.0",
        }

        return data

    def _json_serializer(self, obj: Any) -> Any:
        """Custom JSON serializer for objects that aren't natively serializable.

        Args:
            obj: Object to serialize

        Returns:
            JSON-serializable representation

        Raises:
            TypeError: If object cannot be serialized
        """
        # Handle Path objects
        if isinstance(obj, Path):
            return str(obj)

        # Handle set objects
        if isinstance(obj, set):
            return list(obj)

        # Handle bytes objects
        if isinstance(obj, bytes):
            return obj.decode("utf-8", errors="replace")

        # Handle other complex objects by converting to string
        if hasattr(obj, "__str__"):
            try:
                return str(obj)
            except (NotImplementedError, Exception):
                # If __str__ fails, raise ValidationError
                raise ValidationError(
                    f"Object of type {type(obj)} is not JSON serializable (__str__ raised exception)",
                    component="json_processor",
                    operation="serialize",
                )

        # Use ValidationError since this is about validating JSON serializability
        raise ValidationError(
            f"Object of type {type(obj)} is not JSON serializable",
            component="utils.json_processor",
            operation="_json_serial",
            details={"object_type": str(type(obj)), "object_repr": repr(obj)[:100]},
        )

    # Expected schema for pipeline metrics JSON output.
    # Maps field name -> (required, expected_type_or_None).
    _SCHEMA: dict[str, tuple[bool, type | None]] = {
        "run_id": (True, str),
        "timestamp": (True, str),
        "total_records_processed": (True, (int, float)),
        "status": (False, str),
        "duration": (False, dict),
        "performance_metrics": (False, (dict, type(None))),
        "module_metrics": (False, (dict, type(None))),
        "data_quality_summary": (False, (dict, type(None))),
        "errors": (False, (list, type(None))),
        "warnings": (False, (list, type(None))),
    }

    def _validate_json_schema(self, json_data: dict[str, Any]) -> None:
        """Validate JSON data against the expected pipeline metrics schema.

        Checks required field presence and type correctness for all known fields.
        Logs warnings for unexpected types rather than raising, to avoid breaking
        backward compatibility on optional fields.

        Args:
            json_data: JSON data to validate

        Raises:
            ValidationError: If required fields are missing or have wrong types
        """
        errors: list[str] = []

        for field_name, (required, expected_type) in self._SCHEMA.items():
            if field_name not in json_data:
                if required:
                    errors.append(f"Required field '{field_name}' missing")
                continue

            if expected_type is not None:
                value = json_data[field_name]
                if not isinstance(value, expected_type):
                    msg = (
                        f"Field '{field_name}' has type {type(value).__name__}, "
                        f"expected {expected_type}"
                    )
                    if required:
                        errors.append(msg)
                    else:
                        from loguru import logger

                        logger.warning(f"JSON schema warning: {msg}")

        if errors:
            raise ValidationError(
                f"JSON schema validation failed: {'; '.join(errors)}",
                component="utils.json_processor",
                operation="_validate_json_schema",
                details={
                    "errors": errors,
                    "available_fields": list(json_data.keys()),
                },
            )

    def _get_interactive_flag(self) -> bool:
        """JSON reports are not interactive."""
        return False

    def _get_visualization_flag(self) -> bool:
        """JSON reports do not contain visualizations."""
        return False
