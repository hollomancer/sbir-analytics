# Codex Instructions

## Project

Graph-based ETL: SBIR awards → Neo4j. Dagster orchestration, DuckDB processing, Docker deployment.

**Intent / north star:** [docs/research-questions.md](docs/research-questions.md) is the canonical inventory of what this repo exists to answer. Use it to judge whether a proposed change serves a real question vs. adds incidental scope.

Architectural patterns and technical docs live in `docs/steering/`. Feature specs live in `specs/`.

## Live deployment

Before any deployment, server operation, or live Dagster materialization, read
[the Mac mini runbook](docs/deployment/mac-mini-server.md#live-instance-on-this-mac-mini).
The only live checkout is `/Users/conradhollomon/projects/sbir-analytics-server`;
never operate the live stack from the development checkout. Preserve
`.env.server`, `/Volumes/SSDmini/sbir-analytics`, and the Docker `dagster_home`
volume. Ingress must remain Tailscale Serve only; never enable Funnel.

## Agents

Custom agents in `.Codex/agents/`:

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

## Research and analysis workflow

Use a **notebook-first** workflow when the research question, cohort definition, matching rule,
statistical assumption, or visualization is still being explored.

- Start from `notebooks/_template.ipynb` and tie the notebook to a concrete entry in
  `docs/research-questions.md`.
- Reuse the closest notebook under `notebooks/examples/` as the working pattern. Track active and
  migrated investigations in `notebooks/BACKLOG.md`.
- Use notebooks for exploration, evidence inspection, sensitivity analysis, and narrative. Do not
  use them for scheduled jobs, downloads, database mutation, or the only implementation of a
  load-bearing published calculation.
- Import existing project functions and read canonical artifacts rather than copying logic from
  `sbir_etl/`, packages, or `scripts/data/` into cells.
- When an analysis is rerun, cited, scheduled, or consumed downstream, graduate its core into a
  typed, tested library module with a thin CLI. Keep the notebook as the research record and
  diagnostic front end.
- Record inputs, grain, keys, exclusions, as-of dates, assumptions, and deterministic seeds. Clear
  outputs and execution counts before committing.
- Build or update a figure verifier alongside any findings report. A passing notebook is not a
  substitute for publication checks.

Before implementing an exploratory analysis directly as a large Python script, agents must check
whether a notebook spike would answer the uncertain parts first. Before porting an existing script,
agents must preserve one canonical computation path and avoid notebook/script duplication.

## Testing

```bash
pytest tests/unit/           # Fast unit tests
pytest -m integration        # Integration tests
pytest -n auto               # Parallel execution
```

Transition scoring changes must maintain ≥85% precision benchmark.

## Releases and versioning

- Follow [Semantic Versioning 2.0.0](https://semver.org/) and the repository policy in
  [docs/steering/versioning.md](docs/steering/versioning.md).
- Treat the root project and all packages under `packages/` as one synchronized release.
- Release tags must be annotated and named `vMAJOR.MINOR.PATCH`; the version stored in every
  `pyproject.toml` and in `uv.lock` must match the tag without the `v` prefix.
- Do not move, replace, or reuse a published tag or version. Release corrections require a new
  version.
- Before proposing or preparing a release, classify user-visible changes since the latest release,
  select the required version increment, update all version metadata, run `uv lock`, and run
  `uv run python scripts/ci/check_versioning.py --tag vMAJOR.MINOR.PATCH`.

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
