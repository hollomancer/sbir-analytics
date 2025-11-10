"""Tests for migration models."""

import pytest
from pathlib import Path
from datetime import datetime

from src.migration.models import (
    MigrationConfig,
    OpenSpecChange,
    OpenSpecProposal,
    OpenSpecImpact,
    OpenSpecTasks,
    OpenSpecTask,
    OpenSpecDesign,
    OpenSpecDelta,
    OpenSpecSpec,
    OpenSpecContent,
    KiroSpec,
    KiroRequirements,
    KiroRequirement,
    KiroDesign,
    KiroTasks,
    KiroTask,
    KiroContent,
    GeneratedSpec,
    ValidationIssue,
    ValidationReport,
    MigrationReport,
    MigrationError,
    ContentParsingError,
    TransformationError,
    ValidationError,
    FileSystemError,
)


class TestMigrationConfig:
    """Tests for MigrationConfig model."""

    def test_minimal_config(self):
        """Test creating minimal MigrationConfig."""
        config = MigrationConfig(
            openspec_path=Path("/openspec"),
            kiro_path=Path("/kiro"),
            archive_path=Path("/archive"),
            output_path=Path("/output"),
        )
        assert config.openspec_path == Path("/openspec")
        assert config.kiro_path == Path("/kiro")
        assert config.dry_run is False
        assert config.preserve_history is True

    def test_full_config(self):
        """Test creating full MigrationConfig with all options."""
        config = MigrationConfig(
            openspec_path=Path("/openspec"),
            kiro_path=Path("/kiro"),
            archive_path=Path("/archive"),
            output_path=Path("/output"),
            dry_run=True,
            verbose=True,
            preserve_history=False,
        )
        assert config.dry_run is True
        assert config.verbose is True
        assert config.preserve_history is False

    def test_default_values(self):
        """Test MigrationConfig default values."""
        config = MigrationConfig(
            openspec_path=Path("/test"),
            kiro_path=Path("/test"),
            archive_path=Path("/test"),
            output_path=Path("/test"),
        )
        assert config.dry_run is False
        assert config.verbose is False
        assert config.preserve_history is True


