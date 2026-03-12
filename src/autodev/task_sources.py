"""Multi-source task discovery for autonomous development.

Beyond Kiro specs, discovers work items from:
- Test failures and coverage gaps (pytest output)
- Lint and type errors (ruff/mypy output)
- Documented improvement roadmaps
- Code TODO/FIXME comments
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from .task_parser import TaskRisk


class TaskSource(StrEnum):
    """Where a work item was discovered."""

    KIRO_SPEC = "kiro_spec"
    TEST_FAILURE = "test_failure"
    COVERAGE_GAP = "coverage_gap"
    LINT_ERROR = "lint_error"
    TYPE_ERROR = "type_error"
    ROADMAP = "roadmap"
    CODE_TODO = "code_todo"


@dataclass
class WorkItem:
    """A unified work item from any source."""

    source: TaskSource
    title: str
    description: str
    risk: TaskRisk = TaskRisk.LOW
    file_path: str | None = None
    line_number: int | None = None
    spec_name: str | None = None
    task_id: str | None = None
    context: dict[str, str] = field(default_factory=dict)

    @property
    def location(self) -> str:
        if self.file_path and self.line_number:
            return f"{self.file_path}:{self.line_number}"
        return self.file_path or "unknown"

    @property
    def needs_human_review(self) -> bool:
        return self.risk == TaskRisk.HIGH


def discover_lint_errors(project_root: Path) -> list[WorkItem]:
    """Run ruff and collect fixable lint errors as work items."""
    items: list[WorkItem] = []
    try:
        result = subprocess.run(
            ["uv", "run", "ruff", "check", "src/", "--output-format=json"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 and result.stdout:
            import json

            try:
                errors = json.loads(result.stdout)
            except json.JSONDecodeError:
                return items

            for error in errors[:50]:  # Cap at 50
                items.append(
                    WorkItem(
                        source=TaskSource.LINT_ERROR,
                        title=f"Fix {error.get('code', 'unknown')} in {error.get('filename', 'unknown')}",
                        description=error.get("message", ""),
                        file_path=error.get("filename"),
                        line_number=error.get("location", {}).get("row"),
                        risk=TaskRisk.LOW,
                    )
                )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return items


def discover_type_errors(project_root: Path) -> list[WorkItem]:
    """Run mypy and collect type errors as work items."""
    items: list[WorkItem] = []
    try:
        result = subprocess.run(
            ["uv", "run", "mypy", "src/", "--no-error-summary"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 and result.stdout:
            error_pattern = re.compile(r"^(.+?):(\d+): error: (.+)$", re.MULTILINE)
            for match in error_pattern.finditer(result.stdout):
                filepath, line, message = match.groups()
                items.append(
                    WorkItem(
                        source=TaskSource.TYPE_ERROR,
                        title=f"Fix type error in {Path(filepath).name}:{line}",
                        description=message,
                        file_path=filepath,
                        line_number=int(line),
                        risk=TaskRisk.LOW,
                    )
                )
                if len(items) >= 50:
                    break
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return items


def discover_test_failures(project_root: Path) -> list[WorkItem]:
    """Run fast unit tests and collect failures as work items."""
    items: list[WorkItem] = []
    try:
        result = subprocess.run(
            [
                "uv", "run", "pytest", "tests/unit/",
                "-x", "--tb=line", "-q", "--no-header",
                "-m", "not slow",
                "--timeout=30",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0 and result.stdout:
            # Parse "FAILED tests/unit/foo.py::test_bar - ErrorMsg" lines
            fail_pattern = re.compile(
                r"FAILED\s+(.+?)::(\S+)\s*-?\s*(.*?)$", re.MULTILINE
            )
            for match in fail_pattern.finditer(result.stdout):
                filepath, test_name, message = match.groups()
                items.append(
                    WorkItem(
                        source=TaskSource.TEST_FAILURE,
                        title=f"Fix failing test {test_name}",
                        description=message.strip() or f"Test {test_name} in {filepath} is failing",
                        file_path=filepath,
                        risk=TaskRisk.LOW,
                    )
                )
                if len(items) >= 30:
                    break
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return items


def discover_code_todos(project_root: Path) -> list[WorkItem]:
    """Scan src/ for TODO/FIXME comments."""
    items: list[WorkItem] = []
    todo_pattern = re.compile(r"#\s*(TODO|FIXME|HACK|XXX)[\s:]+(.+)$", re.IGNORECASE)

    src_dir = project_root / "src"
    if not src_dir.exists():
        return items

    for py_file in src_dir.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            for i, line in enumerate(content.splitlines(), 1):
                match = todo_pattern.search(line)
                if match:
                    tag, message = match.groups()
                    items.append(
                        WorkItem(
                            source=TaskSource.CODE_TODO,
                            title=f"{tag.upper()}: {message.strip()[:80]}",
                            description=message.strip(),
                            file_path=str(py_file.relative_to(project_root)),
                            line_number=i,
                            risk=TaskRisk.LOW,
                        )
                    )
        except (OSError, UnicodeDecodeError):
            continue

    return items


def discover_all(project_root: Path, *, run_tests: bool = False) -> list[WorkItem]:
    """Discover work items from all sources.

    Args:
        project_root: Root of the project.
        run_tests: If True, also run pytest to find test failures (slower).

    Returns:
        Prioritized list of work items.
    """
    items: list[WorkItem] = []

    # Fast sources first
    items.extend(discover_code_todos(project_root))
    items.extend(discover_lint_errors(project_root))
    items.extend(discover_type_errors(project_root))

    if run_tests:
        items.extend(discover_test_failures(project_root))

    return items
