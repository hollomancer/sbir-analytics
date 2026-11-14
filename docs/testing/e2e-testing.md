# End-to-End Testing

**Type**: Testing Guide

**Maintainer**: Conrad Hollomon

**Last-Reviewed**: 2026-08-03

**Status**: Active

End-to-end tests live in `tests/e2e/`. They execute production Dagster jobs from persisted,
deterministic fixtures and validate their emitted products and asset checks. Mock-only checks and
direct composition of helpers belong in unit or integration suites. The scenario runner is
`scripts/run_e2e_tests.py`.

## Preferred Docker workflow

Copy the example environment once and set local test credentials:

```bash
cp .env.example .env
```

Then run a scenario through the Compose `ci` profile:

```bash
make docker-e2e-minimal
make docker-e2e-standard
```

`make docker-e2e` uses `E2E_TEST_SCENARIO` directly and leaves containers running for inspection:

```bash
E2E_TEST_SCENARIO=standard make docker-e2e
make docker-logs SERVICE=app
make docker-e2e-clean
```

The non-minimal scenario creates branch-aware HTML coverage under `artifacts/htmlcov` (mounted as
`/app/artifacts/htmlcov` in the test container). Use `make docker-e2e-debug` for an interactive shell
in the same image. Override the host path with `E2E_ARTIFACT_DIR` when needed.

## Running the scenario runner directly

Run the scenario runner from the installed workspace:

```bash
ENVIRONMENT=test uv run python scripts/run_e2e_tests.py --scenario minimal --timeout 120
```

Supported scenarios are:

| Scenario | Pytest selection |
| --- | --- |
| `minimal` | Selects the `smoke` job and excludes `requires_api` and `real_data` |
| `standard` | Excludes `requires_api` and `real_data` |

The descriptions and expected durations printed by the runner are planning estimates, not CI
service-level guarantees. The `--timeout` value defaults to 600 seconds. When `pytest-timeout` is
installed it is also applied per test; the runner always enforces an overall subprocess timeout.

## Test structure

The current hermetic scenarios are:

- `test_enrichment_job.py`: persisted freshness records and enriched awards through the production
  USAspending freshness-selection job and asset check, with API construction prohibited.
- `test_nsf_defense_lineage.py`: pinned CSV, JSON, and Parquet sources through the production
  lineage job, release validation, static network-file publication, and deterministic replay.

Synthetic fiscal, multi-source enrichment, and transition chains live under `tests/integration/`.
Mocked pipeline-validator contracts live under `tests/unit/`.

List the current tests rather than relying on a static count:

```bash
uv run pytest tests/e2e/ --collect-only -q
```

## GitHub Actions coverage

`.github/workflows/ci.yml` is the only workflow. Pull requests run the hermetic E2E selection in
addition to fast unit-test shards. Pushes to `main`, weekly scheduled runs, and manual workflow runs
execute the whole `tests/` tree, subject to the explicit deselections documented in the
workflow.

CI does not currently invoke the Docker E2E Make targets. GitHub Actions is test-only and never
runs extraction, enrichment, reporting, or live Dagster materializations.

## Troubleshooting

If Compose fails, inspect service logs and configuration:

```bash
docker compose --profile ci config -q
make docker-logs SERVICE=app
```

Clean test volumes with `make docker-e2e-clean`. This removes only the
test Compose environment; never use the development checkout for live-stack operations.