class TestOpenSpecModels:
    """Tests for OpenSpec data models."""

    def test_openspec_impact_defaults(self):
        """Test OpenSpecImpact default values."""
        impact = OpenSpecImpact()
        assert impact.affected_specs == []
        assert impact.affected_code == []
        assert impact.dependencies == []
        assert impact.risks == []

    def test_openspec_impact_with_data(self):
        """Test OpenSpecImpact with data."""
        impact = OpenSpecImpact(
            affected_specs=["spec1", "spec2"],
            affected_code=["module1"],
            dependencies=["dep1"],
            risks=["risk1", "risk2"],
        )
        assert len(impact.affected_specs) == 2
        assert len(impact.risks) == 2

    def test_openspec_proposal(self):
        """Test OpenSpecProposal model."""
        impact = OpenSpecImpact(affected_specs=["spec1"])
        proposal = OpenSpecProposal(
            title="Test Proposal",
            why="Because reasons",
            what_changes=["change1", "change2"],
            impact=impact,
            raw_content="# Test\nContent",
        )
        assert proposal.title == "Test Proposal"
        assert len(proposal.what_changes) == 2
        assert proposal.impact.affected_specs == ["spec1"]

    def test_openspec_task_defaults(self):
        """Test OpenSpecTask default values."""
        task = OpenSpecTask(
            id="task-1",
            description="Do something",
            completed=False,
        )
        assert task.subtasks == []
        assert task.notes == ""

    def test_openspec_task_with_subtasks(self):
        """Test OpenSpecTask with subtasks."""
        task = OpenSpecTask(
            id="task-1",
            description="Main task",
            completed=True,
            subtasks=["subtask1", "subtask2"],
            notes="Some notes",
        )
        assert len(task.subtasks) == 2
        assert task.notes == "Some notes"
        assert task.completed is True

    def test_openspec_tasks(self):
        """Test OpenSpecTasks model."""
        tasks = OpenSpecTasks(
            tasks=[
                OpenSpecTask(id="1", description="Task 1", completed=False),
                OpenSpecTask(id="2", description="Task 2", completed=True),
            ],
            raw_content="# Tasks\n- Task 1\n- Task 2",
        )
        assert len(tasks.tasks) == 2
        assert tasks.tasks[1].completed is True

    def test_openspec_design(self):
        """Test OpenSpecDesign model."""
        design = OpenSpecDesign(
            content="Design content",
            sections={"architecture": "Arch details", "data": "Data models"},
        )
        assert design.content == "Design content"
        assert len(design.sections) == 2

    def test_openspec_delta(self):
        """Test OpenSpecDelta model."""
        delta = OpenSpecDelta(
            spec_name="spec1",
            operation="MODIFIED",
            content="New content",
        )
        assert delta.spec_name == "spec1"
        assert delta.operation == "MODIFIED"

    def test_openspec_spec(self):
        """Test OpenSpecSpec model."""
        spec = OpenSpecSpec(
            name="test-spec",
            path=Path("/specs/test-spec.md"),
            content="Specification content",
            sections={"overview": "Overview text"},
        )
        assert spec.name == "test-spec"
        assert spec.path == Path("/specs/test-spec.md")

    def test_openspec_change_defaults(self):
        """Test OpenSpecChange default values."""
        change = OpenSpecChange(
            id="change-1",
            path=Path("/changes/change-1"),
        )
        assert change.proposal is None
        assert change.tasks is None
        assert change.design is None
        assert change.spec_deltas == []
        assert change.metadata == {}

    def test_openspec_change_full(self):
        """Test OpenSpecChange with all components."""
        impact = OpenSpecImpact(affected_specs=["spec1"])
        proposal = OpenSpecProposal(
            title="Test",
            why="Reason",
            what_changes=["change"],
            impact=impact,
            raw_content="Content",
        )
        tasks = OpenSpecTasks(tasks=[], raw_content="Tasks")
        design = OpenSpecDesign(content="Design")

        change = OpenSpecChange(
            id="change-1",
            path=Path("/changes/change-1"),
            proposal=proposal,
            tasks=tasks,
            design=design,
            spec_deltas=[OpenSpecDelta("spec1", "ADDED", "content")],
            metadata={"author": "test"},
        )

        assert change.proposal.title == "Test"
        assert change.tasks is not None
        assert len(change.spec_deltas) == 1
        assert change.metadata["author"] == "test"

    def test_openspec_content_defaults(self):
        """Test OpenSpecContent default values."""
        content = OpenSpecContent()
        assert content.active_changes == []
        assert content.specifications == []
        assert content.project_context is None
        assert content.agent_instructions is None
        assert content.archived_changes == []

    def test_openspec_content_with_data(self):
        """Test OpenSpecContent with data."""
        change = OpenSpecChange(id="change-1", path=Path("/test"))
        spec = OpenSpecSpec(name="spec1", path=Path("/spec"), content="Content")

        content = OpenSpecContent(
            active_changes=[change],
            specifications=[spec],
            project_context="Project context",
            agent_instructions="Agent instructions",
            archived_changes=["archived-1", "archived-2"],
        )

        assert len(content.active_changes) == 1
        assert len(content.specifications) == 1
        assert content.project_context == "Project context"
        assert len(content.archived_changes) == 2


