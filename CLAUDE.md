# Claude Code Instructions

See [AGENTS.md](./AGENTS.md) for project context, architecture, and development workflows.

## Agents

Custom agents in `.claude/agents/`:

| Agent | When to Use | Model |
|-------|-------------|-------|
| `spec-implementer` | Implementing Kiro spec tasks, "work on [spec-name]" | opus |
| `test-fixer` | Failing tests, broken coverage, test diagnostics | sonnet |
| `quality-sweep` | Lint/type errors, code cleanup after large changes | sonnet |
| `scope-guard` | Before large implementations — challenges scope creep and over-engineering | opus |

### Agent Workflow

For **spec work**, the typical flow is:

1. **scope-guard** — Review the spec tasks for necessity and alignment before building
2. **spec-implementer** — Implement the approved tasks
3. **test-fixer** — Fix any test failures introduced
4. **quality-sweep** — Clean up lint/type issues

For **bug fixes and quality work**, skip straight to the relevant agent (test-fixer or quality-sweep).

## Skills

| Skill | Use Case |
|-------|----------|
| `/review-spec [spec-name\|all]` | Review spec relevance against codebase |

## Testing Quick Reference

```bash
pytest tests/unit/           # Fast unit tests
pytest -m integration        # Integration tests
pytest -n auto               # Parallel execution
```

Transition scoring changes must maintain ≥85% precision benchmark.
