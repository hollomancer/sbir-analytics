"""Tests for agent prompt loading and integration."""

from pathlib import Path
from textwrap import dedent

import pytest

from src.autodev.agent_prompts import (
    QUALITY_SWEEP,
    SPEC_IMPLEMENTER,
    TEST_FIXER,
    agent_for_source,
    load_agent_instructions,
)


@pytest.fixture()
def agents_dir(tmp_path: Path) -> Path:
    """Create a temporary .claude/agents/ directory with sample agent files."""
    d = tmp_path / ".claude" / "agents"
    d.mkdir(parents=True)
    return d


class TestLoadAgentInstructions:
    def test_loads_plain_markdown(self, tmp_path: Path, agents_dir: Path):
        (agents_dir / "spec-implementer.md").write_text("Do the spec work.\n")
        result = load_agent_instructions(tmp_path, "spec-implementer")
        assert result == "Do the spec work."

    def test_strips_yaml_frontmatter(self, tmp_path: Path, agents_dir: Path):
        content = dedent("""\
            ---
            name: test-agent
            tools: Read, Write
            ---
            Body text here.
        """)
        (agents_dir / "test-agent.md").write_text(content)
        result = load_agent_instructions(tmp_path, "test-agent")
        assert result == "Body text here."
        assert "---" not in result

    def test_returns_empty_for_missing_file(self, tmp_path: Path, agents_dir: Path):
        result = load_agent_instructions(tmp_path, "nonexistent-agent")
        assert result == ""

    def test_returns_empty_when_agents_dir_missing(self, tmp_path: Path):
        result = load_agent_instructions(tmp_path, "any-agent")
        assert result == ""

    def test_preserves_body_content(self, tmp_path: Path, agents_dir: Path):
        content = dedent("""\
            ---
            name: scope-guard
            description: Challenges scope
            tools: Read, Glob
            model: opus
            ---
            You are the scope guard.

            ## Core Principle

            Question everything.
        """)
        (agents_dir / "scope-guard.md").write_text(content)
        result = load_agent_instructions(tmp_path, "scope-guard")
        assert result.startswith("You are the scope guard.")
        assert "## Core Principle" in result
        assert "Question everything." in result


class TestAgentForSource:
    @pytest.mark.parametrize(
        ("source", "expected"),
        [
            ("kiro_spec", SPEC_IMPLEMENTER),
            ("test_failure", TEST_FIXER),
            ("lint_error", QUALITY_SWEEP),
            ("type_error", QUALITY_SWEEP),
            ("code_todo", SPEC_IMPLEMENTER),
            ("coverage_gap", TEST_FIXER),
        ],
    )
    def test_known_sources(self, source: str, expected: str):
        assert agent_for_source(source) == expected

    def test_unknown_source_defaults_to_spec_implementer(self):
        assert agent_for_source("unknown_source") == SPEC_IMPLEMENTER


class TestBuildImplementationPromptIntegration:
    """Test that build_implementation_prompt injects agent instructions."""

    def test_prompt_includes_agent_instructions(self, tmp_path: Path, agents_dir: Path):
        (agents_dir / "spec-implementer.md").write_text(
            dedent("""\
                ---
                name: spec-implementer
                ---
                Follow the spec carefully.
            """)
        )

        from src.autodev.orchestrator import build_implementation_prompt
        from src.autodev.task_sources import TaskSource, WorkItem

        item = WorkItem(
            source=TaskSource.KIRO_SPEC,
            title="[test-spec] Add widget",
            description="Add a widget module",
            spec_name="test-spec",
            task_id="1.1",
        )
        prompt = build_implementation_prompt(item, project_root=tmp_path)
        assert "## Agent Instructions" in prompt
        assert "Follow the spec carefully." in prompt
        assert "## Task: [test-spec] Add widget" in prompt

    def test_prompt_without_project_root_has_no_agent_section(self):
        from src.autodev.orchestrator import build_implementation_prompt
        from src.autodev.task_sources import TaskSource, WorkItem

        item = WorkItem(
            source=TaskSource.LINT_ERROR,
            title="Fix lint",
            description="Unused import",
            file_path="src/foo.py",
            line_number=10,
        )
        prompt = build_implementation_prompt(item)
        assert "## Agent Instructions" not in prompt
        assert "## Task: Fix lint" in prompt