class TestKiroModels:
    """Tests for Kiro data models."""

    def test_kiro_requirement(self):
        """Test KiroRequirement model."""
        requirement = KiroRequirement(
            number=1,
            user_story="As a user, I want to...",
            acceptance_criteria=["Given...", "When...", "Then..."],
            source_references=["change-1", "spec-1"],
        )
        assert requirement.number == 1
        assert len(requirement.acceptance_criteria) == 3
        assert len(requirement.source_references) == 2

    def test_kiro_requirement_defaults(self):
        """Test KiroRequirement default values."""
        requirement = KiroRequirement(
            number=1,
            user_story="Story",
            acceptance_criteria=["criteria"],
        )
        assert requirement.source_references == []

    def test_kiro_requirements(self):
        """Test KiroRequirements model."""
        req1 = KiroRequirement(
            number=1,
            user_story="Story 1",
            acceptance_criteria=["AC1"],
        )
        req2 = KiroRequirement(
            number=2,
            user_story="Story 2",
            acceptance_criteria=["AC2"],
        )

        requirements = KiroRequirements(
            introduction="Introduction text",
            glossary={"term1": "definition1", "term2": "definition2"},
            requirements=[req1, req2],
        )

        assert requirements.introduction == "Introduction text"
        assert len(requirements.glossary) == 2
        assert len(requirements.requirements) == 2

    def test_kiro_requirements_defaults(self):
        """Test KiroRequirements default values."""
        requirements = KiroRequirements(introduction="Intro")
        assert requirements.glossary == {}
        assert requirements.requirements == []

    def test_kiro_design_defaults(self):
        """Test KiroDesign default values."""
        design = KiroDesign(overview="Overview text")
        assert design.architecture == ""
        assert design.components == ""
        assert design.data_models == ""
        assert design.error_handling == ""
        assert design.testing_strategy == ""
        assert design.source_content == ""

    def test_kiro_design_full(self):
        """Test KiroDesign with all fields."""
        design = KiroDesign(
            overview="Overview",
            architecture="Architecture",
            components="Components",
            data_models="Data models",
            error_handling="Error handling",
            testing_strategy="Testing",
            source_content="Source",
        )
        assert design.overview == "Overview"
        assert design.architecture == "Architecture"
        assert design.testing_strategy == "Testing"

    def test_kiro_task_defaults(self):
        """Test KiroTask default values."""
        task = KiroTask(number="1", description="Task description")
        assert task.subtasks == []
        assert task.requirements_refs == []
        assert task.completed is False
        assert task.optional is False

    def test_kiro_task_full(self):
        """Test KiroTask with all fields."""
        task = KiroTask(
            number="1.1",
            description="Implementation task",
            subtasks=["subtask1", "subtask2"],
            requirements_refs=["REQ-1", "REQ-2"],
            completed=True,
            optional=True,
        )
        assert task.number == "1.1"
        assert len(task.subtasks) == 2
        assert len(task.requirements_refs) == 2
        assert task.completed is True
        assert task.optional is True

    def test_kiro_tasks(self):
        """Test KiroTasks model."""
        tasks = KiroTasks(
            tasks=[
                KiroTask(number="1", description="Task 1"),
                KiroTask(number="2", description="Task 2", completed=True),
            ]
        )
        assert len(tasks.tasks) == 2
        assert tasks.tasks[1].completed is True

    def test_kiro_spec_defaults(self):
        """Test KiroSpec default values."""
        requirements = KiroRequirements(introduction="Intro")
        spec = KiroSpec(name="test-spec", requirements=requirements)
        assert spec.design is None
        assert spec.tasks is None
        assert spec.source_mapping == {}

    def test_kiro_spec_full(self):
        """Test KiroSpec with all components."""
        requirements = KiroRequirements(introduction="Intro")
        design = KiroDesign(overview="Overview")
        tasks = KiroTasks(tasks=[])

        spec = KiroSpec(
            name="test-spec",
            requirements=requirements,
            design=design,
            tasks=tasks,
            source_mapping={"from_change": "change-1"},
        )

        assert spec.name == "test-spec"
        assert spec.design is not None
        assert spec.tasks is not None
        assert spec.source_mapping["from_change"] == "change-1"

    def test_kiro_content_defaults(self):
        """Test KiroContent default values."""
        content = KiroContent()
        assert content.specs == []
        assert content.consolidation_mapping == {}

    def test_kiro_content_with_specs(self):
        """Test KiroContent with specs."""
        requirements = KiroRequirements(introduction="Intro")
        spec1 = KiroSpec(name="spec1", requirements=requirements)
        spec2 = KiroSpec(name="spec2", requirements=requirements)

        content = KiroContent(
            specs=[spec1, spec2],
            consolidation_mapping={"spec1": ["change-1", "change-2"]},
        )

        assert len(content.specs) == 2
        assert content.consolidation_mapping["spec1"] == ["change-1", "change-2"]


