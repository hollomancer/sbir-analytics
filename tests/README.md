# Test Suite Documentation

## Overview
Comprehensive test suite for the **SBIR Analytics** project with 3,400+ tests organized into:

- **unit/** – Fast, isolated tests (~3,400 tests, <20s)
- **integration/** – Tests requiring external services (Neo4j, APIs)
- **e2e/** – End-to-end pipeline scenarios
- **validation/** – Data validation scripts

## Quick Start
```bash
# Run all unit tests
uv run pytest tests/unit

# Run with coverage
uv run pytest tests/unit --cov=src --cov-report=html

# Run specific markers
uv run pytest -m "fast"           # Fast tests only
uv run pytest -m "not slow"       # Skip slow tests
uv run pytest -m "integration"    # Integration tests
```

## Fixture Organization

### Main conftest.py (`tests/conftest.py`)
Core fixtures available to all tests:
- `repo_root` - Repository root path
- `test_config` - Loaded pipeline configuration
- `sbir_csv_path` - Smart fixture (sample or real data)
- `neo4j_driver` - Session-scoped Neo4j connection
- Dependency check fixtures (`neo4j_available`, `pandas_available`, etc.)

### Domain Fixtures (`tests/conftest_shared.py`)
Import explicitly in subdirectory conftest.py files:
```python
from tests.conftest_shared import (
    neo4j_config, neo4j_client, neo4j_helper,
    sample_sbir_df, sample_award, sample_contract,
    default_config, mock_vendor_resolver,
)
```

### Mock Factories (`tests/mocks/`)
Reusable mock objects:
```python
from tests.mocks import Neo4jMocks, ConfigMocks, EnrichmentMocks

driver = Neo4jMocks.driver()
session = Neo4jMocks.session()
config = ConfigMocks.pipeline_config()
```

## Test Data Factories (`tests/factories.py`)

### Model Factories
```python
from tests.factories import AwardFactory, RawAwardFactory

# Single instance
award = AwardFactory.create(agency="DOD", phase="II")

# Batch creation
awards = AwardFactory.create_batch(10, agency="NASA")
```

### DataFrame Builders
```python
from tests.factories import DataFrameBuilder

# Fluent API for test DataFrames
df = (DataFrameBuilder.awards(10)
      .with_agency("DOD")
      .with_phase("II")
      .with_amount_range(100000, 500000)
      .build())

contracts_df = DataFrameBuilder.contracts(5).with_agency("NASA").build()
```

## Custom Assertions (`tests/assertions.py`)
```python
from tests.assertions import (
    assert_valid_award,
    assert_valid_cet_classification,
    assert_valid_neo4j_load_metrics,
    assert_dict_subset,
    assert_dataframe_has_columns,
    assert_no_null_values,
)
```

## Test Markers
Register in `conftest.py`, use with `@pytest.mark.<marker>`:

| Marker | Description |
|--------|-------------|
| `fast` | Tests completing in <1 second |
| `slow` | Tests taking >1 second |
| `integration` | Requires external services |
| `e2e` | End-to-end pipeline tests |
| `neo4j` | Requires Neo4j database |
| `requires_aws` | Requires AWS credentials |
| `requires_r` | Requires R/rpy2 |

## Writing Tests

### Best Practices
1. **Use factories** - Avoid inline test data creation
2. **Parametrize** - Use `@pytest.mark.parametrize` for variants
3. **Use shared assertions** - Import from `tests/assertions.py`
4. **Keep tests focused** - One concept per test
5. **Add docstrings** - Describe what's being tested

### Example Test
```python
import pytest
from tests.factories import AwardFactory
from tests.assertions import assert_valid_award

pytestmark = pytest.mark.fast

class TestAwardProcessing:
    """Tests for award processing logic."""

    @pytest.mark.parametrize("phase", ["I", "II", "III"])
    def test_process_award_by_phase(self, phase):
        """Test processing works for all phases."""
        award = AwardFactory.create(phase=phase)
        result = process_award(award)
        assert_valid_award(result)
        assert result.phase == phase
```

## Directory Structure
```
tests/
├── conftest.py              # Core fixtures, markers
├── conftest_shared.py       # Domain fixtures (import explicitly)
├── factories.py             # Test data factories
├── assertions.py            # Custom assertion helpers
├── mocks/                   # Mock factories
│   ├── neo4j.py
│   ├── config.py
│   └── enrichment.py
├── fixtures/                # Test data files
├── unit/                    # Unit tests by module
│   ├── assets/
│   ├── enrichers/
│   ├── loaders/
│   ├── models/
│   └── ...
├── integration/             # Integration tests
└── e2e/                     # End-to-end tests
```

## CI/CD
Tests run automatically via GitHub Actions:
- **ci.yml** - Runs on every PR (unit tests, linting)
- **weekly.yml** - Full test suite including slow tests
- **nightly.yml** - Security scans and smoke tests
