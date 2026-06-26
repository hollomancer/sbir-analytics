---
Type: Overview
Owner: docs@project
Last-Reviewed: 2025-11-29
Status: active
---

# Testing Index

This is the authoritative reference for running and writing tests across the SBIR
ETL pipeline. Update it whenever commands, markers, or workflows change so other
docs can link here instead of duplicating instructions.

> **Operational data caveat.** No SBIR/STTR award data is committed to this
> repository. The quick-start and unit-test commands below are for local
> development and should run against fixtures, mocks, or small local inputs.
> Integration, E2E, and full dataset reproduction require your own source/bulk
> data downloads, API credentials, and local services such as Neo4j.

## 1. Local Python Execution

Use `uv` (preferred) or `pip`-managed virtualenvs with Python 3.11+.

### Run everything with coverage

```bash
uv run pytest -v --cov=sbir_etl
```

### Parallel execution (faster)

```bash
# Use all CPU cores
uv run pytest -n auto

# Use specific number of workers
uv run pytest -n 4

# Parallel with coverage (slower but thorough)
uv run pytest -n auto --cov=sbir_etl
```

### Tiered execution

| Tier | Command | Notes |
|------|---------|-------|
| Fast unit tests only | `uv run pytest -m fast -n auto` | No external deps, parallel |
| Unit & light integration | `uv run pytest tests/unit tests/integration -m "not slow" -n auto` | Fast feedback, no Docker |
| Slow / ML / heavy assets | `uv run pytest -m "slow"` | Requires local datasets |
| Specific file | `uv run pytest tests/unit/utils/test_metrics.py -vv` | Focused debugging |

### Useful markers

- `-m fast` – fast unit tests (<1s each)
- `-m "not slow"` – skip heavy tests
- `-m "slow"` – only heavy suites (ML, fiscal sensitivity, long-running assets)
- `-k "keyword"` – filter by file, function, or substring

## 2. Docker & Compose Workflows

| Scenario | Command | Description |
|----------|---------|-------------|
| CI mirror | `make docker-test` | Spins up the `ci` profile, runs `pytest` inside containers |
| E2E standard | `make docker-e2e-standard` | Full pipeline validation with default dataset |
| E2E large / performance | `make docker-e2e-large` | Large dataset benchmark suite |
| Tear down | `make docker-down` | Stop all containers |

Env vars: copy `.env.example` to `.env` and set `NEO4J_USER`, `NEO4J_PASSWORD` before running the Make targets.

## 3. CI/CD Reference

GitHub Actions workflows wire these commands:

- `.github/workflows/ci.yml` – runs `uv run pytest -v --cov=sbir_etl` plus lint/type checks.
- `.github/workflows/weekly.yml` – scheduled tests, nightly smoke/security checks, and weekly comprehensive suites.
- `.github/workflows/etl-pipeline.yml` – scheduled/manual ETL pipeline jobs, including USAspending ingestion.

Use `gh workflow run <name>` for manual triggers or inspect [Actions](https://github.com/<org>/<repo>/actions).

## 4. Performance & Regression

- Baseline metrics: `reports/benchmarks/baseline.json`
- Run local perf suite: `uv run python -m sbir_etl.cli.main benchmarks run --config config/base.yaml`
- Compare against baseline: `uv run python -m sbir_etl.cli.main benchmarks compare --baseline reports/benchmarks/baseline.json`
- Transition detection throughput: `uv run python scripts/performance/benchmark_transition_detection.py --sample-size 5000 --batch-size 250` (run inside `make docker-e2e-large` to match Dagster/Docker environments)
- Regression detection: `uv run python scripts/performance/detect_performance_regression.py --fail-on-regression`
- For Docker-based perf runs, use `make docker-e2e-large` and review `reports/performance/*.json`.

See [docs/guides/quality-assurance.md](../guides/quality-assurance.md) for thresholds and monitoring expectations.

## 5. Test Strategy

### Test pyramid

```text
        /\
       /E2E\         scenarios (full pipeline)
      /------\
     /  Integ \      component integrations (Neo4j, APIs, DuckDB)
    /----------\
   /    Unit    \    pure functions and business logic
  /--------------\
```

| Layer | Marker | Target speed | Focus |
|-------|--------|--------------|-------|
| Unit | `@pytest.mark.fast` | <1s each | Models, validation, config schemas, pure functions, transformers/enrichers |
| Integration | `@pytest.mark.integration` | <10s each | Neo4j operations, API integrations (SAM.gov, USAspending), DuckDB queries, file I/O |
| E2E | `@pytest.mark.e2e` | <5min each | Full pipeline runs, multi-stage workflows, data quality, performance |

### Coverage goals

Maintain overall coverage ≥85% (higher for loaders and enrichers). Priority by module:

| Module | Target | Priority |
|--------|--------|----------|
| `loaders/` | 85% | High |
| `enrichers/` | 80% | High |
| `transformers/` | 80% | Medium |
| `extractors/` | 75% | Medium |
| `validators/` | 85% | Low |
| `models/` | 90% | Low |

## 6. Conventions & Best Practices

### Naming

- **Files**: `test_<module>_<component>.py`
- **Functions**: `test_<function>_<scenario>()`
- **Classes**: `Test<Component>`

### Writing tests

1. Follow pytest naming conventions (`test_<unit>_<scenario>()`).
2. Prefer fixtures over ad-hoc setup/teardown; share fixtures via `conftest.py` and `tests/fixtures/`.
3. Mock external services for unit tests; reserve real API/DB calls for integration/e2e.
4. Use the Arrange-Act-Assert pattern and descriptive names.
5. Keep tests fast, independent, and clean up after themselves (fixtures, temp files).

### Quality gates

- Coverage is measured with pytest-cov and reported to Codecov; there is no hard `--cov-fail-under` gate in CI.
- 100% pass rate required — fix or skip flaky tests and document known issues.
- Ruff linting, MyPy type checking, and Bandit security scan must pass.

## 7. Supporting Guides

- [Neo4j Testing Environments](neo4j-testing-environments-guide.md) – Docker-based graph testing environments.
- [E2E Testing](e2e-testing.md) – architecture, scenarios, data prep, and CI integration.
- [CI Sharding Setup](ci-sharding-setup.md) – parallel test execution across shards.
- [Categorization Testing](categorization-testing.md) / [Validation Testing](validation-testing.md) – domain-specific instructions.

For broader context, review [Quality Assurance](../guides/quality-assurance.md) and the main [project README](../../README.md).

> ⚠️ Whenever you add a new Make target, pytest marker, or workflow, update this index and link to it from README/Quick Start instead of duplicating the command.
