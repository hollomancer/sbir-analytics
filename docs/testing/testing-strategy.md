# Testing Strategy

**Audience**: Developers, QA
**Prerequisites**: [Testing Index](index.md)
**Related**: [E2E Testing Guide](e2e-testing-guide.md), [CI Sharding](ci-sharding-setup.md)
**Last Updated**: 2025-11-29

## Overview

Comprehensive testing strategy for SBIR ETL pipeline covering unit, integration, and E2E tests with clear coverage goals and improvement roadmap.

## Current State

- **Total Tests**: ~3,450 tests
- **Coverage**: 59% → Target: 80%
- **Test Types**: Unit (fast), Integration (slow), E2E (scenarios)
- **CI Runtime**: ~8-12 minutes (sharded)

## Test Pyramid

```text
        /\
       /E2E\         ~50 tests (scenarios)
      /------\
     /  Integ \      ~400 tests (components)
    /----------\
   /    Unit    \    ~3,000 tests (functions)
  /--------------\
```

### Unit Tests (Fast)

**Target**: 3,000+ tests, <1s each
**Coverage**: 70%+ for core modules
**Marker**: `@pytest.mark.fast`

**Focus Areas:**

- Data models and validation
- Configuration schemas
- Pure functions (no I/O)
- Business logic
- Transformers and enrichers

**Example:**

```python
@pytest.mark.fast
def test_award_validation():
    award = Award(award_id="123", amount=50000)
    assert award.is_valid()
```

### Integration Tests

**Target**: 400+ tests, <10s each
**Coverage**: 60%+ for integrations
**Marker**: `@pytest.mark.integration`

**Focus Areas:**

- Neo4j database operations
- API integrations (SAM.gov, USAspending)
- DuckDB queries
- File I/O operations

**Example:**

```python
@pytest.mark.integration
def test_neo4j_award_loading(neo4j_session):
    loader = AwardLoader(neo4j_session)
    loader.load_awards([test_award])
    assert neo4j_session.run("MATCH (a:Award) RETURN count(a)").single()[0] == 1
```

### E2E Tests

**Target**: 50+ tests, <5min each
**Coverage**: Critical user journeys
**Marker**: `@pytest.mark.e2e`

**Focus Areas:**

- Full pipeline execution
- Multi-stage workflows
- Data quality validation
- Performance benchmarks

**Example:**

```python
@pytest.mark.e2e
def test_sbir_ingestion_pipeline():
    result = execute_job("sbir_weekly_refresh_job")
    assert result.success
    assert result.output_for_node("validated_awards").row_count > 0
```

## Coverage Goals

### By Module

| Module | Current | Target | Priority |
|--------|---------|--------|----------|
| `loaders/` | 45% | 85% | High |
| `enrichers/` | 52% | 80% | High |
| `transformers/` | 68% | 80% | Medium |
| `extractors/` | 71% | 75% | Medium |
| `validators/` | 78% | 85% | Low |
| `models/` | 82% | 90% | Low |

### By Test Type

| Type | Current | Target |
|------|---------|--------|
| Unit | 65% | 75% |
| Integration | 45% | 65% |
| E2E | 30% | 50% |

## Improvement Roadmap

### Phase 1: Quick Wins (1-2 weeks)

**Goal**: Increase coverage to 65%

**Actions:**

1. Add unit tests for uncovered loaders
2. Add integration tests for enrichers
3. Fix flaky tests in CI
4. Add missing fixtures

**Estimated Effort**: 20-30 hours

### Phase 2: Integration Coverage (2-4 weeks)

**Goal**: Increase coverage to 70%

**Actions:**

1. Add Neo4j integration tests for all loaders
2. Add API integration tests for enrichers
3. Add DuckDB integration tests for extractors
4. Improve test data fixtures

**Estimated Effort**: 40-60 hours

### Phase 3: E2E Scenarios (4-6 weeks)

**Goal**: Increase coverage to 75%

**Actions:**

1. Add E2E tests for all major pipelines
2. Add performance regression tests
3. Add data quality validation tests
4. Add error handling tests

**Estimated Effort**: 60-80 hours

### Phase 4: Edge Cases (6-8 weeks)

**Goal**: Reach 80% coverage

**Actions:**

1. Add edge case tests for all modules
2. Add error recovery tests
3. Add concurrent execution tests
4. Add memory leak tests

**Estimated Effort**: 40-60 hours

## Test Organization

### Directory Structure

```text
tests/
├── unit/              # Fast unit tests
│   ├── loaders/
│   ├── enrichers/
│   ├── transformers/
│   └── models/
├── integration/       # Integration tests
│   ├── neo4j/
│   ├── api/
│   └── duckdb/
├── e2e/              # End-to-end tests
│   ├── pipelines/
│   ├── scenarios/
│   └── performance/
└── fixtures/         # Shared test data
```

### Naming Conventions

