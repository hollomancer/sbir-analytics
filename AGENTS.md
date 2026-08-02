# Agent Instructions

Project conventions for any AI coding agent working in this repository
(Claude Code, Codex, Cursor, Aider, and others). Tool-specific configuration
lives alongside this file — see [Tool-specific setup](#tool-specific-setup).

## Project

Graph-based ETL: SBIR awards → Neo4j. Dagster orchestration, DuckDB processing,
Docker deployment.

**Intent / north star:** [docs/research-questions.md](docs/research-questions.md)
is the canonical inventory of what this repo exists to answer. Use it to judge
whether a proposed change serves a real question or adds incidental scope.
[docs/research-plan-alignment.md](docs/research-plan-alignment.md) maps the same
work onto the M1–M5 delivery milestones and carries a crosswalk between the two
framings.

Architectural patterns and technical docs live in `docs/steering/`. Feature
specs live in `specs/`.

## Key directories

```text
sbir_etl/                 # Core ETL library (extractors, enrichers, transformers,
                          #   validators, models, config, quality, utils)
packages/
  sbir-analytics/         # Dagster assets, jobs, sensors
  sbir-graph/             # Neo4j loaders
  sbir-ml/                # ML models (CET, transition detection)
config/base.yaml          # Thresholds, paths, performance settings
docs/steering/            # Architectural patterns (neo4j, pipelines, data quality)
specs/                    # Per-feature requirements/design/tasks
```

## Commands

Prefer the `make` targets over hand-rolled invocations — they are the single
place kept in sync with CI. `make help` lists every target.

| Task | Command |
|------|---------|
| Install dependencies | `make install` (add `uv sync --all-extras --dev` for lint/type tooling) |
| Lint + type check | `make lint` |
| Auto-format and auto-fix | `make format` |
| Full test suite with coverage | `make test` |
| Start Dagster UI (localhost:3000) | `make dev` |

**Do not hand-roll `ruff`/`mypy` paths.** `make lint` mirrors
`.github/workflows/ci.yml` exactly: ruff over `sbir_etl`, all three
`packages/*`, and `tests`; mypy over `sbir_etl` and `packages/sbir-graph`
(blocking) plus `sbir-analytics` and `sbir-ml` (non-blocking, matching CI's
`continue-on-error`); then the repository hygiene guard. Checking only
`sbir_etl/` covers 205 of 783 files and will pass while CI fails. If you change
the lint scope, change it in `LINT_PATHS` in the `Makefile` **and** in
`ci.yml` — they are duplicated by necessity.

For the inner loop, the full suite is too slow. Use:

```bash
uv run pytest tests/unit/ -x -q -m "not slow"   # fast feedback while iterating
uv run pytest -m integration                     # integration tests
uv run pytest -n auto                            # parallel (default in addopts)
```

Run `make lint` and the full `make test` once before declaring work done.

## Testing

- Place tests in `tests/unit|integration|e2e/`.
- Fixtures: `tests/conftest.py`, `tests/conftest_shared.py`, and
  domain-specific `conftest.py` files in subdirectories. Neo4j integration
  tests use the `cleanup_test_data` fixture from `tests/integration/conftest.py`.
- Markers are registered in `pyproject.toml` — `fast`, `smoke`, `unit`,
  `integration`, `slow`, `e2e`, `neo4j`, `requires_neo4j`, `real_data`,
  `weekly`, `regression`, `performance`, `transition`, `fiscal`.
- `asyncio_mode = "auto"` — async tests need no explicit marker.
- Pydantic models are used extensively; check field validators first when a
  test fails on validation.
- **Transition scoring changes must maintain the ≥85% precision benchmark.**
  CI enforces this.

## Code standards

- Line length: 100. Target: Python 3.11 (`requires-python = ">=3.11,<3.13"`).
- Ruff rules: `E`, `W`, `F`, `I`, `B`, `C4`, `UP`.
- Use `StrEnum`, not `str, Enum`.
- Use `datetime.UTC`, not `timezone.utc`.
- **Do NOT use `from __future__ import annotations` in Dagster asset files** —
  it breaks runtime context type validation. This fails at runtime, not at
  lint time, so nothing will catch it for you.
- **Neo4j:** loaders live in `packages/sbir-graph/sbir_graph/loaders/`. Use
  `MERGE`, not `CREATE`, so loads stay idempotent.
- **Monitoring:** use the `sbir_etl.utils` decorators and `AlertCollector`.
- **CI:** workflows are in `.github/workflows/*.yml`; upload artifacts to
  `reports/`.

## Principles

- **Simplicity first.** The simplest change that solves the problem. No
  speculative abstractions, no "flexibility" that wasn't requested. If 200
  lines could be 50, rewrite it. Ask: would a senior engineer call this
  overcomplicated?
- **No laziness.** Root causes, not temporary fixes. Senior developer
  standards.
- **Surgical changes.** Only touch what the task requires. Don't "improve"
  adjacent code. Match existing style. If your changes orphan imports or
  variables, remove them — but don't remove pre-existing dead code unless
  asked. Every changed line should trace to the request.
- **Verify before done.** Prove it works: run tests, check logs, demonstrate
  correctness. Turn the task into verifiable steps:

  ```text
  1. [Step] → verify: [check]
  2. [Step] → verify: [check]
  ```

- **Report faithfully.** If tests fail, say so and show the output. If you
  skipped a step, say that. Don't describe work as verified when it wasn't.

## Scope discipline

This repo accumulates research questions faster than it can implement them, so
scope pressure is the normal failure mode. Before building something large:

1. Find the question it serves in
   [docs/research-questions.md](docs/research-questions.md) (policy areas A–F).
2. Find the milestone it advances in
   [docs/research-plan-alignment.md](docs/research-plan-alignment.md) (M1–M5),
   or confirm via the crosswalk there that the area has no milestone yet.
3. If neither lands, say so before writing code.

Common red flags: abstractions built for a single call site, YAML config for
values that will never change, test infrastructure that exceeds the value of
what it tests, dashboards before the analytical pipeline produces results, and
rebuilding awards-layer infrastructure that SAM.gov/USAspending already provide.

## Data and reproducibility

Award data is generally **not** committed — reproducing analyses means
downloading sources and supplying your own API credentials. The exceptions are
small reference tables in `data/reference/` (NAICS→BEA crosswalk, CMF registry,
state effective tax rates) and a 226-row CET classifier validation sample and
answer key. Don't commit bulk extracts.

## Tool-specific setup

- **Claude Code** — [CLAUDE.md](CLAUDE.md) adds the subagent roster
  (`.claude/agents/`) and skills (`.claude/skills/`). Everything in this file
  applies as well.
- **Other agents** — this file is the whole contract.
