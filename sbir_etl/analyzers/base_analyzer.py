"""Base analyzer class for module-specific statistical analysis."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, ClassVar

from loguru import logger
from pydantic import BaseModel

from sbir_etl.models.quality import ChangesSummary, DataHygieneMetrics, ModuleReport


class AnalysisInsight(BaseModel):
    """Individual analysis insight with context and recommendations."""

    category: str
    title: str
    message: str
    severity: str
    confidence: float
    affected_records: int
    recommendations: list[str]
    metadata: dict[str, Any]


class ModuleAnalyzer(ABC):
    """Base class for module-specific statistical analyzers."""

    stage: ClassVar[str]
    primary_data_key: ClassVar[str]
    total_data_key: ClassVar[str | None] = None
    processing_keys: ClassVar[tuple[str, str, str]]
    duration_data_key: ClassVar[str | None] = None
    analysis_label: ClassVar[str]
    start_analysis_label: ClassVar[str | None] = None
    missing_data_warning: ClassVar[str]
    missing_data_error: ClassVar[str]

    def __init__(self, module_name: str, config: dict[str, Any] | None = None):
        """Initialize the analyzer.

        Args:
            module_name: Name of the module being analyzed
            config: Optional configuration for the analyzer
        """
        self.module_name = module_name
        self.config = config or {}
        self.insights: list[AnalysisInsight] = []

    def analyze(self, module_data: dict[str, Any]) -> ModuleReport:
        """Run the shared analyzer lifecycle around domain-specific calculations.

        Args:
            module_data: Module-specific data to analyze

        Returns:
            ModuleReport with analysis results
        """
        start_label = self.start_analysis_label or self.analysis_label
        logger.info(f"Starting {start_label} analysis")

        primary_data = module_data.get(self.primary_data_key)
        run_context = module_data.get("run_context", {})

        if primary_data is None:
            logger.warning(self.missing_data_warning)
            return self._create_empty_report(run_context)

        key_metrics = self.get_key_metrics(module_data)
        insights = self.generate_insights(module_data)
        data_hygiene = self._calculate_report_data_hygiene(module_data)
        changes_summary = self._calculate_report_changes_summary(module_data)

        total_records = self._get_total_records(module_data)
        records_processed, records_failed, duration_seconds = self._get_processing_metrics(
            module_data, total_records
        )

        report = self.create_module_report(
            run_id=run_context.get("run_id", "unknown"),
            stage=self.stage,
            total_records=total_records,
            records_processed=records_processed,
            records_failed=records_failed,
            duration_seconds=duration_seconds,
            module_metrics=key_metrics,
            data_hygiene=data_hygiene,
            changes_summary=changes_summary,
        )

        logger.info(f"{self.analysis_label} analysis complete: {len(insights)} insights generated")
        return report

    def _get_total_records(self, module_data: dict[str, Any]) -> int:
        """Return the domain's report denominator."""
        total_data = module_data.get(self.total_data_key or self.primary_data_key)
        return len(total_data) if total_data is not None else 0

    def _get_processing_metrics(
        self, module_data: dict[str, Any], total_records: int
    ) -> tuple[int, int, float]:
        """Read shared processing counts while preserving domain-specific keys."""
        results_key, processed_key, failed_key = self.processing_keys
        processing_results = module_data.get(results_key, {})
        duration_results = module_data.get(self.duration_data_key or results_key, {})
        return (
            processing_results.get(processed_key, total_records),
            processing_results.get(failed_key, 0),
            duration_results.get("duration_seconds", 0.0),
        )

    @abstractmethod
    def _calculate_report_data_hygiene(
        self, module_data: dict[str, Any]
    ) -> DataHygieneMetrics | None:
        """Calculate domain-specific hygiene for the shared lifecycle."""

    @abstractmethod
    def _calculate_report_changes_summary(
        self, module_data: dict[str, Any]
    ) -> ChangesSummary | None:
        """Calculate domain-specific changes for the shared lifecycle."""

    def _create_empty_report(self, run_context: dict[str, Any]) -> ModuleReport:
        """Create a standardized report when the primary input is missing."""
        return self.create_module_report(
            run_id=run_context.get("run_id", "unknown"),
            stage=self.stage,
            total_records=0,
            records_processed=0,
            records_failed=0,
            duration_seconds=0.0,
            module_metrics={"error": self.missing_data_error},
        )

    @abstractmethod
    def get_key_metrics(self, module_data: dict[str, Any]) -> dict[str, Any]:
        """Extract key metrics from module data.

        Args:
            module_data: Module-specific data

        Returns:
            Dictionary of key metrics
        """
        pass

    @abstractmethod
    def generate_insights(self, module_data: dict[str, Any]) -> list[AnalysisInsight]:
        """Generate automated insights and recommendations.

        Args:
            module_data: Module-specific data

        Returns:
            List of analysis insights
        """
        pass

    def calculate_success_rate(self, processed: int, total: int) -> float:
        """Calculate success rate with safe division.

        Args:
            processed: Number of successfully processed records
            total: Total number of records

        Returns:
            Success rate as a float between 0.0 and 1.0
        """
        return processed / total if total > 0 else 0.0

    def calculate_coverage_rate(self, enriched: int, total: int) -> float:
        """Calculate coverage rate with safe division.

        Args:
            enriched: Number of enriched records
            total: Total number of records

        Returns:
            Coverage rate as a float between 0.0 and 1.0
        """
        return enriched / total if total > 0 else 0.0

    def add_insight(self, insight: AnalysisInsight) -> None:
        """Add an insight to the analyzer's insight collection.

        Args:
            insight: Analysis insight to add
        """
        self.insights.append(insight)

    def create_module_report(
        self,
        run_id: str,
        stage: str,
        total_records: int,
        records_processed: int,
        records_failed: int,
        duration_seconds: float,
        module_metrics: dict[str, Any],
        data_hygiene: Any | None = None,
        changes_summary: Any | None = None,
    ) -> ModuleReport:
        """Create a standardized module report.

        Args:
            run_id: Pipeline run identifier
            stage: Pipeline stage
            total_records: Total number of records
            records_processed: Successfully processed records
            records_failed: Failed records
            duration_seconds: Processing duration
            module_metrics: Module-specific metrics
            data_hygiene: Optional data hygiene metrics
            changes_summary: Optional changes summary

        Returns:
            ModuleReport instance
        """
        success_rate = self.calculate_success_rate(records_processed, total_records)
        throughput = records_processed / duration_seconds if duration_seconds > 0 else 0.0

        return ModuleReport(
            module_name=self.module_name,
            run_id=run_id,
            timestamp=datetime.now().isoformat(),
            stage=stage,
            total_records=total_records,
            records_processed=records_processed,
            records_failed=records_failed,
            success_rate=success_rate,
            duration_seconds=duration_seconds,
            throughput_records_per_second=throughput,
            data_hygiene=data_hygiene,
            changes_summary=changes_summary,
            module_metrics=module_metrics,
        )

    def detect_anomalies(
        self, current_value: float, expected_value: float, threshold: float = 0.2
    ) -> bool:
        """Detect if a metric value is anomalous compared to expected value.

        Args:
            current_value: Current metric value
            expected_value: Expected or baseline value
            threshold: Threshold for anomaly detection (default 20%)

        Returns:
            True if anomaly detected
        """
        if expected_value == 0:
            return current_value > 0

        deviation = abs(current_value - expected_value) / expected_value
        return deviation > threshold

    def categorize_confidence(self, confidence: float) -> str:
        """Categorize confidence score into human-readable levels.

        Args:
            confidence: Confidence score between 0.0 and 1.0

        Returns:
            Confidence category string
        """
        if confidence >= 0.8:
            return "high"
        elif confidence >= 0.6:
            return "medium"
        else:
            return "low"
