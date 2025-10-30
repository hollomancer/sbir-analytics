"""
Data models for OpenSpec to Kiro migration.

This module defines the data structures used throughout the migration process,
including OpenSpec content models, Kiro content models, and migration metadata.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any


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
    spec_deltas: List['OpenSpecDelta'] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OpenSpecProposal:
    """OpenSpec proposal.md content."""
    title: str
    why: str
    what_changes: List[str]
    impact: 'OpenSpecImpact'
    raw_content: str


@dataclass
class OpenSpecImpact:
    """Impact section from OpenSpec proposal."""
    affected_specs: List[str] = field(default_factory=list)
    affected_code: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)


@dataclass
class OpenSpecTasks:
    """OpenSpec tasks.md content."""
    tasks: List['OpenSpecTask']
    raw_content: str


@dataclass
class OpenSpecTask:
    """Individual task from OpenSpec."""
    id: str
    description: str
    completed: bool
    subtasks: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class OpenSpecDesign:
    """OpenSpec design.md content."""
    content: str
    sections: Dict[str, str] = field(default_factory=dict)


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
    sections: Dict[str, str] = field(default_factory=dict)


@dataclass
class OpenSpecContent:
    """Complete OpenSpec content structure."""
    active_changes: List[OpenSpecChange] = field(default_factory=list)
    specifications: List[OpenSpecSpec] = field(default_factory=list)
    project_context: Optional[str] = None
    agent_instructions: Optional[str] = None
    archived_changes: List[str] = field(default_factory=list)


# Kiro Content Models
@dataclass
class KiroSpec:
    """Represents a complete Kiro specification."""
    name: str
    requirements: 'KiroRequirements'
    design: Optional['KiroDesign'] = None
    tasks: Optional['KiroTasks'] = None
    source_mapping: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KiroRequirements:
    """Kiro requirements.md content."""
    introduction: str
    glossary: Dict[str, str] = field(default_factory=dict)
    requirements: List['KiroRequirement'] = field(default_factory=list)


@dataclass
class KiroRequirement:
    """Individual requirement in EARS format."""
    number: int
    user_story: str
    acceptance_criteria: List[str]
    source_references: List[str] = field(default_factory=list)


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
    tasks: List['KiroTask']


@dataclass
class KiroTask:
    """Individual task for Kiro execution."""
    number: str
    description: str
    subtasks: List[str] = field(default_factory=list)
    requirements_refs: List[str] = field(default_factory=list)
    completed: bool = False
    optional: bool = False


@dataclass
class KiroContent:
    """Complete Kiro content structure."""
    specs: List[KiroSpec] = field(default_factory=list)
    consolidation_mapping: Dict[str, List[str]] = field(default_factory=dict)


# Migration Results and Validation
@dataclass
class GeneratedSpec:
    """Represents a generated Kiro specification."""
    name: str
    path: Path
    files_created: List[str] = field(default_factory=list)
    source_changes: List[str] = field(default_factory=list)
    source_specs: List[str] = field(default_factory=list)


@dataclass
class ValidationIssue:
    """Represents a validation issue found during migration."""
    spec_name: str
    issue_type: str
    severity: str  # ERROR, WARNING, INFO
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    suggestion: Optional[str] = None


@dataclass
class ValidationReport:
    """Report of migration validation results."""
    total_specs: int
    issues: List[ValidationIssue] = field(default_factory=list)
    passed: bool = True
    validation_time: datetime = field(default_factory=datetime.now)
    
    def add_issue(self, issue: ValidationIssue):
        """Add a validation issue."""
        self.issues.append(issue)
        if issue.severity == "ERROR":
            self.passed = False
    
    def get_issues_by_severity(self, severity: str) -> List[ValidationIssue]:
        """Get issues by severity level."""
        return [issue for issue in self.issues if issue.severity == severity]
    
    def get_issues_by_type(self, issue_type: str) -> List[ValidationIssue]:
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
    generated_specs: List[GeneratedSpec] = field(default_factory=list)
    validation_report: Optional[ValidationReport] = None
    progress: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
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