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

## Principles

- **Simplicity First**: Simplest change that solves the problem. Minimal code impact.
- **No Laziness**: Root causes, not temporary fixes. Senior developer standards.
- **Minimal Impact**: Only touch what's necessary. Avoid introducing bugs.
- **Verify Before Done**: Prove it works — run tests, check logs, demonstrate correctness.
