# Test Scheduling Recommendations

## Executive Summary

**Current State**: 294 tests collected, ~40s collection time, multiple test suites run on every commit
**Problem**: Slow CI feedback loop, redundant test execution, inefficient resource usage
**Solution**: Tiered test execution based on speed, criticality, and change frequency

## Test Classification

### Tier 1: Pre-Commit (< 2 minutes total)
**When**: On every commit/PR
**Goal**: Fast feedback on basic correctness

#### Tests to Include:
- **Fast unit tests** (`@pytest.mark.fast`)
  - Model validation tests
  - Configuration schema tests
  - Pure function tests (no I/O)
  - Data transformation logic

- **Static analysis** (already in place)
  - Ruff lint/format
  - MyPy type checking
  - Bandit security scan

#### Estimated Runtime: 1-2 minutes

#### Implementation:
```yaml
# .github/workflows/ci.yml - fast-tests job
pytest -m "fast and not integration and not e2e" -n auto --maxfail=5
```

---

### Tier 2: PR Validation (< 10 minutes total)
**When**: On PR creation/update
**Goal**: Comprehensive validation before merge

#### Tests to Include:
- **All Tier 1 tests**
- **Integration tests** (conditional on changed files)
  - Neo4j integration (only if graph/loader changes)
  - API integration (only if enricher changes)
  - Database integration (only if extractor changes)

- **Path-based test selection**:
  - CET tests → only if `src/ml/**` or `config/cet/**` changed
  - Transition tests → only if `src/transition/**` changed
  - Fiscal tests → only if `src/enrichers/fiscal/**` changed

#### Estimated Runtime: 5-10 minutes

#### Implementation:
```yaml
# Use existing detect-changes action
- if: steps.detect.outputs.cet == 'true'
  run: pytest tests/unit/ml/ tests/integration/test_cet_*.py -n auto

- if: steps.detect.outputs.transition == 'true'
  run: pytest tests/unit/transition/ tests/e2e/transition/ -n auto
```

---

### Tier 3: Nightly (< 30 minutes total)
**When**: Once per day at 3 AM UTC
**Goal**: Catch integration issues and slow tests

#### Tests to Include:
- **Slow unit tests** (`@pytest.mark.slow`)
  - Large dataset processing tests
  - Performance benchmarks
  - Comprehensive validation tests

- **Full integration suite**
  - All Neo4j integration tests
  - All API integration tests
  - Multi-source enrichment tests

- **E2E smoke tests**
  - Pipeline validation
  - End-to-end enrichment flow
  - Graph query validation

#### Estimated Runtime: 20-30 minutes

#### Current Implementation: Already in `.github/workflows/nightly.yml`

---

### Tier 4: Weekly (< 2 hours total)
**When**: Sunday at 2 AM UTC
**Goal**: Comprehensive validation and data quality checks

#### Tests to Include:
- **Full E2E test suite**
  - Complete pipeline runs
  - Real data validation (`@pytest.mark.real_data`)
  - CET training and classification
  - Transition detection full pipeline

- **Performance regression tests**
  - Enrichment performance benchmarks
  - Database query performance
  - Memory usage profiling

- **Data quality validation**
  - Taxonomy completeness checks
  - Schema validation against production data
  - Data drift detection

#### Estimated Runtime: 1-2 hours

#### Implementation:
```yaml
# New workflow: .github/workflows/weekly.yml
on:
  schedule:
    - cron: "0 2 * * 0"  # Sunday 2 AM UTC
```

---

## Redundant/Unnecessary Tests

### Tests to Remove or Consolidate:

1. **Duplicate validation tests** (tests/validation/test_categorization_validation.py - 1513 lines)
   - **Issue**: Overlaps with unit tests in tests/unit/models/
   - **Action**: Remove or move to weekly validation suite
   - **Savings**: ~2-3 minutes

2. **Redundant Docker tests**
   - **Issue**: Docker build tested on every commit even when Dockerfile unchanged
   - **Action**: Only run on Dockerfile/docker-compose.yml changes (already implemented)
   - **Savings**: ~5 minutes when skipped

3. **Full CET pipeline on every commit**
   - **Issue**: CET training/classification runs even when CET code unchanged
   - **Action**: Move to nightly, only run on CET changes in CI
   - **Savings**: ~3-5 minutes

4. **Performance regression on every commit**
   - **Issue**: Runs even when enrichment code unchanged
   - **Action**: Already conditional, but move baseline comparison to nightly
   - **Savings**: ~2 minutes

5. **Multiple Neo4j integration tests**
   - **Issue**: Some tests overlap in coverage
   - **Action**: Consolidate similar tests, move comprehensive suite to nightly
   - **Savings**: ~3-4 minutes

---

## Recommended Changes

### 1. Update pytest markers
```toml
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "fast: fast unit tests (< 1 second each) - run on every commit",
    "integration: integration tests - run on PR",
    "slow: long-running tests - run nightly",
    "e2e: end-to-end tests - run nightly/weekly",
    "real_data: tests using real data - run weekly",
    "weekly: comprehensive validation - run weekly only"
]
```

### 2. Mark tests appropriately
```python
# Fast tests (< 1s each)
@pytest.mark.fast
def test_award_validation():
    ...

# Integration tests (1-10s each)
@pytest.mark.integration
def test_neo4j_connection():
    ...

# Slow tests (> 10s each)
@pytest.mark.slow
def test_large_dataset_processing():
    ...

# Weekly comprehensive tests
@pytest.mark.weekly
@pytest.mark.real_data
def test_full_pipeline_with_real_data():
    ...
```

