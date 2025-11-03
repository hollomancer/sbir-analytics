"""Tests for the E2E pipeline validator.

This module tests the pipeline validator functionality to ensure
comprehensive validation of ETL pipeline stages.
"""

from unittest.mock import Mock

import pandas as pd

from src.models.quality import QualitySeverity
from tests.e2e.pipeline_validator import (
    PipelineValidator,
    ValidationCheck,
    ValidationStage,
    ValidationStatus,
)
from tests.e2e.validation_models import (
    RecommendationPriority,
    TestReport,
    TestScenario,
    ValidationReporter,
    ValidationResult,
)


class TestPipelineValidator:
    """Test cases for PipelineValidator."""

    def test_validate_extraction_stage_success(self):
        """Test successful extraction stage validation."""
        validator = PipelineValidator()

        # Create test data
        test_data = pd.DataFrame(
            {
                "Company": ["Acme Inc", "TechCorp"],
                "UEI": ["UEI001", "UEI002"],
                "Contract": ["C001", "C002"],
            }
        )

        result = validator.validate_extraction_stage(
            raw_data=test_data, expected_columns=["Company", "UEI", "Contract"], min_records=1
        )

        assert result.stage == ValidationStage.EXTRACTION
        assert result.status == ValidationStatus.PASSED
        assert len(result.checks) >= 2  # At least record count and column checks
        assert result.metadata["record_count"] == 2
        assert result.metadata["column_count"] == 3

    def test_validate_extraction_stage_missing_columns(self):
        """Test extraction validation with missing required columns."""
        validator = PipelineValidator()

        test_data = pd.DataFrame({"Company": ["Acme Inc"], "UEI": ["UEI001"]})

        result = validator.validate_extraction_stage(
            raw_data=test_data,
            expected_columns=["Company", "UEI", "Contract"],  # Contract missing
            min_records=1,
        )

        assert result.stage == ValidationStage.EXTRACTION
        assert result.status == ValidationStatus.FAILED

        # Find the failed column check
        column_check = next((c for c in result.checks if c.name == "required_columns"), None)
        assert column_check is not None
        assert column_check.status == ValidationStatus.FAILED
        assert "Contract" in column_check.message

    def test_validate_extraction_stage_insufficient_records(self):
        """Test extraction validation with insufficient records."""
        validator = PipelineValidator()

        test_data = pd.DataFrame({"Company": ["Acme Inc"], "UEI": ["UEI001"]})

        result = validator.validate_extraction_stage(
            raw_data=test_data,
            min_records=5,  # Require 5 records but only have 1
        )

        assert result.status == ValidationStatus.FAILED

        record_check = next((c for c in result.checks if c.name == "minimum_record_count"), None)
        assert record_check is not None
        assert record_check.status == ValidationStatus.FAILED
        assert record_check.severity == QualitySeverity.CRITICAL

    def test_validate_enrichment_stage_success(self):
        """Test successful enrichment stage validation."""
        validator = PipelineValidator()

        # Original data
        original_data = pd.DataFrame(
            {"Company": ["Acme Inc", "TechCorp"], "UEI": ["UEI001", "UEI002"]}
        )

        # Enriched data with match columns
        enriched_data = pd.DataFrame(
            {
                "Company": ["Acme Inc", "TechCorp"],
                "UEI": ["UEI001", "UEI002"],
                "_usaspending_match_method": ["exact", "fuzzy"],
                "_usaspending_match_score": [1.0, 0.85],
            }
        )

        result = validator.validate_enrichment_stage(
            enriched_data=enriched_data,
            original_data=original_data,
            min_match_rate=0.7,
            expected_enrichment_columns=["_usaspending_match_method", "_usaspending_match_score"],
        )

        assert result.stage == ValidationStage.ENRICHMENT
        assert result.status == ValidationStatus.PASSED
        assert result.metadata["match_rate"] == 1.0  # Both records matched

    def test_validate_enrichment_stage_low_match_rate(self):
        """Test enrichment validation with low match rate."""
        validator = PipelineValidator()

        original_data = pd.DataFrame(
            {
                "Company": ["Acme Inc", "TechCorp", "StartupCo"],
                "UEI": ["UEI001", "UEI002", "UEI003"],
            }
        )

        # Only 1 out of 3 records matched
        enriched_data = pd.DataFrame(
            {
                "Company": ["Acme Inc", "TechCorp", "StartupCo"],
                "UEI": ["UEI001", "UEI002", "UEI003"],
                "_usaspending_match_method": ["exact", None, None],
                "_usaspending_match_score": [1.0, None, None],
            }
        )

        result = validator.validate_enrichment_stage(
            enriched_data=enriched_data,
            original_data=original_data,
            min_match_rate=0.7,  # Require 70% but only have 33%
        )

        assert result.status == ValidationStatus.FAILED

        match_rate_check = next((c for c in result.checks if c.name == "match_rate"), None)
        assert match_rate_check is not None
        assert match_rate_check.status == ValidationStatus.FAILED
        assert match_rate_check.actual < 0.7

    def test_validate_neo4j_graph_success(self):
        """Test successful Neo4j graph validation."""
        # Mock Neo4j client
        mock_client = Mock()
        mock_session = Mock()

        # Properly mock the context manager
        mock_client.session.return_value = mock_session
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=None)

        # Create a list to track call order
        call_results = []

        def mock_run(query, **kwargs):
            """Mock run method that returns appropriate results based on query."""
            result = Mock()

            if "isolated_count" in query:
                # Connectivity query - check this first since it also contains "count(n)"
                result.single.return_value = {"isolated_count": 0}
                call_results.append("connectivity")
            elif "count(n)" in query:
                # Node count query
                result.single.return_value = {"count": 100}
                call_results.append("node_count")
            elif "count(r)" in query:
                # Relationship count query
                result.single.return_value = {"count": 50}
                call_results.append("rel_count")
            elif "db.labels()" in query:
                # Node types query
                result.__iter__ = Mock(
                    return_value=iter([{"label": "Company"}, {"label": "Award"}])
                )
                call_results.append("node_types")
            elif "db.relationshipTypes()" in query:
                # Relationship types query
                result.__iter__ = Mock(return_value=iter([{"relationshipType": "RECEIVED"}]))
                call_results.append("rel_types")

            return result

        mock_session.run.side_effect = mock_run

        validator = PipelineValidator(neo4j_client=mock_client)

        result = validator.validate_neo4j_graph(
            expected_node_types=["Company", "Award"],
            expected_relationships=["RECEIVED"],
            min_nodes=10,
            min_relationships=5,
        )

        assert result.stage == ValidationStage.LOADING
        assert result.status == ValidationStatus.PASSED
        assert result.metadata["node_count"] == 100
        assert result.metadata["relationship_count"] == 50

    def test_validate_neo4j_graph_no_client(self):
        """Test Neo4j validation when no client is provided."""
        validator = PipelineValidator()  # No Neo4j client

        result = validator.validate_neo4j_graph()

        assert result.stage == ValidationStage.LOADING
        assert result.status == ValidationStatus.SKIPPED
        assert len(result.checks) == 1
        assert result.checks[0].name == "neo4j_client"

    def test_validate_neo4j_graph_connection_failure(self):
        """Test Neo4j validation with connection failure."""
        mock_client = Mock()
        mock_client.session.side_effect = Exception("Connection failed")

        validator = PipelineValidator(neo4j_client=mock_client)

        result = validator.validate_neo4j_graph()

        assert result.status == ValidationStatus.FAILED

        connection_check = next((c for c in result.checks if c.name == "neo4j_connection"), None)
        assert connection_check is not None
        assert connection_check.status == ValidationStatus.FAILED
        assert connection_check.severity == QualitySeverity.CRITICAL