class TestMigrationResults:
    """Tests for migration result models."""

    def test_generated_spec_defaults(self):
        """Test GeneratedSpec default values."""
        spec = GeneratedSpec(name="test-spec", path=Path("/output/test-spec"))
        assert spec.files_created == []
        assert spec.source_changes == []
        assert spec.source_specs == []

    def test_generated_spec_full(self):
        """Test GeneratedSpec with all fields."""
        spec = GeneratedSpec(
            name="test-spec",
            path=Path("/output/test-spec"),
            files_created=["requirements.md", "design.md", "tasks.md"],
            source_changes=["change-1", "change-2"],
            source_specs=["old-spec-1"],
        )
        assert len(spec.files_created) == 3
        assert len(spec.source_changes) == 2
        assert "old-spec-1" in spec.source_specs

    def test_validation_issue(self):
        """Test ValidationIssue model."""
        issue = ValidationIssue(
            spec_name="test-spec",
            issue_type="missing_requirement",
            severity="ERROR",
            message="Requirement is missing",
            file_path="/spec/requirements.md",
            line_number=42,
            suggestion="Add requirement",
        )
        assert issue.spec_name == "test-spec"
        assert issue.severity == "ERROR"
        assert issue.line_number == 42

    def test_validation_issue_minimal(self):
        """Test ValidationIssue with minimal fields."""
        issue = ValidationIssue(
            spec_name="test-spec",
            issue_type="warning",
            severity="WARNING",
            message="Warning message",
        )
        assert issue.file_path is None
        assert issue.line_number is None
        assert issue.suggestion is None

    def test_validation_report_defaults(self):
        """Test ValidationReport default values."""
        report = ValidationReport(total_specs=5)
        assert report.total_specs == 5
        assert report.issues == []
        assert report.passed is True
        assert isinstance(report.validation_time, datetime)

    def test_validation_report_add_issue_warning(self):
        """Test adding warning issue to validation report."""
        report = ValidationReport(total_specs=5)
        issue = ValidationIssue(
            spec_name="spec1",
            issue_type="warning",
            severity="WARNING",
            message="Warning",
        )
        report.add_issue(issue)

        assert len(report.issues) == 1
        assert report.passed is True  # Warnings don't fail

    def test_validation_report_add_issue_error(self):
        """Test adding error issue to validation report."""
        report = ValidationReport(total_specs=5)
        issue = ValidationIssue(
            spec_name="spec1",
            issue_type="error",
            severity="ERROR",
            message="Error",
        )
        report.add_issue(issue)

        assert len(report.issues) == 1
        assert report.passed is False  # Errors cause failure

    def test_validation_report_get_issues_by_severity(self):
        """Test getting issues by severity level."""
        report = ValidationReport(total_specs=5)
        report.add_issue(ValidationIssue("spec1", "err", "ERROR", "Error 1"))
        report.add_issue(ValidationIssue("spec1", "warn", "WARNING", "Warning 1"))
        report.add_issue(ValidationIssue("spec2", "err", "ERROR", "Error 2"))
        report.add_issue(ValidationIssue("spec2", "info", "INFO", "Info 1"))

        errors = report.get_issues_by_severity("ERROR")
        warnings = report.get_issues_by_severity("WARNING")
        infos = report.get_issues_by_severity("INFO")

        assert len(errors) == 2
        assert len(warnings) == 1
        assert len(infos) == 1

    def test_validation_report_get_issues_by_type(self):
        """Test getting issues by type."""
        report = ValidationReport(total_specs=5)
        report.add_issue(ValidationIssue("spec1", "missing", "ERROR", "Error"))
        report.add_issue(ValidationIssue("spec1", "missing", "WARNING", "Warning"))
        report.add_issue(ValidationIssue("spec2", "format", "ERROR", "Error"))

        missing_issues = report.get_issues_by_type("missing")
        format_issues = report.get_issues_by_type("format")

        assert len(missing_issues) == 2
        assert len(format_issues) == 1

    def test_migration_report_to_dict(self):
        """Test MigrationReport.to_dict() method."""
        config = MigrationConfig(
            openspec_path=Path("/openspec"),
            kiro_path=Path("/kiro"),
            archive_path=Path("/archive"),
            output_path=Path("/output"),
            dry_run=True,
            preserve_history=True,
        )

        openspec_content = OpenSpecContent(
            active_changes=[OpenSpecChange(id="c1", path=Path("/c1"))],
            specifications=[OpenSpecSpec("s1", Path("/s1"), "content")],
            archived_changes=["a1", "a2"],
        )

        validation_report = ValidationReport(total_specs=2)
        validation_report.add_issue(ValidationIssue("s1", "err", "ERROR", "Error"))
        validation_report.add_issue(ValidationIssue("s1", "warn", "WARNING", "Warn"))

        start = datetime(2024, 1, 1, 10, 0, 0)
        end = datetime(2024, 1, 1, 10, 5, 30)

        report = MigrationReport(
            migration_id="mig-123",
            start_time=start,
            end_time=end,
            config=config,
            openspec_content=openspec_content,
            generated_specs=[
                GeneratedSpec("spec1", Path("/spec1")),
                GeneratedSpec("spec2", Path("/spec2")),
            ],
            validation_report=validation_report,
            progress={"step": "validation"},
            errors=["Error 1"],
        )

        result = report.to_dict()

        # Check basic fields
        assert result["migration_id"] == "mig-123"
        assert result["start_time"] == "2024-01-01T10:00:00"
        assert result["end_time"] == "2024-01-01T10:05:30"
        assert result["duration_seconds"] == 330.0

        # Check config
        assert result["config"]["openspec_path"] == "/openspec"
        assert result["config"]["dry_run"] is True

        # Check content summary
        assert result["content_summary"]["active_changes"] == 1
        assert result["content_summary"]["specifications"] == 1
        assert result["content_summary"]["archived_changes"] == 2
        assert result["content_summary"]["generated_specs"] == 2

        # Check validation
        assert result["validation"]["passed"] is False
        assert result["validation"]["total_issues"] == 2
        assert result["validation"]["error_count"] == 1
        assert result["validation"]["warning_count"] == 1

        # Check progress and errors
        assert result["progress"]["step"] == "validation"
        assert len(result["errors"]) == 1

    def test_migration_report_to_dict_no_validation(self):
        """Test MigrationReport.to_dict() without validation report."""
        config = MigrationConfig(
            openspec_path=Path("/test"),
            kiro_path=Path("/test"),
            archive_path=Path("/test"),
            output_path=Path("/test"),
        )

        report = MigrationReport(
            migration_id="mig-456",
            start_time=datetime.now(),
            end_time=datetime.now(),
            config=config,
            openspec_content=OpenSpecContent(),
            validation_report=None,
        )

        result = report.to_dict()

        assert result["validation"]["passed"] is False
        assert result["validation"]["total_issues"] == 0
        assert result["validation"]["error_count"] == 0


