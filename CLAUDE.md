# Claude Code Instructions

See [AGENTS.md](./AGENTS.md) for project context, architecture, and development workflows.

## Agents

Custom agents in `.claude/agents/`:

| Agent | Trigger |
|-------|---------|
| `spec-implementer` | Implementing Kiro spec tasks, "work on [spec-name]" |
| `test-fixer` | Failing tests, improving test coverage |
| `quality-sweep` | Lint errors, type errors, code quality cleanup |
| `autodev-runner` | Autonomous development sessions, "start autodev" |
| `scope-guard` | Before large implementations, reviewing specs for over-engineering. Counterbalance to builder agents. |

## Skills

| Skill | Use Case |
|-------|----------|
| `/review-spec [spec-name\|all]` | Review spec relevance against codebase |

## Autonomous Development

```bash
sbir-cli autodev discover    # See all pending work items
sbir-cli autodev specs       # View Kiro spec completion status
```

Use the `autodev-runner` agent for interactive autonomous work.

## Testing Quick Reference

```bash
pytest tests/unit/           # Fast unit tests
pytest -m integration        # Integration tests
pytest -n auto               # Parallel execution
```

Transition scoring changes must maintain ≥85% precision benchmark.
