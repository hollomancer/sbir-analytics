"""Tests for the Kiro spec task parser."""

from pathlib import Path


from src.autodev.task_parser import (
    SpecContext,
    SpecTask,
    TaskRisk,
    TaskStatus,
    build_task_queue,
    discover_specs,
    load_spec,
    parse_tasks_md,
)


class TestParseTasksMd:
    """Tests for parsing tasks.md content."""

    def test_parse_simple_tasks(self):
        content = """# Implementation Plan

- [x] 1.1 Create data models
- [ ] 1.2 Implement classifier
- [x] 1.3 Write unit tests
"""
        tasks = parse_tasks_md("test-spec", content)
        assert len(tasks) == 3
        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[1].status == TaskStatus.PENDING
        assert tasks[2].status == TaskStatus.COMPLETED

    def test_parse_hierarchical_tasks(self):
        content = """# Tasks

- [x] 1.1 Parent task
  - [x] 1.1.1 Subtask A
  - [ ] 1.1.2 Subtask B
"""
        tasks = parse_tasks_md("test-spec", content)
        assert len(tasks) == 3
        assert tasks[0].task_id == "1.1"
        assert tasks[1].task_id == "1.1.1"
        assert tasks[1].parent_id == "1.1"
        assert "1.1.1" in tasks[0].children

    def test_parse_requirements_links(self):
        content = "- [ ] 2.1 Implement API _Requirements: 1.1, 1.2, 1.3_\n"
        tasks = parse_tasks_md("test-spec", content)
        assert len(tasks) == 1
        assert tasks[0].requirements == ["1.1", "1.2", "1.3"]

    def test_parse_file_hints(self):
        content = "- [ ] 3.1 Create `src/models/foo.py` module\n"
        tasks = parse_tasks_md("test-spec", content)
        assert len(tasks) == 1
        assert "src/models/foo.py" in tasks[0].file_hints

    def test_risk_assessment_high(self):
        content = "- [ ] 4.1 Add API key credential management\n"
        tasks = parse_tasks_md("test-spec", content)
        assert tasks[0].risk == TaskRisk.HIGH

    def test_risk_assessment_medium(self):
        content = "- [ ] 5.1 Create new Dagster asset for enrichment\n"
        tasks = parse_tasks_md("test-spec", content)
        assert tasks[0].risk == TaskRisk.MEDIUM

    def test_risk_assessment_low(self):
        content = "- [ ] 6.1 Write unit tests for classifier\n"
        tasks = parse_tasks_md("test-spec", content)
        assert tasks[0].risk == TaskRisk.LOW

    def test_empty_content(self):
        tasks = parse_tasks_md("test-spec", "")
        assert tasks == []

    def test_no_task_lines(self):
        content = """# Implementation Plan

Some description text without any checkbox tasks.
"""
        tasks = parse_tasks_md("test-spec", content)
        assert tasks == []

    def test_spec_name_propagated(self):
        content = "- [ ] 1.1 Some task\n"
        tasks = parse_tasks_md("my-spec", content)
        assert tasks[0].spec_name == "my-spec"


class TestSpecContext:
    """Tests for SpecContext properties."""

    def test_progress_pct(self):
        ctx = SpecContext(name="test", spec_dir=Path("."))
        ctx.tasks = [
            SpecTask("test", "1", "a", TaskStatus.COMPLETED),
            SpecTask("test", "2", "b", TaskStatus.COMPLETED),
            SpecTask("test", "3", "c", TaskStatus.PENDING),
            SpecTask("test", "4", "d", TaskStatus.PENDING),
        ]
        assert ctx.progress_pct == 50.0

    def test_progress_pct_empty(self):
        ctx = SpecContext(name="test", spec_dir=Path("."))
        assert ctx.progress_pct == 100.0

    def test_pending_tasks(self):
        ctx = SpecContext(name="test", spec_dir=Path("."))
        ctx.tasks = [
            SpecTask("test", "1", "a", TaskStatus.COMPLETED),
            SpecTask("test", "2", "b", TaskStatus.PENDING),
        ]
        assert len(ctx.pending_tasks) == 1
        assert ctx.pending_tasks[0].task_id == "2"


