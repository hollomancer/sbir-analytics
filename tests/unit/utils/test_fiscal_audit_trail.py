"""Unit tests for fiscal audit trail."""

import json

import pytest

pytestmark = pytest.mark.fast

from src.utils.fiscal_audit_trail import FiscalAuditTrail, create_audit_trail


@pytest.fixture
def audit_trail():
    """Create a FiscalAuditTrail instance."""
    return FiscalAuditTrail(analysis_id="test_analysis_001")


class TestFiscalAuditTrail:
    """Test FiscalAuditTrail class."""

    def test_initialization(self, audit_trail):
        """Test audit trail initialization."""
        assert audit_trail.analysis_id == "test_analysis_001"
        assert "analysis_started_at" in audit_trail.audit_log
        assert "base_year" in audit_trail.audit_log

    def test_log_configuration(self, audit_trail):
        """Test configuration logging."""
        audit_trail.log_configuration()

        assert "configuration" in audit_trail.audit_log
        assert "base_year" in audit_trail.audit_log["configuration"]
        assert "tax_parameters" in audit_trail.audit_log["configuration"]

    def test_log_transformation(self, audit_trail):
        """Test transformation logging."""
        audit_trail.log_transformation(
            step_name="NAICS_enrichment",
            input_count=100,
            output_count=95,
            parameters={"method": "usaspending_lookup"},
            quality_metrics={"coverage_rate": 0.95},
        )

        assert len(audit_trail.audit_log["transformations"]) == 1
        transformation = audit_trail.audit_log["transformations"][0]
        assert transformation["step_name"] == "NAICS_enrichment"
        assert transformation["input_count"] == 100
        assert transformation["output_count"] == 95

    def test_log_assumption(self, audit_trail):
        """Test assumption logging."""
        audit_trail.log_assumption(
            assumption_type="tax_rate",
            description="Using 22% effective income tax rate",
            rationale="Based on IRS statistics",
            impact="Moderate - affects all income tax estimates",
        )

        assert len(audit_trail.audit_log["assumptions"]) == 1
        assumption = audit_trail.audit_log["assumptions"][0]
        assert assumption["assumption_type"] == "tax_rate"
        assert assumption["description"] == "Using 22% effective income tax rate"

    def test_track_lineage(self, audit_trail):
        """Test data lineage tracking."""
        audit_trail.track_lineage(
            award_id="AWARD-001",
            transformation_step="economic_shock_aggregation",
            output_id="SHOCK-CA-11-2023",
        )

        assert "AWARD-001" in audit_trail.lineage
        assert len(audit_trail.lineage["AWARD-001"]) == 1
        assert audit_trail.lineage["AWARD-001"][0]["step"] == "economic_shock_aggregation"

    def test_log_quality_metrics(self, audit_trail):
        """Test quality metrics logging."""
        audit_trail.log_quality_metrics(
            "inflation_adjustment", {"success_rate": 0.98, "avg_confidence": 0.95}
        )

        assert "inflation_adjustment" in audit_trail.audit_log["quality_metrics"]
        assert (
            audit_trail.audit_log["quality_metrics"]["inflation_adjustment"]["success_rate"] == 0.98
        )

    def test_finalize_audit_log(self, audit_trail):
        """Test audit log finalization."""
        audit_trail.log_transformation("test_step", 10, 10)
        audit_trail.track_lineage("AWARD-001", "test_step")

        log = audit_trail.finalize_audit_log()

        assert "analysis_completed_at" in log
        assert "data_lineage" in log
        assert "total_transformations" in log
        assert log["total_transformations"] == 1

    def test_save_audit_log(self, audit_trail, tmp_path):
        """Test audit log saving."""
        audit_trail.log_transformation("test_step", 10, 10)
        output_path = tmp_path / "audit_trail.json"

        saved_path = audit_trail.save_audit_log(output_path)

        assert saved_path.exists()
        assert saved_path == output_path

        # Verify JSON is valid
        with output_path.open() as f:
            log_data = json.load(f)
            assert log_data["analysis_id"] == "test_analysis_001"

    def test_get_audit_summary(self, audit_trail):
        """Test audit summary generation."""
        audit_trail.log_transformation("step1", 10, 10)
        audit_trail.log_assumption("tax_rate", "Test assumption")
        audit_trail.track_lineage("AWARD-001", "step1")

        summary = audit_trail.get_audit_summary()

        assert summary["analysis_id"] == "test_analysis_001"
        assert summary["total_transformations"] == 1
        assert summary["total_assumptions"] == 1
        assert summary["awards_tracked"] == 1


def test_create_audit_trail():
    """Test audit trail factory function."""
    trail = create_audit_trail(analysis_id="factory_test")

    assert trail.analysis_id == "factory_test"
    assert "configuration" in trail.audit_log
    assert len(trail.audit_log["configuration"]) > 0  # Should have logged config
