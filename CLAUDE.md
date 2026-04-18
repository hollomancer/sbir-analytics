# Claude Code Instructions

## Project

Graph-based ETL: SBIR awards → Neo4j. Dagster orchestration, DuckDB processing, Docker deployment.

Architectural patterns and technical docs live in `docs/steering/`. Feature specs live in `specs/`.

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

## Key Directories

```text
sbir_etl/                 # Core ETL library (extractors, enrichers, transformers, validators, models, config, quality, utils)
packages/
  sbir-analytics/         # Dagster assets, jobs, sensors
  sbir-graph/             # Neo4j loaders
  sbir-ml/                # ML models (CET, transition detection)
config/base.yaml          # Thresholds, paths, performance settings
```

## Common Patterns

- **Monitoring:** Use `sbir_etl.utils` decorators and `AlertCollector`
- **CI:** Edit `.github/workflows/*.yml`, upload artifacts to `reports/`
- **Tests:** Place in `tests/unit|integration|e2e/`, run `pytest -v --cov=sbir_etl`
- **Neo4j:** Modify `packages/sbir-graph/sbir_graph/loaders/`, use MERGE operations

## Testing

```bash
pytest tests/unit/           # Fast unit tests
pytest -m integration        # Integration tests
pytest -n auto               # Parallel execution
```

Transition scoring changes must maintain ≥85% precision benchmark.

## Code Standards

- Line length: 100
- Target: Python 3.11
- Ruff rules: E, W, F, I, B, C4, UP
- Use `StrEnum` not `str, Enum`
- Use `datetime.UTC` not `timezone.utc`
- Do NOT use `from __future__ import annotations` in Dagster asset files — it breaks runtime context type validation

## Principles

- **Simplicity First**: Simplest change that solves the problem. No speculative abstractions, no "flexibility" that wasn't requested. If 200 lines could be 50, rewrite it. Ask: "Would a senior engineer say this is overcomplicated?"
- **No Laziness**: Root causes, not temporary fixes. Senior developer standards.
- **Surgical Changes**: Only touch what the task requires. Don't "improve" adjacent code. Match existing style. If your changes orphan imports/variables, remove them — but don't remove pre-existing dead code unless asked. Every changed line should trace to the request.
- **Verify Before Done**: Prove it works — run tests, check logs, demonstrate correctness. Transform tasks into verifiable goals:

```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```
