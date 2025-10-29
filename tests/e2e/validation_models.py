"""Data models for E2E validation reporting.

This module provides comprehensive data models for validation results,
test reports, and recommendations for E2E testing.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from tests.e2e.pipeline_validator import ValidationCheck, ValidationStage, ValidationStatus, StageValidationResult


class TestScenario(str, Enum):
    """E2E test scenarios."""
    
    MINIMAL = "minimal"
    STANDARD = "standard"
    LARGE = "large"
    EDGE_CASES = "edge_cases"


class RecommendationPriority(str, Enum):
    """Priority levels for recommendations."""
    
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ValidationResult:
    """Comprehensive validation result for E2E testing."""
    
    test_id: str
    scenario: TestScenario
    timestamp: datetime
    overall_status: ValidationStatus
    total_duration_seconds: float
    stage_results: List[StageValidationResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def passed_stages(self) -> List[StageValidationResult]:
        """Get all stages that passed validation."""
        return [s for s in self.stage_results if s.status == ValidationStatus.PASSED]
    
    @property
    def failed_stages(self) -> List[StageValidationResult]:
        """Get all stages that failed validation."""
        return [s for s in self.stage_results if s.status == ValidationStatus.FAILED]
    
    @property
    def warning_stages(self) -> List[StageValidationResult]:
        """Get all stages with warnings."""
        return [s for s in self.stage_results if s.status == ValidationStatus.WARNING]
    
    @property
    def all_checks(self) -> List[ValidationCheck]:
        """Get all validation checks across all stages."""
        checks = []
        for stage_result in self.stage_results:
            checks.extend(stage_result.checks)
        return checks
    
    @property
    def failed_checks(self) -> List[ValidationCheck]:
        """Get all failed validation checks."""
        return [c for c in self.all_checks if c.status == ValidationStatus.FAILED]
    
    @property
    def critical_issues(self) -> List[ValidationCheck]:
        """Get all critical validation issues."""
        from src.models.quality import QualitySeverity
        return [c for c in self.all_checks if c.severity == QualitySeverity.CRITICAL]


@dataclass
class Recommendation:
    """Actionable recommendation based on validation results."""
    
    title: str
    description: str
    priority: RecommendationPriority
    category: str  # e.g., "data_quality", "performance", "configuration"
    actions: List[str] = field(default_factory=list)
    related_checks: List[str] = field(default_factory=list)  # Check names
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestReport:
    """Comprehensive test report with validation results and recommendations."""
    
    report_id: str
    test_id: str
    scenario: TestScenario
    timestamp: datetime
    validation_result: ValidationResult
    recommendations: List[Recommendation] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)  # artifact_type -> file_path
    
    def __post_init__(self):
        """Generate summary and recommendations after initialization."""
        self._generate_summary()
        self._generate_recommendations()
    
    def _generate_summary(self):
        """Generate test summary statistics."""
        validation = self.validation_result
        
        self.summary = {
            "overall_status": validation.overall_status.value,
            "total_duration_seconds": validation.total_duration_seconds,
            "stages_tested": len(validation.stage_results),
            "stages_passed": len(validation.passed_stages),
            "stages_failed": len(validation.failed_stages),
            "stages_with_warnings": len(validation.warning_stages),
            "total_checks": len(validation.all_checks),
            "checks_passed": len([c for c in validation.all_checks if c.status == ValidationStatus.PASSED]),
            "checks_failed": len(validation.failed_checks),
            "critical_issues": len(validation.critical_issues),
            "scenario": validation.scenario.value
        }
    
    def _generate_recommendations(self):
        """Generate actionable recommendations based on validation results."""
        recommendations = []
        validation = self.validation_result
        
        # Critical issues recommendations
        if validation.critical_issues:
            critical_checks = [c.name for c in validation.critical_issues]
            recommendations.append(Recommendation(
                title="Address Critical Issues",
                description=f"Found {len(validation.critical_issues)} critical issues that must be resolved",
                priority=RecommendationPriority.CRITICAL,
                category="data_quality",
                actions=[
                    "Review failed validation checks",
                    "Fix data source issues",
                    "Verify pipeline configuration",
                    "Re-run validation after fixes"
                ],
                related_checks=critical_checks,
                details={"critical_count": len(validation.critical_issues)}
            ))
        
        # Performance recommendations
        slow_stages = [s for s in validation.stage_results if s.duration_seconds > 30]
        if slow_stages:
            stage_names = [s.stage.value for s in slow_stages]
            recommendations.append(Recommendation(
                title="Optimize Performance",
                description=f"Stages taking longer than expected: {', '.join(stage_names)}",
                priority=RecommendationPriority.MEDIUM,
                category="performance",
                actions=[
                    "Review resource allocation",
                    "Optimize data processing logic",
                    "Consider batch size adjustments",
                    "Monitor memory usage"
                ],
                details={"slow_stages": stage_names}
            ))
        
        # Data quality recommendations
        failed_data_checks = [c for c in validation.failed_checks if "record_count" in c.name or "match_rate" in c.name]
        if failed_data_checks:
            check_names = [c.name for c in failed_data_checks]
            recommendations.append(Recommendation(
                title="Improve Data Quality",
                description="Data quality checks failed, indicating potential issues with input data",
                priority=RecommendationPriority.HIGH,
                category="data_quality",
                actions=[
                    "Validate input data sources",
                    "Review data extraction logic",
                    "Check enrichment data coverage",
                    "Adjust quality thresholds if appropriate"
                ],
                related_checks=check_names
            ))
        
        # Neo4j specific recommendations
        neo4j_failures = [c for c in validation.failed_checks if any(stage.stage == ValidationStage.LOADING for stage in validation.stage_results)]
        if neo4j_failures:
            recommendations.append(Recommendation(
                title="Fix Neo4j Loading Issues",
                description="Neo4j graph validation failed",
                priority=RecommendationPriority.HIGH,
                category="infrastructure",
                actions=[
                    "Verify Neo4j connection",
                    "Check database constraints",
                    "Review loading logic",
                    "Validate graph schema"
                ],
                related_checks=[c.name for c in neo4j_failures]
            ))
        
        # Success recommendations
        if validation.overall_status == ValidationStatus.PASSED:
            recommendations.append(Recommendation(
                title="Pipeline Validation Successful",
                description="All validation checks passed successfully",
                priority=RecommendationPriority.LOW,
                category="success",
                actions=[
                    "Pipeline is ready for production use",
                    "Consider running performance benchmarks",
                    "Monitor ongoing data quality"
                ]
            ))
        
        self.recommendations = recommendations


class ValidationReporter:
    """Reporter for generating validation reports and artifacts."""
    
    def __init__(self, output_dir: str = "artifacts"):
        """Initialize validation reporter.
        
        Args:
            output_dir: Directory to save report artifacts
        """
        self.output_dir = output_dir
    
    def generate_report(
        self,
        validation_result: ValidationResult,
        test_id: Optional[str] = None,
        include_artifacts: bool = True
    ) -> TestReport:
        """Generate comprehensive test report.
        
        Args:
            validation_result: Validation result to report on
            test_id: Optional test identifier
            include_artifacts: Whether to generate artifact files
            
        Returns:
            TestReport with validation results and recommendations
        """
        if not test_id:
            test_id = f"test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        report_id = f"report_{test_id}"
        
        report = TestReport(
            report_id=report_id,
            test_id=test_id,
            scenario=validation_result.scenario,
            timestamp=datetime.now(),
            validation_result=validation_result
        )
        
        if include_artifacts:
            artifacts = self._generate_artifacts(report)
            report.artifacts = artifacts
        
        return report
    
    def _generate_artifacts(self, report: TestReport) -> Dict[str, str]:
        """Generate report artifacts (files).
        
        Args:
            report: Test report to generate artifacts for
            
        Returns:
            Dictionary mapping artifact type to file path
        """
        import json
        import os
        from pathlib import Path
        
        # Create output directory
        output_path = Path(self.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        artifacts = {}
        
        # JSON report
        json_path = output_path / f"{report.report_id}.json"
        json_data = {
            "report_id": report.report_id,
            "test_id": report.test_id,
            "scenario": report.scenario.value,
            "timestamp": report.timestamp.isoformat(),
            "summary": report.summary,
            "validation_result": {
                "overall_status": report.validation_result.overall_status.value,
                "total_duration_seconds": report.validation_result.total_duration_seconds,
                "stage_results": [
                    {
                        "stage": stage.stage.value,
                        "status": stage.status.value,
                        "duration_seconds": stage.duration_seconds,
                        "checks": [
                            {
                                "name": check.name,
                                "status": check.status.value,
                                "message": check.message,
                                "expected": check.expected,
                                "actual": check.actual,
                                "severity": check.severity.value if hasattr(check.severity, 'value') else str(check.severity)
                            }
                            for check in stage.checks
                        ],
                        "metadata": stage.metadata
                    }
                    for stage in report.validation_result.stage_results
                ]
            },
            "recommendations": [
                {
                    "title": rec.title,
                    "description": rec.description,
                    "priority": rec.priority.value,
                    "category": rec.category,
                    "actions": rec.actions,
                    "related_checks": rec.related_checks,
                    "details": rec.details
                }
                for rec in report.recommendations
            ]
        }
        
        with open(json_path, 'w') as f:
            json.dump(json_data, f, indent=2, default=str)
        artifacts["json"] = str(json_path)
        
        # Markdown report
        md_path = output_path / f"{report.report_id}.md"
        md_content = self._generate_markdown_report(report)
        with open(md_path, 'w') as f:
            f.write(md_content)
        artifacts["markdown"] = str(md_path)
        
        return artifacts
    
    def _generate_markdown_report(self, report: TestReport) -> str:
        """Generate markdown report content.
        
        Args:
            report: Test report to generate markdown for
            
        Returns:
            Markdown report content as string
        """
        lines = []
        
        # Header
        lines.append(f"# E2E Test Report: {report.test_id}")
        lines.append("")
        lines.append(f"**Report ID:** {report.report_id}")
        lines.append(f"**Scenario:** {report.scenario.value}")
        lines.append(f"**Timestamp:** {report.timestamp.isoformat()}")
        lines.append(f"**Overall Status:** {report.validation_result.overall_status.value.upper()}")
        lines.append(f"**Duration:** {report.validation_result.total_duration_seconds:.2f} seconds")
        lines.append("")
        
        # Summary
        lines.append("## Summary")
        lines.append("")
        summary = report.summary
        lines.append(f"- **Stages Tested:** {summary['stages_tested']}")
        lines.append(f"- **Stages Passed:** {summary['stages_passed']}")
        lines.append(f"- **Stages Failed:** {summary['stages_failed']}")
        lines.append(f"- **Total Checks:** {summary['total_checks']}")
        lines.append(f"- **Checks Passed:** {summary['checks_passed']}")
        lines.append(f"- **Checks Failed:** {summary['checks_failed']}")
        lines.append(f"- **Critical Issues:** {summary['critical_issues']}")
        lines.append("")
        
        # Stage Results
        lines.append("## Stage Results")
        lines.append("")
        for stage_result in report.validation_result.stage_results:
            status_icon = "✅" if stage_result.status == ValidationStatus.PASSED else "❌" if stage_result.status == ValidationStatus.FAILED else "⚠️"
            lines.append(f"### {status_icon} {stage_result.stage.value.title()} Stage")
            lines.append("")
            lines.append(f"**Status:** {stage_result.status.value}")
            lines.append(f"**Duration:** {stage_result.duration_seconds:.2f} seconds")
            lines.append("")
            
            if stage_result.checks:
                lines.append("**Validation Checks:**")
                lines.append("")
                for check in stage_result.checks:
                    check_icon = "✅" if check.status == ValidationStatus.PASSED else "❌" if check.status == ValidationStatus.FAILED else "⚠️"
                    lines.append(f"- {check_icon} **{check.name}**: {check.message}")
                lines.append("")
        
        # Recommendations
        if report.recommendations:
            lines.append("## Recommendations")
            lines.append("")
            for rec in report.recommendations:
                priority_icon = "🔴" if rec.priority == RecommendationPriority.CRITICAL else "🟡" if rec.priority == RecommendationPriority.HIGH else "🟢"
                lines.append(f"### {priority_icon} {rec.title}")
                lines.append("")
                lines.append(f"**Priority:** {rec.priority.value}")
                lines.append(f"**Category:** {rec.category}")
                lines.append("")
                lines.append(rec.description)
                lines.append("")
                if rec.actions:
                    lines.append("**Recommended Actions:**")
                    for action in rec.actions:
                        lines.append(f"- {action}")
                    lines.append("")
        
        return "\n".join(lines)