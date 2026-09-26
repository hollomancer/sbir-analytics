"""Tests for quality models."""

import pytest
from pydantic import ValidationError


pytestmark = pytest.mark.fast

from sbir_etl.models.quality import (
    ChangesSummary,
    DataHygieneMetrics,
    InsightRecommendation,
    ModuleReport,
    QualityIssue,
    QualityReport,
    QualitySeverity,
)


# ============================================================================
# Quality Models Tests
# ============================================================================


pytestmark = pytest.mark.fast


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
