"""
Migration Validator

This module validates migration completeness and accuracy,
including EARS pattern validation and content verification.
"""

import logging
import re
from pathlib import Path

from .models import (
    GeneratedSpec,
    OpenSpecContent,
    ValidationError,
    ValidationIssue,
    ValidationReport,
)


class MigrationValidator:
    """Validates migration completeness and accuracy."""

    def __init__(self):
        """Initialize validator."""
        self.logger = logging.getLogger(__name__)
        self.ears_validator = EARSValidator()

    def validate_migration(self, generated_specs: list[GeneratedSpec],
                         openspec_content: OpenSpecContent) -> ValidationReport:
        """Comprehensive migration validation."""
        self.logger.info(f"Validating migration of {len(generated_specs)} specs")

        report = ValidationReport(total_specs=len(generated_specs))

        try:
            # Content completeness validation
            self._validate_content_completeness(report, generated_specs, openspec_content)

            # Format validation
            self._validate_kiro_format(report, generated_specs)

            # EARS pattern validation
            self._validate_ears_patterns(report, generated_specs)

            # Task structure validation
            self._validate_task_structure(report, generated_specs)

            self.logger.info(f"Validation complete: {len(report.issues)} issues found")

        except Exception as e:
            raise ValidationError(f"Validation failed: {e}")

        return report

    def _validate_content_completeness(self, report: ValidationReport,
                                     generated_specs: list[GeneratedSpec],
                                     openspec_content: OpenSpecContent):
        """Validate that no content was lost during migration."""
        # Check that all active changes have corresponding specs
        change_ids = {change.id for change in openspec_content.active_changes}
        spec_names = {spec.name for spec in generated_specs}

        for change_id in change_ids:
            # Convert change ID to expected spec name
            expected_name = change_id.replace("add-", "").replace("evaluate-", "").replace("-", "_")

            if expected_name not in spec_names:
                report.add_issue(ValidationIssue(
                    spec_name=expected_name,
                    issue_type="missing_spec",
                    severity="ERROR",
                    message=f"OpenSpec change '{change_id}' has no corresponding Kiro spec"
                ))

    def _validate_kiro_format(self, report: ValidationReport, generated_specs: list[GeneratedSpec]):
        """Validate that generated specs follow Kiro format."""
        for spec in generated_specs:
            # Check that required files exist
            if "requirements.md" not in spec.files_created:
                report.add_issue(ValidationIssue(
                    spec_name=spec.name,
                    issue_type="missing_file",
                    severity="ERROR",
                    message="Missing requirements.md file"
                ))

            # Validate file structure
            self._validate_spec_files(report, spec)

    def _validate_spec_files(self, report: ValidationReport, spec: GeneratedSpec):
        """Validate individual spec files."""
        # Validate requirements.md
        requirements_file = spec.path / "requirements.md"
        if requirements_file.exists():
            self._validate_requirements_file(report, spec.name, requirements_file)

        # Validate tasks.md
        tasks_file = spec.path / "tasks.md"
        if tasks_file.exists():
            self._validate_tasks_file(report, spec.name, tasks_file)

    def _validate_requirements_file(self, report: ValidationReport, spec_name: str, file_path: Path):
        """Validate requirements.md file structure."""
        try:
            content = file_path.read_text(encoding='utf-8')

            # Check for required sections
            required_sections = ["# Requirements Document", "## Introduction", "## Glossary", "## Requirements"]

            for section in required_sections:
                if section not in content:
                    report.add_issue(ValidationIssue(
                        spec_name=spec_name,
                        issue_type="missing_section",
                        severity="WARNING",
                        message=f"Missing section: {section}",
                        file_path=str(file_path)
                    ))

        except Exception as e:
            report.add_issue(ValidationIssue(
                spec_name=spec_name,
                issue_type="file_read_error",
                severity="ERROR",
                message=f"Cannot read requirements file: {e}",
                file_path=str(file_path)
            ))

    def _validate_tasks_file(self, report: ValidationReport, spec_name: str, file_path: Path):
        """Validate tasks.md file structure."""
        try:
            content = file_path.read_text(encoding='utf-8')

            # Check for task format
            task_pattern = r'^\s*-\s*\[\s*[x\s]\s*\]\s*\d+(?:\.\d+)*\s+.+'

            if not re.search(task_pattern, content, re.MULTILINE):
                report.add_issue(ValidationIssue(
                    spec_name=spec_name,
                    issue_type="invalid_task_format",
                    severity="WARNING",
                    message="No properly formatted tasks found",
                    file_path=str(file_path)
                ))

        except Exception as e:
            report.add_issue(ValidationIssue(
                spec_name=spec_name,
                issue_type="file_read_error",
                severity="ERROR",
                message=f"Cannot read tasks file: {e}",
                file_path=str(file_path)
            ))

    def _validate_ears_patterns(self, report: ValidationReport, generated_specs: list[GeneratedSpec]):
        """Validate that requirements follow EARS patterns."""
        for spec in generated_specs:
            requirements_file = spec.path / "requirements.md"
            if requirements_file.exists():
                self.ears_validator.validate_ears_patterns(report, spec.name, requirements_file)

    def _validate_task_structure(self, report: ValidationReport, generated_specs: list[GeneratedSpec]):
        """Validate task structure and references."""
        for spec in generated_specs:
            tasks_file = spec.path / "tasks.md"
            if tasks_file.exists():
                self._validate_task_references(report, spec.name, tasks_file)

    def _validate_task_references(self, report: ValidationReport, spec_name: str, tasks_file: Path):
        """Validate that tasks reference requirements properly."""
        try:
            content = tasks_file.read_text(encoding='utf-8')

            # Look for requirement references
            ref_pattern = r'_Requirements:\s*([^_]+)_'
            references = re.findall(ref_pattern, content)

            if not references:
                report.add_issue(ValidationIssue(
                    spec_name=spec_name,
                    issue_type="missing_requirement_refs",
                    severity="INFO",
                    message="Tasks do not reference specific requirements",
                    file_path=str(tasks_file)
                ))

        except Exception as e:
            report.add_issue(ValidationIssue(
                spec_name=spec_name,
                issue_type="file_read_error",
                severity="ERROR",
                message=f"Cannot validate task references: {e}",
                file_path=str(tasks_file)
            ))


