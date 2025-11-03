"""Base analyzer class for module-specific statistical analysis."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from src.models.quality import ModuleReport


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

    def __init__(self, module_name: str, config: dict[str, Any] | None = None):
        """Initialize the analyzer.

        Args:
            module_name: Name of the module being analyzed
            config: Optional configuration for the analyzer
        """
        self.module_name = module_name
        self.config = config or {}
        self.insights: list[AnalysisInsight] = []

    @abstractmethod
    def analyze(self, module_data: dict[str, Any]) -> ModuleReport:
        """Analyze module data and generate a comprehensive report.

        Args:
            module_data: Module-specific data to analyze

        Returns:
            ModuleReport with analysis results
        """
        pass

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
