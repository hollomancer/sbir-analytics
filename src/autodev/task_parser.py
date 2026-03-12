"""Parse Kiro specification task files into an actionable task queue.

Reads tasks.md files from .kiro/specs/, extracts incomplete tasks with their
hierarchy, requirements links, and context from associated design/requirements docs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path


class TaskStatus(StrEnum):
    """Status of a parsed task."""

    PENDING = "pending"
    COMPLETED = "completed"


class TaskRisk(StrEnum):
    """Risk level determining whether human review is needed."""

    LOW = "low"  # Pure implementation, tests, docs
    MEDIUM = "medium"  # New modules, API integration design
    HIGH = "high"  # Architecture changes, external services, credentials


@dataclass
class SpecTask:
    """A single actionable task parsed from a Kiro spec."""

    spec_name: str
    task_id: str
    description: str
    status: TaskStatus
    parent_id: str | None = None
    children: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)
    risk: TaskRisk = TaskRisk.LOW
    file_hints: list[str] = field(default_factory=list)

    @property
    def is_pending(self) -> bool:
        return self.status == TaskStatus.PENDING

    @property
    def needs_human_review(self) -> bool:
        return self.risk == TaskRisk.HIGH


@dataclass
class SpecContext:
    """Full context for a specification, including design and requirements."""

    name: str
    spec_dir: Path
    requirements_text: str = ""
    design_text: str = ""
    tasks_text: str = ""
    tasks: list[SpecTask] = field(default_factory=list)

    @property
    def pending_tasks(self) -> list[SpecTask]:
        return [t for t in self.tasks if t.is_pending]

    @property
    def completed_tasks(self) -> list[SpecTask]:
        return [t for t in self.tasks if t.status == TaskStatus.COMPLETED]

    @property
    def progress_pct(self) -> float:
        if not self.tasks:
            return 100.0
        return len(self.completed_tasks) / len(self.tasks) * 100


# Patterns that suggest higher risk
_HIGH_RISK_PATTERNS = re.compile(
    r"(credential|secret|auth|deploy|production|infrastructure|"
    r"schema\s+change|migration|api\s+key|aws|lambda|docker)",
    re.IGNORECASE,
)

_MEDIUM_RISK_PATTERNS = re.compile(
    r"(new\s+module|api\s+integration|external\s+service|"
    r"dagster\s+asset|neo4j\s+schema|pipeline\s+stage)",
    re.IGNORECASE,
)

_FILE_HINT_PATTERN = re.compile(r"`(src/[^`]+\.py)`")

_TASK_LINE_PATTERN = re.compile(
    r"^(\s*)- \[([ x])\]\s*(\d+(?:\.\d+)*)\s+(.*?)$"
)

_REQUIREMENTS_PATTERN = re.compile(
    r"_Requirements?:\s*([^_]+)_", re.IGNORECASE
)


def _assess_risk(description: str) -> TaskRisk:
    """Determine risk level from task description."""
    if _HIGH_RISK_PATTERNS.search(description):
        return TaskRisk.HIGH
    if _MEDIUM_RISK_PATTERNS.search(description):
        return TaskRisk.MEDIUM
    return TaskRisk.LOW


def _extract_file_hints(text: str) -> list[str]:
    """Extract file path hints from backtick-quoted paths."""
    return _FILE_HINT_PATTERN.findall(text)


def parse_tasks_md(spec_name: str, content: str) -> list[SpecTask]:
    """Parse a tasks.md file into a list of SpecTask objects.

    Handles both flat and hierarchical task formats:
      - [x] 1.1 Completed task
      - [ ] 1.2 Pending task
        - [x] 1.2.1 Completed subtask
        - [ ] 1.2.2 Pending subtask
    """
    tasks: list[SpecTask] = []
    task_map: dict[str, SpecTask] = {}

    for line in content.splitlines():
        match = _TASK_LINE_PATTERN.match(line)
        if not match:
            continue

        _indent, checkbox, task_id, description = match.groups()
        status = TaskStatus.COMPLETED if checkbox == "x" else TaskStatus.PENDING

        # Extract requirements references
        req_match = _REQUIREMENTS_PATTERN.search(description)
        requirements = []
        if req_match:
            requirements = [r.strip() for r in req_match.group(1).split(",")]

        # Extract file hints
        file_hints = _extract_file_hints(description)

        # Determine parent
        parts = task_id.split(".")
        parent_id = ".".join(parts[:-1]) if len(parts) > 1 else None

        task = SpecTask(
            spec_name=spec_name,
            task_id=task_id,
            description=description.strip(),
            status=status,
            parent_id=parent_id,
            requirements=requirements,
            risk=_assess_risk(description),
            file_hints=file_hints,
        )

        tasks.append(task)
        task_map[task_id] = task

        # Link to parent
        if parent_id and parent_id in task_map:
            task_map[parent_id].children.append(task_id)

    return tasks


def load_spec(spec_dir: Path) -> SpecContext:
    """Load a complete specification from a directory.

    Reads requirements.md, design.md, and tasks.md to build full context.
    """
    name = spec_dir.name

    requirements_text = ""
    design_text = ""
    tasks_text = ""

    req_path = spec_dir / "requirements.md"
    if req_path.exists():
        requirements_text = req_path.read_text(encoding="utf-8")

    design_path = spec_dir / "design.md"
    if design_path.exists():
        design_text = design_path.read_text(encoding="utf-8")

    tasks_path = spec_dir / "tasks.md"
    if tasks_path.exists():
        tasks_text = tasks_path.read_text(encoding="utf-8")

    # Also check for plan.md (alternative format)
    plan_path = spec_dir / "plan.md"
    if not tasks_path.exists() and plan_path.exists():
        tasks_text = plan_path.read_text(encoding="utf-8")

    tasks = parse_tasks_md(name, tasks_text)

    return SpecContext(
        name=name,
        spec_dir=spec_dir,
        requirements_text=requirements_text,
        design_text=design_text,
        tasks_text=tasks_text,
        tasks=tasks,
    )


def discover_specs(specs_root: Path) -> list[SpecContext]:
    """Discover and load all active specifications.

    Scans .kiro/specs/ for spec directories, skipping the archive.
    Returns specs sorted by completion percentage (most complete first,
    to finish near-done specs before starting new ones).
    """
    specs = []

    if not specs_root.exists():
        return specs

    for entry in sorted(specs_root.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name == "archive":
            continue

        spec = load_spec(entry)
        if spec.tasks:  # Only include specs that have parseable tasks
            specs.append(spec)

    # Sort: most complete specs first (finish what's started)
    specs.sort(key=lambda s: s.progress_pct, reverse=True)

    return specs


def build_task_queue(specs: list[SpecContext]) -> list[SpecTask]:
    """Build a prioritized queue of pending tasks across all specs.

    Priority order:
    1. Tasks from nearly-complete specs (finish what's started)
    2. Low-risk tasks before high-risk (maximize autonomous progress)
    3. Parent tasks before children (respect hierarchy)
    """
    pending: list[SpecTask] = []

    for spec in specs:
        pending.extend(spec.pending_tasks)

    # Sort by risk (low first), preserving spec order from discover_specs
    risk_order = {TaskRisk.LOW: 0, TaskRisk.MEDIUM: 1, TaskRisk.HIGH: 2}
    pending.sort(key=lambda t: risk_order[t.risk])

    return pending