class TestValidationModels:
    """Test cases for validation data models."""

    def test_validation_result_properties(self):
        """Test ValidationResult property methods."""
        from tests.e2e.pipeline_validator import StageValidationResult

        # Create test stage results
        passed_stage = StageValidationResult(
            stage=ValidationStage.EXTRACTION,
            status=ValidationStatus.PASSED,
            duration_seconds=1.0,
            checks=[
                ValidationCheck(
                    name="test_check", status=ValidationStatus.PASSED, message="Test passed"
                )
            ],
        )

        failed_stage = StageValidationResult(
            stage=ValidationStage.ENRICHMENT,
            status=ValidationStatus.FAILED,
            duration_seconds=2.0,
            checks=[
                ValidationCheck(
                    name="critical_check",
                    status=ValidationStatus.FAILED,
                    message="Critical failure",
                    severity=QualitySeverity.CRITICAL,
                )
            ],
        )

        validation_result = ValidationResult(
            test_id="test_001",
            scenario=TestScenario.STANDARD,
            timestamp=pd.Timestamp.now(),
            overall_status=ValidationStatus.FAILED,
            total_duration_seconds=3.0,
            stage_results=[passed_stage, failed_stage],
        )

        assert len(validation_result.passed_stages) == 1
        assert len(validation_result.failed_stages) == 1
        assert len(validation_result.all_checks) == 2
        assert len(validation_result.failed_checks) == 1
        assert len(validation_result.critical_issues) == 1

    def test_test_report_generation(self):
        """Test TestReport generation with recommendations."""
        from tests.e2e.pipeline_validator import StageValidationResult

        # Create validation result with critical issue
        critical_check = ValidationCheck(
            name="critical_test",
            status=ValidationStatus.FAILED,
            message="Critical failure",
            severity=QualitySeverity.CRITICAL,
        )

        stage_result = StageValidationResult(
            stage=ValidationStage.EXTRACTION,
            status=ValidationStatus.FAILED,
            duration_seconds=1.0,
            checks=[critical_check],
        )

        validation_result = ValidationResult(
            test_id="test_002",
            scenario=TestScenario.MINIMAL,
            timestamp=pd.Timestamp.now(),
            overall_status=ValidationStatus.FAILED,
            total_duration_seconds=1.0,
            stage_results=[stage_result],
        )

        report = TestReport(
            report_id="report_002",
            test_id="test_002",
            scenario=TestScenario.MINIMAL,
            timestamp=pd.Timestamp.now(),
            validation_result=validation_result,
        )

        # Check summary generation
        assert report.summary["overall_status"] == "failed"
        assert report.summary["critical_issues"] == 1
        assert report.summary["stages_failed"] == 1

        # Check recommendations generation
        assert len(report.recommendations) > 0
        critical_rec = next(
            (r for r in report.recommendations if r.priority == RecommendationPriority.CRITICAL),
            None,
        )
        assert critical_rec is not None
        assert "critical_test" in critical_rec.related_checks

    def test_validation_reporter(self):
        """Test ValidationReporter functionality."""
        import os
        import tempfile

        from tests.e2e.pipeline_validator import StageValidationResult

        # Create temporary directory for artifacts
        with tempfile.TemporaryDirectory() as temp_dir:
            reporter = ValidationReporter(output_dir=temp_dir)

            # Create simple validation result
            stage_result = StageValidationResult(
                stage=ValidationStage.EXTRACTION,
                status=ValidationStatus.PASSED,
                duration_seconds=1.0,
                checks=[
                    ValidationCheck(
                        name="test_check", status=ValidationStatus.PASSED, message="Test passed"
                    )
                ],
            )

            validation_result = ValidationResult(
                test_id="test_003",
                scenario=TestScenario.STANDARD,
                timestamp=pd.Timestamp.now(),
                overall_status=ValidationStatus.PASSED,
                total_duration_seconds=1.0,
                stage_results=[stage_result],
            )

            # Generate report with explicit test_id
            report = reporter.generate_report(
                validation_result, test_id="test_003", include_artifacts=True
            )

            assert report.test_id == "test_003"
            assert report.scenario == TestScenario.STANDARD
            assert len(report.artifacts) == 2  # JSON and Markdown

            # Check that artifact files were created
            assert os.path.exists(report.artifacts["json"])
            assert os.path.exists(report.artifacts["markdown"])

            # Check JSON content
            import json

            with open(report.artifacts["json"]) as f:
                json_data = json.load(f)
            assert json_data["test_id"] == "test_003"
            assert json_data["summary"]["overall_status"] == "passed"

            # Check Markdown content
            with open(report.artifacts["markdown"]) as f:
                md_content = f.read()
            assert "# E2E Test Report: test_003" in md_content
            assert "**Overall Status:** PASSED" in md_content


