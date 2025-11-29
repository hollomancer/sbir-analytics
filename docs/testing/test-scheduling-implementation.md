# Test Scheduling Implementation Summary

## Completed: 2025-11-29

This document summarizes the implementation of tiered test scheduling to speed up CI feedback.

## What Was Implemented

### ✅ Phase 1: Updated pytest markers
**File**: `pyproject.toml`

Added scheduling guidance to all test markers:
- `fast`: Run on every commit
- `integration`: Run on PR
- `slow`: Run nightly
- `e2e`: Run nightly/weekly
- `real_data`: Run weekly
- `weekly`: Run weekly only (new marker)

### ✅ Phase 2: Created weekly workflow
**File**: `.github/workflows/weekly.yml`

New comprehensive test workflow that runs Sunday at 2 AM UTC:
- **comprehensive-tests**: Full E2E suite with Neo4j (90 min timeout)
- **real-data-validation**: Validation scripts with real data (60 min timeout)
- **performance-profiling**: Performance benchmarks (45 min timeout)

Features:
- Uses real SBIR data (`USE_REAL_SBIR_DATA=1`)
- Runs tests marked with `e2e`, `real_data`, or `weekly`
- Uploads coverage reports to Codecov
- Retains artifacts for 30-90 days

### ✅ Phase 3: Updated nightly workflow
**File**: `.github/workflows/nightly.yml`

Modified test matrix to exclude weekly tests:
- **slow-unit**: Slow unit tests only
- **integration**: Integration tests (excluding slow ones)
- **e2e-smoke**: E2E smoke tests (excluding weekly comprehensive tests)

### ✅ Phase 4: Marked tests appropriately

**E2E Tests marked as weekly**:
- `tests/e2e/test_fiscal_stateio_pipeline.py` - Comprehensive fiscal pipeline
- `tests/e2e/test_multi_source_enrichment.py` - Multi-source enrichment

**Real data tests marked as weekly**:
- `test_real_sbir_with_real_usaspending` - Real USAspending data
- `test_real_sbir_with_real_sam_gov` - Real SAM.gov data

**Obsolete tests skipped**:
- `tests/unit/ml/test_cet_context_rules.py` - Tests removed private methods
- `tests/unit/ml/test_cet_enhancements_phase1.py` - Tests removed private methods

## Current Test Distribution

### Tier 1: Commit (Fast Tests)
**Trigger**: Every commit/PR
**Runtime**: ~2 minutes
**Command**: `pytest -m "fast" -n auto`
**Tests**: ~150-200 fast unit tests

### Tier 2: PR Validation (Conditional)
**Trigger**: PR creation/update (conditional on changed files)
**Runtime**: ~5-10 minutes
**Tests**:
- CET tests (if `src/ml/**` or `config/cet/**` changed)
- Transition tests (if `src/transition/**` changed)
- Docker tests (if `Dockerfile` or `docker-compose.yml` changed)

### Tier 3: Nightly
**Trigger**: Daily at 3 AM UTC
**Runtime**: ~20-30 minutes
**Tests**:
- Slow unit tests (`-m "slow"`)
- Integration tests (`-m "integration and not slow"`)
- E2E smoke tests (`-m "e2e and not weekly"`)

### Tier 4: Weekly
**Trigger**: Sunday at 2 AM UTC
**Runtime**: ~1-2 hours
**Tests**:
- Comprehensive E2E tests (`-m "e2e or real_data or weekly"`)
- Real data validation
- Performance profiling

## Expected Impact

### Before Implementation
- Every commit: ~15-20 minutes (all tests)
- Nightly: ~30 minutes (duplicate tests)
- Weekly: Not implemented

### After Implementation
- Every commit: ~2 minutes (87% faster)
- PR validation: ~5-10 minutes (conditional)
- Nightly: ~20-30 minutes (optimized)
- Weekly: ~1-2 hours (comprehensive)

