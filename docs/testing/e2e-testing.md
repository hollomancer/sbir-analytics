# End-to-End Testing

**Type**: Testing Guide

**Owner**: Engineering Team

**Last-Reviewed**: 2026-08-03

**Status**: Active

End-to-end tests live in `tests/e2e/`. They exercise pipeline behavior across component boundaries,
including scenarios that require Neo4j. The scenario runner is `scripts/run_e2e_tests.py`.

## Preferred Docker workflow

Copy the example environment once and set local test credentials:

```bash
cp .env.example .env
```

Then run a scenario through the Compose `ci` profile:

```bash
make docker-e2e-minimal
make docker-e2e-standard
make docker-e2e-large
make docker-e2e-edge-cases
```

`make docker-e2e` uses `E2E_TEST_SCENARIO` directly and leaves containers running for inspection:

```bash
E2E_TEST_SCENARIO=standard make docker-e2e
make docker-logs SERVICE=app
make docker-e2e-clean
```

The non-minimal scenarios create HTML coverage under `/app/artifacts/htmlcov` in the test
container. Use `make docker-e2e-debug` for an interactive shell in the same image.

## Running the scenario runner directly

A direct host run requires these variables because the runner validates them before pytest starts:

```bash
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=password
export SBIR_ETL__NEO4J__BOLT_URL=bolt://localhost:7687

uv run python scripts/run_e2e_tests.py --scenario minimal --timeout 120
```

Supported scenarios are:

| Scenario | Pytest selection |
| --- | --- |
| `minimal` | Excludes `slow` and `large_dataset` |
| `standard` | Excludes `large_dataset` |
| `large` | Runs all E2E markers |
| `edge-cases` | Selects `edge_case` |

The descriptions and expected durations printed by the runner are planning estimates, not CI
service-level guarantees. The `--timeout` value defaults to 600 seconds. When `pytest-timeout` is
installed it is also applied per test; the runner always enforces an overall subprocess timeout.

## Test structure

Important shared helpers are intentionally small:

- `tests/e2e/pipeline_validator.py` validates pipeline outputs and quality conditions.
- `tests/e2e/validation_models.py` defines validation result models.
- `tests/fixtures/enrichment_scenarios.json` contains enrichment scenarios.
- `tests/e2e/transition/` covers the transition pipeline and graph queries.

List the current tests rather than relying on a static count:

```bash
uv run pytest tests/e2e/ --collect-only -q
```

## GitHub Actions coverage

`.github/workflows/ci.yml` is the only workflow. Pull requests run fast unit-test shards. Pushes to
`main` and manual workflow runs execute the whole `tests/` tree with Neo4j, subject to the explicit
deselections documented in the workflow.

CI does not currently invoke the Docker E2E Make targets. GitHub Actions is test-only and never
runs extraction, enrichment, reporting, or live Dagster materializations.

## Troubleshooting

If the runner stops before pytest, check the three required Neo4j variables above. If Compose
fails, inspect service logs and configuration:

```bash
docker compose --profile ci config -q
make docker-logs SERVICE=app
make docker-logs SERVICE=neo4j
```

Clean volumes between incompatible graph states with `make docker-e2e-clean`. This removes only the
test Compose environment; never use the development checkout for live-stack operations.
