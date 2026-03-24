"""Load agent instructions from .claude/agents/ for prompt injection.

Agent markdown files are the single source of truth for behavior.
This module reads them at runtime so the orchestrator and GitHub Actions
workflow use the same instructions as interactive Claude Code sessions.
"""

from __future__ import annotations

import re
from pathlib import Path

# Agent file names (without .md extension)
SPEC_IMPLEMENTER = "spec-implementer"
TEST_FIXER = "test-fixer"
QUALITY_SWEEP = "quality-sweep"
SCOPE_GUARD = "scope-guard"
AUTODEV_RUNNER = "autodev-runner"


def _agents_dir(project_root: Path) -> Path:
    return project_root / ".claude" / "agents"


def load_agent_instructions(project_root: Path, agent_name: str) -> str:
    """Load an agent's instructions from its markdown file.

    Strips YAML frontmatter and returns the body text.
    Returns empty string if the file doesn't exist.
    """
    path = _agents_dir(project_root) / f"{agent_name}.md"
    if not path.exists():
        return ""

    content = path.read_text(encoding="utf-8")

    # Strip YAML frontmatter (--- ... ---)
    content = re.sub(r"^---\n.*?\n---\n", "", content, count=1, flags=re.DOTALL)

    return content.strip()


def agent_for_source(source: str) -> str:
    """Map a task source to the appropriate agent name."""
    mapping = {
        "kiro_spec": SPEC_IMPLEMENTER,
        "test_failure": TEST_FIXER,
        "lint_error": QUALITY_SWEEP,
        "type_error": QUALITY_SWEEP,
        "code_todo": SPEC_IMPLEMENTER,
        "coverage_gap": TEST_FIXER,
    }
    return mapping.get(source, SPEC_IMPLEMENTER)