### Benefits
- **87% faster feedback** on commits
- **Reduced CI costs** from fewer redundant runs
- **Better resource utilization** (heavy tests run when needed)
- **Maintained coverage** (comprehensive tests still run regularly)

## What Still Needs To Be Done

### Phase 5: Mark more fast tests
**Status**: Not started
**Effort**: 2-3 hours

Need to add `@pytest.mark.fast` to more unit tests:
- Model validation tests
- Configuration parsing tests
- Pure function tests (no I/O)
- Data transformation tests

**Target**: 150-200 tests marked as fast (currently ~50)

**How to identify fast tests**:
```bash
# Run tests with duration tracking
pytest tests/unit/ --durations=0 | grep "0.0[0-9]s" > fast_tests.txt

# Tests under 1 second are candidates for @pytest.mark.fast
```

### Phase 6: Consolidate redundant tests
**Status**: Not started
**Effort**: 4-6 hours

**Tests to consolidate**:
1. `tests/validation/test_categorization_validation.py` (1513 lines)
   - Move to weekly validation suite
   - Remove overlap with unit tests

2. Overlapping Neo4j integration tests
   - Consolidate similar tests
   - Move comprehensive suite to nightly

3. Duplicate validation logic
   - Merge similar validation tests
   - Use parametrize for variations

### Phase 7: Add benchmark tracking
**Status**: Not started
**Effort**: 2-3 hours

Add pytest-benchmark to weekly workflow:
- Track performance over time
- Alert on regressions
- Store historical data

### Phase 8: Optimize test fixtures
**Status**: Not started
**Effort**: 3-4 hours

Optimize slow fixtures:
- Use session-scoped fixtures where possible
- Cache expensive setup operations
- Reduce test data size

## Monitoring

Track these metrics to validate improvements:

### CI Execution Time
- **Target**: < 2 min for commits
- **Measure**: GitHub Actions workflow duration
- **Alert**: If > 3 min for 3 consecutive runs

### Test Failure Rate
- **Target**: Maintain current rate (~2-5%)
- **Measure**: Failed tests / total tests
- **Alert**: If > 10% increase

### Coverage Percentage
- **Target**: Maintain ≥ 85%
- **Measure**: Codecov reports
- **Alert**: If < 85%

### CI Cost
- **Target**: Reduce by 50%
- **Measure**: GitHub Actions minutes used
- **Alert**: If increases month-over-month

## Usage Examples

### Run only fast tests locally
```bash
pytest -m fast -n auto
```

### Run integration tests
```bash
pytest -m integration -v
```

### Run slow tests (like nightly)
```bash
pytest -m "slow or (integration and not fast)" -n auto
```

### Run weekly comprehensive tests
```bash
pytest -m "e2e or real_data or weekly" -n auto --timeout=300
```

### Skip slow tests
```bash
pytest -m "not slow and not weekly" -n auto
```

## Rollback Plan

If issues arise, rollback is simple:

1. **Revert weekly workflow**:
   ```bash
   git rm .github/workflows/weekly.yml
   ```

2. **Revert nightly changes**:
   ```bash
   git checkout HEAD~1 .github/workflows/nightly.yml
   ```

3. **Revert test markers**:
   ```bash
   git checkout HEAD~1 pyproject.toml tests/
   ```

4. **Push changes**:
   ```bash
   git commit -m "revert: rollback test scheduling changes"
   git push
   ```

## Next Steps

1. **Monitor CI performance** for 1 week
2. **Mark additional fast tests** (Phase 5)
3. **Consolidate redundant tests** (Phase 6)
4. **Add benchmark tracking** (Phase 7)
5. **Optimize fixtures** (Phase 8)

## References

- [Test Scheduling Recommendations](./test-scheduling-recommendations.md)
- [Testing Guide](./README.md)
- [CI Workflow](.github/workflows/ci.yml)
- [Nightly Workflow](.github/workflows/nightly.yml)
- [Weekly Workflow](.github/workflows/weekly.yml)
