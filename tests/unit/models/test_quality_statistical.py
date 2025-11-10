"""Tests for quality and statistical reporting models."""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
from pydantic import ValidationError

from src.models.quality import (
    QualitySeverity,
    QualityIssue,
    QualityReport,
    InsightRecommendation,
    DataHygieneMetrics,
    ChangesSummary,
    ModuleReport,
)
from src.models.statistical_reports import (
    ReportFormat,
    PerformanceMetrics,
    ModuleMetrics,
    PipelineMetrics,
    ReportArtifact,
    ReportCollection,
)


# ============================================================================
# Quality Models Tests
# ============================================================================


class TestQualitySeverity:
    """Tests for QualitySeverity enum."""

    def test_quality_severity_values(self):
        """Test QualitySeverity enum has correct values."""
        assert QualitySeverity.ERROR == "error"
        assert QualitySeverity.WARNING == "warning"
        assert QualitySeverity.LOW == "low"
        assert QualitySeverity.MEDIUM == "medium"
        assert QualitySeverity.HIGH == "high"
        assert QualitySeverity.CRITICAL == "critical"


class TestQualityIssue:
    """Tests for QualityIssue model."""

    def test_valid_quality_issue(self):
        """Test creating a valid quality issue."""
        issue = QualityIssue(
            field="award_amount",
            value="-1000",
            expected="positive number",
            message="Award amount must be positive",
            severity=QualitySeverity.ERROR,
            rule="positive_amount_check",
            row_index=42,
        )
        assert issue.field == "award_amount"
        assert issue.value == "-1000"
        assert issue.severity == QualitySeverity.ERROR
        assert issue.row_index == 42

    def test_quality_issue_minimal(self):
        """Test quality issue with only required fields."""
        issue = QualityIssue(
            field="company_name",
            message="Missing company name",
            severity=QualitySeverity.WARNING,
        )
        assert issue.field == "company_name"
        assert issue.message == "Missing company name"
        assert issue.value is None
        assert issue.expected is None
        assert issue.rule is None
        assert issue.row_index is None

    def test_quality_issue_all_severities(self):
        """Test quality issue with all severity levels."""
        for severity in QualitySeverity:
            issue = QualityIssue(
                field="test_field",
                message="Test message",
                severity=severity,
            )
            assert issue.severity == severity


class TestQualityReport:
    """Tests for QualityReport model."""

    def test_valid_quality_report(self):
        """Test creating a valid quality report."""
        report = QualityReport(
            record_id="AWARD-001",
            stage="validation",
            timestamp="2023-06-15T10:30:00",
            total_fields=20,
            valid_fields=18,
            invalid_fields=2,
            issues=[
                QualityIssue(
                    field="duns",
                    message="Invalid DUNS format",
                    severity=QualitySeverity.ERROR,
                )
            ],
            completeness_score=0.95,
            validity_score=0.90,
            overall_score=0.92,
            passed=True,
        )
        assert report.record_id == "AWARD-001"
        assert report.total_fields == 20
        assert len(report.issues) == 1
        assert report.passed is True

    def test_quality_report_score_constraints(self):
        """Test quality report score fields have 0-1 constraints."""
        # Valid bounds
        QualityReport(
            record_id="TEST-001",
            stage="test",
            timestamp="2023-01-01T00:00:00",
            total_fields=10,
            valid_fields=5,
            invalid_fields=5,
            completeness_score=0.0,
            validity_score=1.0,
            overall_score=0.5,
            passed=False,
        )

        # Invalid: score > 1.0
        with pytest.raises(ValidationError):
            QualityReport(
                record_id="TEST-002",
                stage="test",
                timestamp="2023-01-01T00:00:00",
                total_fields=10,
                valid_fields=10,
                invalid_fields=0,
                completeness_score=1.5,  # Invalid
                validity_score=1.0,
                overall_score=1.0,
                passed=True,
            )

    def test_quality_report_failed_record(self):
        """Test quality report for a failed record."""
        report = QualityReport(
            record_id="AWARD-002",
            stage="validation",
            timestamp="2023-06-15T11:00:00",
            total_fields=15,
            valid_fields=10,
            invalid_fields=5,
            issues=[
                QualityIssue(
                    field="field1",
                    message="Error 1",
                    severity=QualitySeverity.CRITICAL,
                ),
                QualityIssue(
                    field="field2",
                    message="Error 2",
                    severity=QualitySeverity.HIGH,
                ),
            ],
            completeness_score=0.70,
            validity_score=0.65,
            overall_score=0.67,
            passed=False,
        )
        assert report.passed is False
        assert len(report.issues) == 2