class TestLoadSpec:
    """Tests for loading specs from disk."""

    def test_load_spec_from_real_dir(self, tmp_path):
        spec_dir = tmp_path / "test-spec"
        spec_dir.mkdir()
        (spec_dir / "requirements.md").write_text("# Requirements\nSome reqs")
        (spec_dir / "design.md").write_text("# Design\nSome design")
        (spec_dir / "tasks.md").write_text("- [x] 1.1 Done\n- [ ] 1.2 Todo\n")

        spec = load_spec(spec_dir)
        assert spec.name == "test-spec"
        assert len(spec.tasks) == 2
        assert "Requirements" in spec.requirements_text
        assert "Design" in spec.design_text

    def test_load_spec_plan_md_fallback(self, tmp_path):
        spec_dir = tmp_path / "plan-spec"
        spec_dir.mkdir()
        (spec_dir / "plan.md").write_text("- [ ] 1.1 Task from plan\n")

        spec = load_spec(spec_dir)
        assert len(spec.tasks) == 1
        assert spec.tasks[0].description == "Task from plan"

    def test_load_spec_missing_files(self, tmp_path):
        spec_dir = tmp_path / "empty-spec"
        spec_dir.mkdir()

        spec = load_spec(spec_dir)
        assert spec.name == "empty-spec"
        assert spec.tasks == []


class TestDiscoverSpecs:
    """Tests for spec discovery."""

    def test_discover_skips_archive(self, tmp_path):
        (tmp_path / "active-spec").mkdir()
        (tmp_path / "active-spec" / "tasks.md").write_text("- [ ] 1.1 Task\n")
        (tmp_path / "archive").mkdir()
        (tmp_path / "archive" / "old-spec").mkdir()
        (tmp_path / "archive" / "old-spec" / "tasks.md").write_text("- [ ] 1.1 Old\n")

        specs = discover_specs(tmp_path)
        assert len(specs) == 1
        assert specs[0].name == "active-spec"

    def test_discover_sorts_by_completion(self, tmp_path):
        # Spec A: 50% complete
        (tmp_path / "spec-a").mkdir()
        (tmp_path / "spec-a" / "tasks.md").write_text("- [x] 1.1 Done\n- [ ] 1.2 Todo\n")

        # Spec B: 100% complete
        (tmp_path / "spec-b").mkdir()
        (tmp_path / "spec-b" / "tasks.md").write_text("- [x] 1.1 Done\n")

        specs = discover_specs(tmp_path)
        assert specs[0].name == "spec-b"  # Most complete first

    def test_discover_nonexistent_dir(self, tmp_path):
        specs = discover_specs(tmp_path / "nonexistent")
        assert specs == []


class TestBuildTaskQueue:
    """Tests for task queue building."""

    def test_queue_contains_only_pending(self):
        spec = SpecContext(name="test", spec_dir=Path("."))
        spec.tasks = [
            SpecTask("test", "1", "done", TaskStatus.COMPLETED),
            SpecTask("test", "2", "todo", TaskStatus.PENDING),
        ]
        queue = build_task_queue([spec])
        assert len(queue) == 1
        assert queue[0].task_id == "2"

    def test_queue_sorts_by_risk(self):
        spec = SpecContext(name="test", spec_dir=Path("."))
        spec.tasks = [
            SpecTask("test", "1", "deploy to production", TaskStatus.PENDING, risk=TaskRisk.HIGH),
            SpecTask("test", "2", "write unit tests", TaskStatus.PENDING, risk=TaskRisk.LOW),
            SpecTask("test", "3", "new dagster asset", TaskStatus.PENDING, risk=TaskRisk.MEDIUM),
        ]
        queue = build_task_queue([spec])
        assert queue[0].risk == TaskRisk.LOW
        assert queue[1].risk == TaskRisk.MEDIUM
        assert queue[2].risk == TaskRisk.HIGH
