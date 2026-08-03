---
Type: Overview
Owner: docs@project
Last-Reviewed: 2026-08-03
Status: active
---

# Testing Index

No operational SBIR/STTR data is committed to this repository. Unit tests use fixtures and mocks;
service-backed, E2E, and real-data checks require their declared local prerequisites.

## Install

Use Python 3.11 or 3.12 and install the full workspace:

```bash
make install
```

## Common commands

```bash
make test-unit
make test-integration
make test-functional
make test
make check
```

Use pytest directly for focused work:

```bash
uv run pytest tests/unit/path/to/test_module.py -vv
uv run pytest tests/unit/ -m "not slow" -n auto
uv run pytest tests/integration/ -v
uv run pytest --collect-only tests/e2e/ -q
```

Markers are registered in `pyproject.toml`; inspect that list before adding or documenting one.
`slow`, `integration`, `e2e`, `requires_api`, `real_data`, and scenario-specific markers communicate
prerequisites and execution cost.

## Docker and E2E

```bash
cp .env.example .env
make docker-test
make docker-e2e-minimal
make docker-e2e-standard
make docker-e2e-clean
```

See [End-to-End Testing](e2e-testing.md) for scenarios, required Neo4j variables, artifacts, and
troubleshooting.

## GitHub Actions

`.github/workflows/ci.yml` is the only workflow:

- Pull requests run quality, security, and four fast unit-test shards.
- Pushes to `main` and manual runs execute the full suite with Neo4j and coverage.
- Docker and setup-script checks are conditional on relevant file changes.
- GitHub Actions never performs extraction, enrichment, reporting, or live Dagster materialization.

See [Test Execution and Scheduling](test-scheduling.md) for the exact event matrix and
[Test Suite Inventory](test-suite-inventory.md) for integration/E2E boundaries.

## Test structure

```text
tests/unit/          isolated behavior
tests/integration/   component and service boundaries
tests/functional/    pipeline-level behavior
tests/e2e/           end-to-end scenarios
tests/golden/        stable output comparisons
tests/validation/    numerical/reference checks and operator programs
```

Prefer the narrowest layer that proves a behavior. Unit tests should not call public APIs. Tests
that need Neo4j, credentials, external data, or a real API must state and enforce that prerequisite.

## Related guides

- [Categorization Testing](categorization-testing.md)
- [Company Categorization Validation](validation-testing.md)
- [End-to-End Testing](e2e-testing.md)
- [Data quality contract](../steering/data-quality.md)