### 3. Update CI workflow
```yaml
# .github/workflows/ci.yml

# On every commit (Tier 1)
fast-tests:
  run: pytest -m "fast" -n auto --maxfail=5

# On PR (Tier 2) - conditional
integration-tests:
  if: needs.detect-changes.outputs.integration-needed == 'true'
  run: pytest -m "integration and not slow" -n auto

# Nightly (Tier 3)
nightly-tests:
  run: pytest -m "slow or (integration and not fast)" -n auto

# Weekly (Tier 4)
weekly-tests:
  run: pytest -m "e2e or real_data or weekly" -n auto
```

### 4. Create weekly workflow
```yaml
# .github/workflows/weekly.yml
name: Weekly Comprehensive Tests

on:
  schedule:
    - cron: "0 2 * * 0"  # Sunday 2 AM UTC
  workflow_dispatch:

jobs:
  comprehensive-tests:
    runs-on: ubuntu-latest
    timeout-minutes: 120
    steps:
      - uses: actions/checkout@v4
      - uses: ./.github/actions/setup-python-uv
      - name: Run comprehensive test suite
        run: |
          pytest -m "e2e or real_data or weekly" \
            --cov=src \
            --cov-report=html \
            --cov-report=term \
            -n auto \
            --timeout=300
```

---

## Expected Impact

### Before:
- **Every commit**: ~15-20 minutes (all tests)
- **Nightly**: ~30 minutes (duplicate of commit tests + slow tests)
- **Weekly**: Not implemented

### After:
- **Every commit**: ~2 minutes (fast tests only)
- **PR validation**: ~5-10 minutes (conditional integration tests)
- **Nightly**: ~20-30 minutes (slow + integration tests)
- **Weekly**: ~1-2 hours (comprehensive validation)

### Benefits:
- **87% faster feedback** on commits (20min → 2min)
- **Reduced CI costs** (fewer redundant test runs)
- **Better resource utilization** (heavy tests run when needed)
- **Maintained coverage** (comprehensive tests still run regularly)

---

## Migration Plan

### Phase 1: Mark existing tests (Week 1)
1. Add `@pytest.mark.fast` to unit tests < 1s
2. Add `@pytest.mark.slow` to tests > 10s
3. Add `@pytest.mark.weekly` to comprehensive tests

### Phase 2: Update CI workflows (Week 1)
1. Modify ci.yml to run only fast tests on commit
2. Add conditional integration tests on PR
3. Update nightly.yml to run slow tests

### Phase 3: Create weekly workflow (Week 2)
1. Create weekly.yml for comprehensive tests
2. Move real_data tests to weekly
3. Add performance profiling to weekly

### Phase 4: Remove redundancies (Week 2)
1. Consolidate duplicate validation tests
2. Remove overlapping integration tests
3. Optimize test fixtures and setup

### Phase 5: Monitor and adjust (Ongoing)
1. Track CI execution times
2. Adjust test categorization as needed
3. Add new tests to appropriate tier

---

## Test Categorization Guide

### Fast Tests (< 1s each):
- Pure function tests
- Model validation
- Configuration parsing
- Data transformation
- String manipulation
- Math/calculation logic

### Integration Tests (1-10s each):
- Database connections
- API calls (mocked)
- File I/O
- External service integration
- Multi-component interaction

### Slow Tests (> 10s each):
- Large dataset processing
- Real API calls
- Complex graph queries
- Performance benchmarks
- Training ML models

### Weekly Tests:
- Full pipeline runs
- Real data validation
- Comprehensive E2E scenarios
- Data quality audits
- Performance profiling

---

## Monitoring Metrics

Track these metrics to validate improvements:

1. **CI execution time** (target: < 2min for commits)
2. **Test failure rate** (should remain constant)
3. **Coverage percentage** (should remain ≥ 85%)
4. **Time to feedback** (commit → test results)
5. **CI cost** (GitHub Actions minutes used)

---

## Appendix: Test Inventory

### Large Test Files (> 700 lines):
- `tests/validation/test_categorization_validation.py` (1513) → **Move to weekly**
- `tests/unit/transition/detection/test_detector.py` (1085) → **Split into fast/slow**
- `tests/unit/loaders/neo4j/test_transitions.py` (1040) → **Move to nightly**
- `tests/unit/enrichers/test_chunked_enrichment.py` (1029) → **Split into fast/slow**
- `tests/unit/assets/test_fiscal_assets.py` (997) → **Move to nightly**
- `tests/e2e/test_fiscal_stateio_pipeline.py` (869) → **Move to weekly**

### Test Markers Currently Used:
- `@pytest.mark.asyncio` (58 tests)
- `@pytest.mark.integration` (16 tests)
- `@pytest.mark.slow` (6 tests)
- `@pytest.mark.real_data` (5 tests)
- `@pytest.mark.fast` (1 test) ← **Need to add more**

### Recommended Marker Distribution:
- `@pytest.mark.fast`: ~150-200 tests (50-70% of unit tests)
- `@pytest.mark.integration`: ~50-70 tests (current + new)
- `@pytest.mark.slow`: ~30-50 tests (current + reclassified)
- `@pytest.mark.weekly`: ~20-30 tests (E2E + real_data)