class TestInsightRecommendation:
    """Tests for InsightRecommendation model."""

    def test_valid_insight_recommendation(self):
        """Test creating a valid insight recommendation."""
        insight = InsightRecommendation(
            category="quality",
            priority=QualitySeverity.HIGH,
            title="Low NAICS Coverage",
            message="Only 65% of awards have NAICS codes",
            affected_metrics=["naics_coverage", "enrichment_rate"],
            current_value=0.65,
            expected_value=0.90,
            deviation=-27.8,
            recommendations=[
                "Implement fallback NAICS inference from text",
                "Add USAspending NAICS enrichment",
            ],
        )
        assert insight.category == "quality"
        assert insight.priority == QualitySeverity.HIGH
        assert len(insight.recommendations) == 2

    def test_insight_recommendation_minimal(self):
        """Test insight recommendation with only required fields."""
        insight = InsightRecommendation(
            category="performance",
            priority=QualitySeverity.MEDIUM,
            title="Slow Processing",
            message="Processing time exceeds threshold",
        )
        assert insight.category == "performance"
        assert insight.affected_metrics == []
        assert insight.recommendations == []
        assert insight.current_value is None


class TestDataHygieneMetrics:
    """Tests for DataHygieneMetrics model."""

    def test_valid_data_hygiene_metrics(self):
        """Test creating valid data hygiene metrics."""
        metrics = DataHygieneMetrics(
            total_records=1000,
            clean_records=850,
            dirty_records=150,
            clean_percentage=85.0,
            quality_score_mean=0.88,
            quality_score_median=0.90,
            quality_score_std=0.12,
            quality_score_min=0.45,
            quality_score_max=1.0,
            validation_pass_rate=0.85,
            validation_errors=100,
            validation_warnings=50,
            field_quality_scores={"award_amount": 0.95, "company_name": 0.98},
            field_completeness={"duns": 0.75, "cage": 0.80},
            thresholds_met={"min_quality": True, "min_completeness": False},
        )
        assert metrics.total_records == 1000
        assert metrics.clean_percentage == 85.0
        assert metrics.quality_score_mean == 0.88

    def test_data_hygiene_clean_percentage_constraints(self):
        """Test clean_percentage must be 0-100."""
        # Valid
        DataHygieneMetrics(
            total_records=100,
            clean_records=100,
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
        )

        # Invalid: > 100
        with pytest.raises(ValidationError):
            DataHygieneMetrics(
                total_records=100,
                clean_records=100,
                dirty_records=0,
                clean_percentage=105.0,  # Invalid
                quality_score_mean=1.0,
                quality_score_median=1.0,
                quality_score_std=0.0,
                quality_score_min=1.0,
                quality_score_max=1.0,
                validation_pass_rate=1.0,
                validation_errors=0,
                validation_warnings=0,
            )

    def test_data_hygiene_quality_score_constraints(self):
        """Test quality score fields must be 0-1."""
        with pytest.raises(ValidationError):
            DataHygieneMetrics(
                total_records=100,
                clean_records=50,
                dirty_records=50,
                clean_percentage=50.0,
                quality_score_mean=1.5,  # Invalid
                quality_score_median=0.5,
                quality_score_std=0.2,
                quality_score_min=0.0,
                quality_score_max=1.0,
                validation_pass_rate=0.5,
                validation_errors=50,
                validation_warnings=25,
            )


class TestChangesSummary:
    """Tests for ChangesSummary model."""

    def test_valid_changes_summary(self):
        """Test creating a valid changes summary."""
        summary = ChangesSummary(
            total_records=1000,
            records_modified=600,
            records_unchanged=400,
            modification_rate=0.60,
            fields_added=["naics_code", "bea_sector"],
            fields_modified=["award_amount", "company_address"],
            fields_removed=["deprecated_field"],
            field_modification_counts={"award_amount": 250, "company_address": 350},
            enrichment_coverage={"naics_enriched": 0.65, "geo_enriched": 0.90},
            enrichment_sources={"usaspending": 400, "sam_gov": 200},
            sample_changes=[
                {"before": {"amount": 100}, "after": {"amount": 110}},
            ],
        )
        assert summary.total_records == 1000
        assert summary.modification_rate == 0.60
        assert len(summary.fields_added) == 2

    def test_changes_summary_minimal(self):
        """Test changes summary with only required fields."""
        summary = ChangesSummary(
            total_records=500,
            records_modified=100,
            records_unchanged=400,
            modification_rate=0.20,
        )
        assert summary.fields_added == []
        assert summary.fields_modified == []
        assert summary.enrichment_coverage == {}

    def test_modification_rate_constraints(self):
        """Test modification_rate must be 0-1."""
        with pytest.raises(ValidationError):
            ChangesSummary(
                total_records=100,
                records_modified=150,
                records_unchanged=0,
                modification_rate=1.5,  # Invalid
            )