class TestMigrationExceptions:
    """Tests for migration exception classes."""

    def test_migration_error_basic(self):
        """Test MigrationError basic usage."""
        error = MigrationError("Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.component == "migration.openspec_to_kiro"

    def test_migration_error_with_details(self):
        """Test MigrationError with details."""
        error = MigrationError("Error", details={"file": "test.md"})
        assert error.details["file"] == "test.md"

    def test_content_parsing_error(self):
        """Test ContentParsingError."""
        error = ContentParsingError("Failed to parse content")
        assert "Failed to parse content" in str(error)
        assert error.operation == "parse_content"
        assert error.component == "migration.openspec_to_kiro"

    def test_transformation_error(self):
        """Test TransformationError."""
        error = TransformationError("Failed to transform")
        assert "Failed to transform" in str(error)
        assert error.operation == "transform_content"

    def test_validation_error(self):
        """Test ValidationError."""
        error = ValidationError("Validation failed")
        assert "Validation failed" in str(error)
        assert error.operation == "validate_content"

    def test_filesystem_error(self):
        """Test FileSystemError."""
        error = FileSystemError("File not found")
        assert "File not found" in str(error)
        assert error.operation == "file_operation"

    def test_exception_inheritance(self):
        """Test exception inheritance hierarchy."""
        content_error = ContentParsingError("Parse error")
        transform_error = TransformationError("Transform error")
        validation_error = ValidationError("Validation error")
        fs_error = FileSystemError("FS error")

        # All should be instances of MigrationError
        assert isinstance(content_error, MigrationError)
        assert isinstance(transform_error, MigrationError)
        assert isinstance(validation_error, MigrationError)
        assert isinstance(fs_error, MigrationError)

    def test_exception_can_be_raised(self):
        """Test exceptions can be raised and caught."""
        with pytest.raises(MigrationError):
            raise MigrationError("Test error")

        with pytest.raises(ContentParsingError):
            raise ContentParsingError("Parse error")

        # ContentParsingError is also a MigrationError
        with pytest.raises(MigrationError):
            raise ContentParsingError("Parse error")
