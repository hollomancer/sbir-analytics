"""
Data models for OpenSpec to Kiro migration.

This module defines the data structures used throughout the migration process,
including OpenSpec content models, Kiro content models, and migration metadata.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


# Migration Configuration
@dataclass
class MigrationConfig:
    """Configuration for OpenSpec to Kiro migration."""
    openspec_path: Path
    kiro_path: Path
    archive_path: Path
    output_path: Path
    dry_run: bool = False
    verbose: bool = False
    preserve_history: bool = True


# OpenSpec Content Models
@dataclass
class OpenSpecChange:
    """Represents an OpenSpec change proposal."""
    id: str
    path: Path
    proposal: Optional['OpenSpecProposal'] = None
    tasks: Optional['OpenSpecTasks'] = None
    design: Optional['OpenSpecDesign'] = None
    spec_deltas: list['OpenSpecDelta'] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OpenSpecProposal:
    """OpenSpec proposal.md content."""
    title: str
    why: str
    what_changes: list[str]
    impact: 'OpenSpecImpact'
    raw_content: str


@dataclass
class OpenSpecImpact:
    """Impact section from OpenSpec proposal."""
    affected_specs: list[str] = field(default_factory=list)
    affected_code: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)


@dataclass
class OpenSpecTasks:
    """OpenSpec tasks.md content."""
    tasks: list['OpenSpecTask']
    raw_content: str


@dataclass
class OpenSpecTask:
    """Individual task from OpenSpec."""
    id: str
    description: str
    completed: bool
    subtasks: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class OpenSpecDesign:
    """OpenSpec design.md content."""
    content: str
    sections: dict[str, str] = field(default_factory=dict)


@dataclass
class OpenSpecDelta:
    """Specification delta from OpenSpec change."""
    spec_name: str
    operation: str  # ADDED, MODIFIED, REMOVED
    content: str


@dataclass
class OpenSpecSpec:
    """Represents an OpenSpec specification."""
    name: str
    path: Path
    content: str
    sections: dict[str, str] = field(default_factory=dict)


@dataclass
class OpenSpecContent:
    """Complete OpenSpec content structure."""
    active_changes: list[OpenSpecChange] = field(default_factory=list)
    specifications: list[OpenSpecSpec] = field(default_factory=list)
    project_context: str | None = None
    agent_instructions: str | None = None
    archived_changes: list[str] = field(default_factory=list)


# Kiro Content Models
@dataclass
class KiroSpec:
    """Represents a complete Kiro specification."""
    name: str
    requirements: 'KiroRequirements'
    design: Optional['KiroDesign'] = None
    tasks: Optional['KiroTasks'] = None
    source_mapping: dict[str, Any] = field(default_factory=dict)


@dataclass
class KiroRequirements:
    """Kiro requirements.md content."""
    introduction: str
    glossary: dict[str, str] = field(default_factory=dict)
    requirements: list['KiroRequirement'] = field(default_factory=list)


@dataclass
class KiroRequirement:
    """Individual requirement in EARS format."""
    number: int
    user_story: str
    acceptance_criteria: list[str]
    source_references: list[str] = field(default_factory=list)


@dataclass
class KiroDesign:
    """Kiro design.md content."""
    overview: str
    architecture: str = ""
    components: str = ""
    data_models: str = ""
    error_handling: str = ""
    testing_strategy: str = ""
    source_content: str = ""


@dataclass
class KiroTasks:
    """Kiro tasks.md content."""
    tasks: list['KiroTask']


@dataclass
class KiroTask:
    """Individual task for Kiro execution."""
    number: str
    description: str
    subtasks: list[str] = field(default_factory=list)
    requirements_refs: list[str] = field(default_factory=list)
    completed: bool = False
    optional: bool = False


@dataclass
class KiroContent:
    """Complete Kiro content structure."""
    specs: list[KiroSpec] = field(default_factory=list)
    consolidation_mapping: dict[str, list[str]] = field(default_factory=dict)


# Migration Results and Validation
@dataclass
class GeneratedSpec:
    """Represents a generated Kiro specification."""
    name: str
    path: Path
    files_created: list[str] = field(default_factory=list)
    source_changes: list[str] = field(default_factory=list)
    source_specs: list[str] = field(default_factory=list)


@dataclass
class ValidationIssue:
    """Represents a validation issue found during migration."""
    spec_name: str
    issue_type: str
    severity: str  # ERROR, WARNING, INFO
    message: str
    file_path: str | None = None
    line_number: int | None = None
    suggestion: str | None = None


@dataclass
class ValidationReport:
    """Report of migration validation results."""
    total_specs: int
    issues: list[ValidationIssue] = field(default_factory=list)
    passed: bool = True
    validation_time: datetime = field(default_factory=datetime.now)

    def add_issue(self, issue: ValidationIssue):
        """Add a validation issue."""
        self.issues.append(issue)
        if issue.severity == "ERROR":
            self.passed = False

    def get_issues_by_severity(self, severity: str) -> list[ValidationIssue]:
        """Get issues by severity level."""
        return [issue for issue in self.issues if issue.severity == severity]

    def get_issues_by_type(self, issue_type: str) -> list[ValidationIssue]:
        """Get issues by type."""
        return [issue for issue in self.issues if issue.issue_type == issue_type]


@dataclass
class MigrationReport:
    """Complete migration report."""
    migration_id: str
    start_time: datetime
    end_time: datetime
    config: MigrationConfig
    openspec_content: OpenSpecContent
    generated_specs: list[GeneratedSpec] = field(default_factory=list)
    validation_report: ValidationReport | None = None
    progress: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert report to dictionary for JSON serialization."""
        return {
            "migration_id": self.migration_id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_seconds": (self.end_time - self.start_time).total_seconds(),
            "config": {
                "openspec_path": str(self.config.openspec_path),
                "kiro_path": str(self.config.kiro_path),
                "archive_path": str(self.config.archive_path),
                "dry_run": self.config.dry_run,
                "preserve_history": self.config.preserve_history
            },
            "content_summary": {
                "active_changes": len(self.openspec_content.active_changes),
                "specifications": len(self.openspec_content.specifications),
                "archived_changes": len(self.openspec_content.archived_changes),
                "generated_specs": len(self.generated_specs)
            },
            "validation": {
                "passed": self.validation_report.passed if self.validation_report else False,
                "total_issues": len(self.validation_report.issues) if self.validation_report else 0,
                "error_count": len(self.validation_report.get_issues_by_severity("ERROR")) if self.validation_report else 0,
                "warning_count": len(self.validation_report.get_issues_by_severity("WARNING")) if self.validation_report else 0
            },
            "progress": self.progress,
            "errors": self.errors
        }


# Migration Exceptions
class MigrationError(Exception):
    """Base exception for migration errors."""
    pass


class ContentParsingError(MigrationError):
    """Error parsing OpenSpec content."""
    pass


class TransformationError(MigrationError):
    """Error transforming content to Kiro format."""
    pass


class ValidationError(MigrationError):
    """Error validating migrated content."""
    pass


class FileSystemError(MigrationError):
    """Error with file operations during migration."""
    pass