class TestModuleReport:
    """Tests for ModuleReport base model."""

    def test_valid_module_report(self):
        """Test creating a valid module report."""
        report = ModuleReport(
            module_name="sbir",
            run_id="RUN-001",
            timestamp="2023-06-15T12:00:00",
            stage="extract",
            total_records=1000,
            records_processed=980,
            records_failed=20,
            success_rate=0.98,
            duration_seconds=120.5,
            throughput_records_per_second=8.13,
        )
        assert report.module_name == "sbir"
        assert report.success_rate == 0.98
        assert report.duration_seconds == 120.5

    def test_module_report_with_hygiene_metrics(self):
        """Test module report with data hygiene metrics."""
        hygiene = DataHygieneMetrics(
            total_records=100,
            clean_records=90,
            dirty_records=10,
            clean_percentage=90.0,
            quality_score_mean=0.92,
            quality_score_median=0.95,
            quality_score_std=0.08,
            quality_score_min=0.70,
            quality_score_max=1.0,
            validation_pass_rate=0.90,
            validation_errors=10,
            validation_warnings=5,
        )
        report = ModuleReport(
            module_name="patent",
            run_id="RUN-002",
            timestamp="2023-06-15T13:00:00",
            stage="validate",
            total_records=100,
            records_processed=90,
            records_failed=10,
            success_rate=0.90,
            duration_seconds=30.0,
            throughput_records_per_second=3.0,
            data_hygiene=hygiene,
        )
        assert report.data_hygiene is not None
        assert report.data_hygiene.clean_percentage == 90.0


# ============================================================================
# Statistical Reports Models Tests
# ============================================================================