**Files**: `test_<module>_<component>.py`
**Functions**: `test_<function>_<scenario>()`
**Classes**: `Test<Component>`

**Examples:**

```python
# tests/unit/loaders/test_award_loader.py
def test_load_awards_success():
    pass

def test_load_awards_duplicate_handling():
    pass

# tests/integration/neo4j/test_award_loading.py
class TestAwardLoading:
    def test_batch_loading(self):
        pass

    def test_constraint_violations(self):
        pass
```

## Test Data Management

### Fixtures

**Shared fixtures** in `tests/fixtures/`:

- `sample_awards.json` - Sample SBIR awards
- `sample_patents.json` - Sample USPTO patents
- `sample_contracts.json` - Sample USAspending contracts

**Fixture functions** in `conftest.py`:

```python
@pytest.fixture
def sample_award():
    return Award(award_id="123", amount=50000)

@pytest.fixture
def neo4j_session():
    # Setup Neo4j test session
    yield session
    # Cleanup
```

### Test Data Generation

**Use factories for complex data:**

```python
from factory import Factory, Faker

class AwardFactory(Factory):
    class Meta:
        model = Award

    award_id = Faker('uuid4')
    amount = Faker('random_int', min=10000, max=1000000)
    company_name = Faker('company')
```

## CI/CD Integration

### GitHub Actions Workflows

**Fast Tests** (on every commit):

```yaml
- name: Run fast tests
  run: pytest -m fast -n auto --maxfail=5
```

**Full Tests** (on PR):

```yaml
- name: Run all tests
  run: pytest -v --cov=src --cov-report=xml
```

**E2E Tests** (nightly):

```yaml
- name: Run E2E tests
  run: pytest -m e2e --timeout=300
```

### Test Sharding

**Parallel execution** across 4 shards:

```yaml
strategy:
  matrix:
    shard: [1, 2, 3, 4]

steps:
  - run: pytest --shard-id=${{ matrix.shard }} --num-shards=4
```

See [CI Sharding Setup](ci-sharding-setup.md) for details.

## Performance Testing

### Benchmarks

**Track performance metrics:**

- Enrichment throughput (records/second)
- Neo4j loading speed (nodes/second)
- Memory usage (peak MB)
- Query response time (ms)

**Baseline**: `reports/benchmarks/baseline.json`

### Regression Detection

**Fail CI if performance degrades:**

```python
@pytest.mark.benchmark
def test_enrichment_performance(benchmark):
    result = benchmark(enrich_awards, sample_awards)
    assert result.throughput > 100  # records/second
```

See [Performance Testing for details.

## Quality Gates

### Coverage Thresholds

**Fail CI if coverage drops:**

```yaml
- name: Check coverage
  run: |
    pytest --cov=src --cov-fail-under=59
```

### Test Success Rate

**Require 100% pass rate:**

- No flaky tests allowed
- Fix or skip unstable tests
- Document known issues

### Code Quality

**Enforce standards:**

- Ruff linting (no errors)
- MyPy type checking (strict)
- Bandit security scan (no high severity)

## Best Practices

### Writing Tests

1. **One assertion per test** (when possible)
2. **Use descriptive names** (`test_load_awards_handles_duplicates`)
3. **Arrange-Act-Assert** pattern
4. **Mock external dependencies** in unit tests
5. **Use real services** in integration tests

### Test Maintenance

1. **Keep tests fast** (<1s for unit, <10s for integration)
2. **Avoid test interdependencies**
3. **Clean up after tests** (fixtures, temp files)
4. **Update tests with code changes**
5. **Remove obsolete tests**

### Debugging Tests

```bash
# Run single test with verbose output
pytest tests/unit/loaders/test_award_loader.py::test_load_awards -vv

# Run with debugger
pytest --pdb tests/unit/loaders/test_award_loader.py

# Run with print statements
pytest -s tests/unit/loaders/test_award_loader.py
```

## Metrics and Reporting

### Coverage Reports

**Generate HTML report:**

```bash
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

**Upload to Codecov:**

```yaml
- uses: codecov/codecov-action@v3
  with:
    files: ./coverage.xml
```

### Test Reports

**Generate JSON report:**

```bash
pytest --json-report --json-report-file=test-results.json
```

**View in CI:**

- GitHub Actions → Artifacts → `test-results.json`

## Completed Improvements

See [archive/testing/IMPROVEMENTS.md](../../archive/testing/IMPROVEMENTS.md) for historical improvements.

## Related Documentation

- [Testing Index](index.md) - Commands and workflows
- [E2E Testing Guide](e2e-testing-guide.md) - End-to-end scenarios
- [CI Sharding Setup](ci-sharding-setup.md) - Parallel test execution
- [Neo4j Testing Environments](neo4j-testing-environments-guide.md) - Graph database testing
- [Performance Testing - Benchmarks and regression detection