class TestIntegration:
    """Integration tests for pipeline validator components."""

    def test_end_to_end_validation_flow(self):
        """Test complete validation flow from data to report."""
        validator = PipelineValidator()
        reporter = ValidationReporter()

        # Create test data
        raw_data = pd.DataFrame(
            {
                "Company": ["Acme Inc", "TechCorp"],
                "UEI": ["UEI001", "UEI002"],
                "Contract": ["C001", "C002"],
            }
        )

        enriched_data = pd.DataFrame(
            {
                "Company": ["Acme Inc", "TechCorp"],
                "UEI": ["UEI001", "UEI002"],
                "Contract": ["C001", "C002"],
                "_usaspending_match_method": ["exact", "fuzzy"],
                "_usaspending_match_score": [1.0, 0.85],
            }
        )

        # Run validations
        extraction_result = validator.validate_extraction_stage(
            raw_data=raw_data, expected_columns=["Company", "UEI", "Contract"], min_records=1
        )

        enrichment_result = validator.validate_enrichment_stage(
            enriched_data=enriched_data, original_data=raw_data, min_match_rate=0.7
        )

        # Create overall validation result
        validation_result = ValidationResult(
            test_id="integration_test",
            scenario=TestScenario.STANDARD,
            timestamp=pd.Timestamp.now(),
            overall_status=ValidationStatus.PASSED,
            total_duration_seconds=extraction_result.duration_seconds
            + enrichment_result.duration_seconds,
            stage_results=[extraction_result, enrichment_result],
        )

        # Generate report
        report = reporter.generate_report(validation_result, include_artifacts=False)

        assert report.validation_result.overall_status == ValidationStatus.PASSED
        assert len(report.validation_result.stage_results) == 2
        assert report.summary["stages_passed"] == 2
        assert report.summary["stages_failed"] == 0

        # Should have success recommendation
        success_rec = next((r for r in report.recommendations if r.category == "success"), None)
        assert success_rec is not None
