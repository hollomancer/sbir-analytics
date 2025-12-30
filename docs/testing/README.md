# Testing Guide

Testing strategy and commands for the SBIR ETL pipeline.

## Quick Start

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html

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
uv run pytest --cov=src --cov-report=html
open htmlcov/index.html
```

## CI Testing

Tests run automatically on push via GitHub Actions. See `.github/workflows/ci.yml`.

## Related Guides

- [Testing Index](index.md) - Complete testing reference
- [E2E Testing](e2e-testing-guide.md) - End-to-end test guide
- [Neo4j Testing](neo4j-testing-environments-guide.md) - Database testing