class TestReportFormat:
    """Tests for ReportFormat enum."""

    def test_report_format_values(self):
        """Test ReportFormat enum has correct values."""
        assert ReportFormat.HTML == "html"
        assert ReportFormat.JSON == "json"
        assert ReportFormat.MARKDOWN == "markdown"
        assert ReportFormat.EXECUTIVE == "executive"


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics model."""

    def test_valid_performance_metrics(self):
        """Test creating valid performance metrics."""
        start = datetime(2023, 6, 15, 10, 0, 0)
        end = datetime(2023, 6, 15, 10, 30, 0)
        duration = end - start

        metrics = PerformanceMetrics(
            start_time=start,
            end_time=end,
            duration=duration,
            records_per_second=50.5,
            peak_memory_mb=512.0,
            average_memory_mb=384.0,
            cpu_usage_percent=75.5,
            disk_io_mb=1024.0,
            total_retries=5,
            failed_operations=2,
        )
        assert metrics.start_time == start
        assert metrics.duration == timedelta(minutes=30)
        assert metrics.records_per_second == 50.5

    def test_performance_metrics_minimal(self):
        """Test performance metrics with only required fields."""
        start = datetime.now()
        end = start + timedelta(seconds=120)

        metrics = PerformanceMetrics(
            start_time=start,
            end_time=end,
            duration=timedelta(seconds=120),
            records_per_second=10.0,
            peak_memory_mb=256.0,
            average_memory_mb=200.0,
        )
        assert metrics.total_retries == 0
        assert metrics.failed_operations == 0
        assert metrics.cpu_usage_percent is None


class TestModuleMetrics:
    """Tests for ModuleMetrics model."""

    def test_valid_module_metrics(self):
        """Test creating valid module metrics."""
        start = datetime(2023, 6, 15, 10, 0, 0)
        end = datetime(2023, 6, 15, 10, 5, 0)
        duration = end - start

        metrics = ModuleMetrics(
            module_name="sbir_extractor",
            stage="extract",
            execution_time=duration,
            start_time=start,
            end_time=end,
            records_in=1000,
            records_out=980,
            records_processed=980,
            records_failed=20,
            success_rate=0.98,
            throughput_records_per_second=3.27,
            quality_metrics={"completeness": 0.95, "validity": 0.92},
            enrichment_coverage=0.85,
            match_rates={"exact": 0.70, "fuzzy": 0.15},
            peak_memory_mb=128.0,
            average_cpu_percent=45.5,
            module_specific_metrics={"custom_metric": 42},
        )
        assert metrics.module_name == "sbir_extractor"
        assert metrics.success_rate == 0.98
        assert metrics.enrichment_coverage == 0.85

    def test_module_metrics_success_rate_constraints(self):
        """Test module metrics success_rate must be 0-1."""
        start = datetime.now()
        end = start + timedelta(seconds=60)

        with pytest.raises(ValidationError):
            ModuleMetrics(
                module_name="test",
                stage="test",
                execution_time=timedelta(seconds=60),
                start_time=start,
                end_time=end,
                records_in=100,
                records_out=100,
                records_processed=100,
                records_failed=0,
                success_rate=1.5,  # Invalid
                throughput_records_per_second=1.67,
            )


class TestPipelineMetrics:
    """Tests for PipelineMetrics model."""

    def test_valid_pipeline_metrics(self):
        """Test creating valid pipeline metrics."""
        now = datetime.now()
        start = now - timedelta(hours=1)
        end = now

        perf = PerformanceMetrics(
            start_time=start,
            end_time=end,
            duration=timedelta(hours=1),
            records_per_second=100.0,
            peak_memory_mb=1024.0,
            average_memory_mb=768.0,
        )

        metrics = PipelineMetrics(
            run_id="RUN-123",
            pipeline_name="sbir-etl",
            environment="production",
            timestamp=now,
            duration=timedelta(hours=1),
            total_records_processed=360000,
            overall_success_rate=0.95,
            quality_scores={"overall": 0.90, "completeness": 0.88},
            performance_metrics=perf,
            data_coverage_metrics={"sbir": 0.92, "patents": 0.85},
        )
        assert metrics.run_id == "RUN-123"
        assert metrics.overall_success_rate == 0.95

    def test_pipeline_metrics_defaults(self):
        """Test pipeline metrics with default values."""
        now = datetime.now()
        perf = PerformanceMetrics(
            start_time=now,
            end_time=now,
            duration=timedelta(0),
            records_per_second=0.0,
            peak_memory_mb=0.0,
            average_memory_mb=0.0,
        )

        metrics = PipelineMetrics(
            run_id="RUN-456",
            timestamp=now,
            duration=timedelta(minutes=30),
            total_records_processed=1000,
            overall_success_rate=1.0,
            performance_metrics=perf,
        )
        assert metrics.pipeline_name == "sbir-etl"
        assert metrics.environment == "development"


class TestReportArtifact:
    """Tests for ReportArtifact model."""

    def test_valid_report_artifact(self):
        """Test creating a valid report artifact."""
        artifact = ReportArtifact(
            format=ReportFormat.HTML,
            file_path=Path("/reports/run-123/report.html"),
            file_size_bytes=51200,
            generated_at=datetime.now(),
            generation_duration_seconds=5.5,
            contains_interactive_elements=True,
            contains_visualizations=True,
            is_public_safe=True,
            requires_authentication=False,
        )
        assert artifact.format == ReportFormat.HTML
        assert artifact.file_size_bytes == 51200
        assert artifact.contains_interactive_elements is True

    def test_report_artifact_defaults(self):
        """Test report artifact with default values."""
        artifact = ReportArtifact(
            format=ReportFormat.JSON,
            file_path=Path("/reports/data.json"),
            file_size_bytes=1024,
            generated_at=datetime.now(),
            generation_duration_seconds=1.0,
        )
        assert artifact.contains_interactive_elements is False
        assert artifact.contains_visualizations is False
        assert artifact.is_public_safe is True
        assert artifact.requires_authentication is False


class TestReportCollection:
    """Tests for ReportCollection model."""

    def test_valid_report_collection(self):
        """Test creating a valid report collection."""
        now = datetime.now()
        artifacts = [
            ReportArtifact(
                format=ReportFormat.HTML,
                file_path=Path("/reports/report.html"),
                file_size_bytes=10240,
                generated_at=now,
                generation_duration_seconds=3.0,
            ),
            ReportArtifact(
                format=ReportFormat.JSON,
                file_path=Path("/reports/report.json"),
                file_size_bytes=2048,
                generated_at=now,
                generation_duration_seconds=1.0,
            ),
        ]

        collection = ReportCollection(
            collection_id="COLL-001",
            run_id="RUN-001",
            generated_at=now,
            artifacts=artifacts,
        )
        assert collection.collection_id == "COLL-001"
        assert len(collection.artifacts) == 2

    def test_report_collection_empty_artifacts(self):
        """Test report collection with no artifacts."""
        collection = ReportCollection(
            collection_id="COLL-002",
            run_id="RUN-002",
            generated_at=datetime.now(),
        )
        assert collection.artifacts == []
