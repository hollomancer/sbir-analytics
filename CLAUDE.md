# Claude Code Instructions

**Read [AGENTS.md](AGENTS.md) first.** It holds the project overview, key
directories, commands, testing conventions, code standards, principles, and
scope discipline that apply to every agent working in this repo. This file adds
only the Claude-specific layer.

## Agents

Custom agents in `.claude/agents/`:

| Agent | When to Use | Model |
|-------|-------------|-------|
| `spec-implementer` | Implementing spec tasks, "work on [spec-name]" | opus |
| `test-fixer` | Failing tests, broken coverage, test diagnostics | sonnet |
| `quality-sweep` | Lint/type errors, code cleanup after large changes | sonnet |
| `scope-guard` | Before large implementations — challenges scope creep | opus |

For **spec work**: scope-guard → spec-implementer → test-fixer → quality-sweep.
For **bug fixes**: skip to test-fixer or quality-sweep directly.

## Skills

| Skill | Use Case |
|-------|----------|
| `/review-spec [spec-name\|all]` | Review spec relevance against codebase |

## Reminders that bite most often

All of these are in AGENTS.md, but they cause the most rework:

- Run `make lint`, not hand-rolled `ruff`/`mypy` paths. Checking `sbir_etl/`
  alone covers 205 of 783 files and will pass while CI fails.
- No `from __future__ import annotations` in Dagster asset files. It breaks
  runtime context type validation, and nothing lints for it.
- Transition scoring changes must hold the ≥85% precision benchmark.
