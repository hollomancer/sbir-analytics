"""Autonomous development task discovery.

Discovers pending work items from multiple sources (Kiro specs, lint errors,
type errors, test failures, code TODOs) and prioritizes them for the
autodev-runner agent.

The actual implementation loop runs through the ``autodev-runner`` agent
in Claude Code, not through this module.  This module powers:
- ``sbir-cli autodev discover`` — list all pending work items
- ``sbir-cli autodev specs`` — show Kiro spec completion status
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .task_parser import SpecContext, SpecTask, TaskRisk, build_task_queue, discover_specs
from .task_sources import TaskSource, WorkItem, discover_all


@dataclass
class DiscoveryConfig:
    """Configuration for task discovery."""

    project_root: Path = field(default_factory=lambda: Path.cwd())
    specs_root: Path | None = None
    discover_tests: bool = False

    def __post_init__(self):
        if self.specs_root is None:
            self.specs_root = self.project_root / ".kiro" / "specs"


def _spec_task_to_work_item(task: SpecTask, spec: SpecContext) -> WorkItem:
    """Convert a Kiro spec task to a unified WorkItem."""
    context = {}
    if spec.requirements_text:
        context["requirements_excerpt"] = spec.requirements_text[:500]
    if spec.design_text:
        context["design_excerpt"] = spec.design_text[:500]

    return WorkItem(
        source=TaskSource.KIRO_SPEC,
        title=f"[{spec.name}] {task.description}",
        description=task.description,
        risk=task.risk,
        file_path=task.file_hints[0] if task.file_hints else None,
        spec_name=spec.name,
        task_id=task.task_id,
        context=context,
    )


def discover_work(config: DiscoveryConfig) -> list[WorkItem]:
    """Discover all available work items from all sources."""
    items: list[WorkItem] = []

    # Kiro spec tasks
    specs_root = config.specs_root or config.project_root / ".kiro" / "specs"
    specs = discover_specs(specs_root)
    spec_map = {s.name: s for s in specs}
    queue = build_task_queue(specs)
    for task in queue:
        spec = spec_map[task.spec_name]
        items.append(_spec_task_to_work_item(task, spec))

    # Code quality items
    other_items = discover_all(
        config.project_root,
        run_tests=config.discover_tests,
    )
    items.extend(other_items)

    return items
