# Test Suite Documentation

## Test Categories

| Category | Purpose | External Services | Run Frequency |
| --- | --- | --- | --- |
| **Unit** | Single function/class isolation | None (all mocked) | Every commit |
| **Integration** | Multiple components working together | May require Neo4j | PR merge |
| **E2E** | Full pipeline from input to output | May require Neo4j, APIs | Nightly |
| **Functional** | User-facing behavior validation | Minimal | PR merge |

## Running Tests

```bash
# All tests (parallel)
uv run pytest

# Specific suites
uv run pytest tests/unit/
uv run pytest tests/integration/
uv run pytest tests/e2e/
uv run pytest tests/functional/

# Without parallelism (for debugging)
uv run pytest -n 0

# With coverage
uv run pytest --cov=src --cov-report=html
```

## Test Markers

```bash
# Skip slow tests
uv run pytest -m "not slow"

# Only Neo4j tests (requires running Neo4j)
uv run pytest -m neo4j

# Only integration tests
uv run pytest -m integration
```

## Directory Structure

```text
tests/
├── unit/                    # Isolated component tests
│   ├── models/             # Pydantic model tests
│   ├── extractors/         # Extractor unit tests
│   ├── enrichers/          # Enricher unit tests
│   ├── transformers/       # Transformer unit tests
│   └── ...
├── integration/            # Multi-component tests
│   ├── neo4j/             # Neo4j-specific integration
│   ├── cli/               # CLI integration tests
│   └── ...
├── e2e/                    # End-to-end pipeline tests
│   └── transition/        # Transition detection E2E
├── functional/             # User-facing behavior tests
├── fixtures/               # Shared test data
├── conftest.py            # Root fixtures
└── conftest_shared.py     # Shared fixture utilities
```

## Writing Tests

### When to use each category

- **Unit**: Testing a single function with mocked dependencies
- **Integration**: Testing component interactions (e.g., enricher + transformer)
- **E2E**: Testing complete data flow through pipeline
- **Functional**: Testing user-visible behavior (CLI, API responses)

### Fixtures

Common fixtures are defined in:

- `tests/conftest.py` - Root-level fixtures
- `tests/conftest_shared.py` - Shared utilities
- `tests/fixtures/` - Test data files

### Markers

Add appropriate markers to tests:

```python
import pytest

@pytest.mark.integration
def test_component_integration():
    ...

@pytest.mark.requires_neo4j
def test_neo4j_query():
    ...

@pytest.mark.slow
def test_large_dataset():
    ...
```

## CI Configuration

Tests run in CI with:

- `--dist=loadgroup` - Respects `@pytest.mark.xdist_group` for test isolation
- `-n auto` - Parallel execution across CPU cores
- Skips tests requiring unavailable services (Neo4j, R, external APIs)