class EARSValidator:
    """Validates EARS (Easy Approach to Requirements Syntax) patterns."""

    def __init__(self):
        """Initialize EARS validator."""
        self.ears_patterns = [
            r'THE\s+\w+\s+SHALL\s+',  # Basic EARS pattern
            r'WHEN\s+.+,\s+THE\s+\w+\s+SHALL\s+',  # Event-driven
            r'WHILE\s+.+,\s+THE\s+\w+\s+SHALL\s+',  # State-driven
            r'IF\s+.+,\s+THEN\s+THE\s+\w+\s+SHALL\s+',  # Unwanted event
            r'WHERE\s+.+,\s+THE\s+\w+\s+SHALL\s+'  # Optional feature
        ]

    def validate_ears_patterns(self, report: ValidationReport, spec_name: str, requirements_file: Path):
        """Validate EARS patterns in requirements file."""
        try:
            content = requirements_file.read_text(encoding='utf-8')

            # Extract acceptance criteria sections
            criteria_sections = re.findall(r'#### Acceptance Criteria\s*\n(.*?)(?=###|\Z)', content, re.DOTALL)

            for i, section in enumerate(criteria_sections, 1):
                self._validate_criteria_section(report, spec_name, section, i, requirements_file)

        except Exception as e:
            report.add_issue(ValidationIssue(
                spec_name=spec_name,
                issue_type="ears_validation_error",
                severity="ERROR",
                message=f"Cannot validate EARS patterns: {e}",
                file_path=str(requirements_file)
            ))

    def _validate_criteria_section(self, report: ValidationReport, spec_name: str,
                                 section: str, req_number: int, file_path: Path):
        """Validate individual acceptance criteria section."""
        lines = [line.strip() for line in section.split('\n') if line.strip()]

        for line in lines:
            if line.startswith(('1.', '2.', '3.', '4.', '5.')):
                # This is an acceptance criterion
                if not self._is_valid_ears_pattern(line):
                    report.add_issue(ValidationIssue(
                        spec_name=spec_name,
                        issue_type="invalid_ears_pattern",
                        severity="WARNING",
                        message=f"Requirement {req_number} criterion does not follow EARS patterns: {line[:50]}...",
                        file_path=str(file_path),
                        suggestion="Use format: 'THE System SHALL action' or other EARS patterns"
                    ))

    def _is_valid_ears_pattern(self, criterion: str) -> bool:
        """Check if criterion follows EARS patterns."""
        # Remove numbering
        text = re.sub(r'^\d+\.\s*', '', criterion)

        # Check against EARS patterns
        for pattern in self.ears_patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True

        return False
