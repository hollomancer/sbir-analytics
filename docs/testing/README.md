# Testing Guide

> **Operational data caveat.** No SBIR/STTR award data is committed to this repository. The quick-start and unit-test commands below are for local development and should run against fixtures, mocks, or small local inputs. Integration, E2E, and full dataset reproduction require your own source/bulk data downloads, API credentials, and local services such as Neo4j; reproducing the complete analyses end-to-end is non-trivial.


Testing strategy and commands for the SBIR ETL pipeline.

## Quick Start

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=sbir_etl --cov-report=html

# Run specific test types
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest tests/e2e/
```

## Test Structure

```text
tests/
├── unit/           # Component-level tests (fast, no external deps)
├── integration/    # Multi-component tests (may need Neo4j)
├── e2e/            # End-to-end pipeline tests
├── fixtures/       # Shared test data
└── conftest.py     # Pytest configuration
```

## Running Tests

### Unit Tests (Fast)

```bash
uv run pytest tests/unit/ -v
```

### Integration Tests (Requires Neo4j)

```bash
make neo4j-up
uv run pytest tests/integration/ -v
```

### With Coverage

```bash
uv run pytest --cov=sbir_etl --cov-report=html
open htmlcov/index.html
```

## CI Testing

Tests run automatically on push via GitHub Actions. See `.github/workflows/ci.yml`.

## Related Guides

- [Testing Index](index.md) - Complete testing reference
- [E2E Testing](e2e-testing-guide.md) - End-to-end test guide
- [Neo4j Testing](neo4j-testing-environments-guide.md) - Database testing
