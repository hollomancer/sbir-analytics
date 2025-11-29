# Integration Test Failure Analysis

**Date**: 2025-11-29
**Total Tests**: 166
**Failures**: 138 (83%)
**Passing**: 28 (17%)

## Failure Categories

### 1. Neo4j Connection Failures (42 tests, 30%)

**Root Cause**: Neo4j not running locally

**Affected Tests**:
- `test_neo4j_client.py` (30 tests)
- `test_multi_key_merge.py` (8 tests)
- `test_transition_integration.py` (4 tests)

**Error**: `ConnectionRefusedError: [Errno 61] Connection refused` on `localhost:7687`

**Fix Options**:
1. **Skip when Neo4j unavailable** (Recommended):
   ```python
   @pytest.mark.skipif(not neo4j_available(), reason="Neo4j not running")
   ```

2. **Use pytest-docker** to start Neo4j automatically

3. **Mock Neo4j client** for unit-style tests

**Estimated Effort**: 2-3 hours to add skip decorators

### 2. CLI Tests - Missing CommandContext (5 tests, 4%)

**Root Cause**: Tests mock `src.cli.main.CommandContext` which doesn't exist

**Affected Tests**:
- `test_cli_integration.py::test_main_app_help`
- `test_cli_integration.py::test_status_summary_command`
- `test_cli_integration.py::test_metrics_latest_command`
- `test_cli_integration.py::test_ingest_dry_run`
- `test_cli_integration.py::test_error_handling`

**Error**: `AttributeError: <module 'src.cli.main'> does not have the attribute 'CommandContext'`

**Fix**: Remove `@patch("src.cli.main.CommandContext")` decorators and update tests to work with current CLI structure

**Estimated Effort**: 30 minutes

### 3. Patent ETL Tests (36 tests, 26%)

**Root Cause**: Likely missing test data files or Neo4j connection

**Affected**: `test_patent_etl_integration.py` (all tests)

**Needs Investigation**: Check if tests require:
- Sample patent CSV files
- Neo4j connection
- Specific test fixtures

**Estimated Effort**: 1-2 hours

### 4. Exception Handling Tests (10 tests, 7%)

**Root Cause**: Tests expect specific exception types or behaviors that may have changed

**Affected Tests**:
- `test_usaspending_api_invalid_method_raises_configuration_error`
- `test_company_enricher_missing_column_raises_validation_error`
- `test_economic_model_missing_columns_raises_validation_error`
- `test_neo4j_loader_without_driver_raises_configuration_error`
- Others

**Fix**: Update tests to match current exception handling implementation

**Estimated Effort**: 1 hour

### 5. Transition MVP Tests (6 tests, 4%)

**Root Cause**: Likely missing test data or Neo4j connection

**Affected**: `test_transition_mvp_chain.py`

**Estimated Effort**: 1 hour

### 6. SAM.gov Integration Tests (6 tests, 4%)

**Root Cause**: Missing test data files or API mocking issues

**Affected**: `test_sam_gov_integration.py`

**Estimated Effort**: 1 hour

### 7. PaECTER Client Tests (4 tests, 3%)

**Root Cause**: Missing HuggingFace model or API token

**Affected**: `test_paecter_client.py`

**Estimated Effort**: 30 minutes

### 8. CET/ML Tests (2 tests, 1%)

**Root Cause**: Missing training data or model files

**Affected**:
- `test_cet_training_and_classification.py`
- `test_cet_training_scale.py`

**Estimated Effort**: 1 hour

### 9. Configuration Tests (1 test, <1%)

**Root Cause**: Missing `config/prod.yaml` file

**Affected**: `test_load_prod_environment`

**Fix**: Create `config/prod.yaml` or skip test if file doesn't exist

**Estimated Effort**: 5 minutes

### 10. USAspending Tests (2 tests, 1%)

**Root Cause**: Unknown - needs investigation

**Affected**: `test_usaspending_iterative_enrichment.py`

**Estimated Effort**: 30 minutes

## Quick Wins (Can Fix Immediately)

