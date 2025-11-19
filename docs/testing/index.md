---
Type: Guide
Owner: docs@project
Last-Reviewed: 2025-01-15
Status: active

---

# Testing Index

This consolidated index captures the canonical commands and references for running tests across environments. Use it as the single source of truth and update it whenever commands change so other docs can link here instead of duplicating instructions.

## 1. Local Python Execution

Use `uv` (preferred) or `pip`-managed virtualenvs with Python 3.11+.

### Run everything with coverage

```bash
uv run pytest -v --cov=src
```

### Tiered execution

| Tier | Command | Notes |
|------|---------|-------|
| Unit & light integration | `uv run pytest tests/unit tests/integration -m "not slow"` | Fast feedback, no Docker |
| Slow / ML / heavy assets | `uv run pytest -m "slow"` | Requires local datasets |
| Specific file | `uv run pytest tests/unit/utils/test_metrics.py -vv` | Focused debugging |

### Useful markers

- `-m "not slow"` – skip heavy tests
- `-m "slow"` – only heavy suites (ML, fiscal sensitivity, long-running assets)
- `-k "keyword"` – filter by file, function, or substring

## 2. Docker & Compose Workflows

For parity with CI and to exercise full stacks (Neo4j, Dagster, DuckDB), use the Make targets backed by `docker-compose.yml` profiles (see [Containerization Guide](../deployment/containerization.md)).

| Scenario | Command | Description |
|----------|---------|-------------|
| CI mirror | `make docker-test` | Spins up the `ci` profile, runs `pytest` inside containers |
| E2E standard | `make docker-e2e-standard` | Full pipeline validation with default dataset |
| E2E large / performance | `make docker-e2e-large` | Large dataset benchmark suite |
| Tear down | `make docker-down` | Stop all containers |

Env vars: copy `.env.example` to `.env` and set `NEO4J_USER`, `NEO4J_PASSWORD` (or Aura credentials) before running the Make targets.

## 3. CI/CD Reference

GitHub Actions workflows wire these commands:

- `.github/workflows/ci.yml` – runs `uv run pytest -v --cov=src` plus lint/type checks.
- `.github/workflows/container-ci.yml` – executes `make docker-test` for Compose validation.
- `.github/workflows/performance-regression-check.yml` – reuses Docker images for regression metrics.

Use `gh workflow run <name>` for manual triggers or inspect [Actions](https://github.com/<org>/<repo>/actions).

## 4. Performance & Regression

- Baseline metrics: `reports/benchmarks/baseline.json`
- Run local perf suite: `uv run python -m src.cli.main benchmarks run --config config/base.yaml`
- Compare against baseline: `uv run python -m src.cli.main benchmarks compare --baseline reports/benchmarks/baseline.json`
- Transition detection throughput: `uv run python scripts/performance/benchmark_transition_detection.py --sample-size 5000 --batch-size 250` (run inside `make docker-e2e-large` to match Dagster/Docker environments)
- For Docker-based perf runs, use `make docker-e2e-large` and review `reports/performance/*.json`.

See [docs/performance](../performance) and [docs/guides/quality-assurance.md](../guides/quality-assurance.md) for thresholds and monitoring expectations.

## 5. Supporting Guides

- [Neo4j Testing Environments](neo4j-testing-environments-guide.md) – switch between local Docker and Aura for graph tests.
- [E2E Testing Guide](e2e-testing-guide.md) – scenarios, data prep, CI integration.
- [Test Coverage Strategy](test-coverage-strategy.md) – coverage goals and focus areas.
- [Categorization Testing](categorization-testing.md) / [Validation Testing](validation-testing.md) – domain-specific instructions.
- [CLI Testing Guide](../cli/TESTING.md) – CLI-specific fixtures and snapshot tests.

> ⚠️ Whenever you add a new Make target, pytest marker, or workflow, update this index and link to it from README/Quick Start instead of duplicating the command.