### 1. CLI Tests (5 tests) - 30 minutes

Remove outdated `CommandContext` mocks:

```python
# Before
@patch("src.cli.main.CommandContext")
def test_main_app_help(self, mock_context_class: Mock, runner: CliRunner):
    ...

# After
def test_main_app_help(self, runner: CliRunner):
    ...
```

### 2. Configuration Test (1 test) - 5 minutes

Add skip decorator:

```python
@pytest.mark.skipif(not Path("config/prod.yaml").exists(), reason="prod config not present")
def test_load_prod_environment():
    ...
```

### 3. Neo4j Tests (42 tests) - 2 hours

Add skip decorator to all Neo4j tests:

```python
import pytest
from neo4j import GraphDatabase

def neo4j_available():
    try:
        driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "test"))
        driver.verify_connectivity()
        driver.close()
        return True
    except:
        return False

@pytest.mark.skipif(not neo4j_available(), reason="Neo4j not running")
class TestNeo4jClient:
    ...
```

**Total Quick Wins**: 48 tests fixed in ~3 hours

## Medium Effort Fixes

### 1. Exception Handling Tests (10 tests) - 1 hour

Update tests to match current exception types and messages.

### 2. Patent ETL Tests (36 tests) - 2 hours

- Add test data fixtures
- Mock Neo4j where appropriate
- Update assertions to match current implementation

### 3. Transition/SAM.gov Tests (12 tests) - 2 hours

- Add test data fixtures
- Mock external dependencies
- Update assertions

**Total Medium Effort**: 58 tests fixed in ~5 hours

## Long-Term Improvements

### 1. Test Data Management

**Problem**: Tests depend on external data files that may not exist

**Solution**:
- Create `tests/fixtures/data/` directory
- Add sample data files for all integration tests
- Document data requirements in test docstrings

**Effort**: 4-6 hours

### 2. Docker Test Environment

**Problem**: Tests require Neo4j, which may not be running

**Solution**:
- Add `pytest-docker` plugin
- Create `docker-compose.test.yml` for test services
- Auto-start/stop services during test runs

**Effort**: 2-3 hours

### 3. Test Categorization

**Problem**: Integration tests mixed with tests requiring external services

**Solution**:
- Add markers: `@pytest.mark.requires_neo4j`, `@pytest.mark.requires_data`
- Allow selective test execution: `pytest -m "not requires_neo4j"`
- Document markers in `pytest.ini`

**Effort**: 1-2 hours

## Recommended Action Plan

### Phase 1: Quick Wins (3 hours)

1. Fix CLI tests (remove CommandContext mocks)
2. Add Neo4j skip decorators
3. Fix configuration test

**Result**: 48 tests fixed (35% of failures)

### Phase 2: Medium Effort (5 hours)

1. Fix exception handling tests
2. Add test data fixtures
3. Update patent ETL tests
4. Fix transition/SAM.gov tests

**Result**: 58 more tests fixed (42% of failures)

### Phase 3: Investigation (4 hours)

1. Investigate remaining failures
2. Fix or skip tests that can't be fixed
3. Document known issues

**Result**: Remaining 32 tests addressed

**Total Effort**: 12 hours to fix all integration tests

## Alternative: Skip All Failing Tests

If time is limited, add skip markers to all failing tests:

```python
@pytest.mark.skip(reason="Needs Neo4j - see INTEGRATION_TEST_ANALYSIS.md")
def test_neo4j_connection():
    ...
```

**Effort**: 1 hour
**Result**: All tests pass (by skipping failures)
**Trade-off**: Lose test coverage, but CI passes

## Recommendation

**Do Phase 1 (Quick Wins)** to fix 48 tests in 3 hours. This addresses the most common failure patterns and provides immediate value.

**Defer Phase 2 and 3** until there's dedicated time for test infrastructure improvements.

## Related

- [Testing Strategy](docs/testing/testing-strategy.md)
- [Testing Index](docs/testing/index.md)
- [CI Configuration](.github/workflows/ci.yml)
