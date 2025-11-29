# Test Improvement Roadmap

## Current State (2025-01-29)

- **3,745 tests** (154 unit files | 20 integration | 9 e2e)
- **89% pass rate** (131 failures - CRITICAL)
- **21% coverage** (target: 85%+)
- **Test execution**: ~60s unit tests

## Critical Issues (Fix Immediately)

### 1. Fix 131 Failing Tests ⚠️
**Impact**: Blocks CI confidence, masks real failures

**Breakdown**:
- Transition detection: 14 failures
- CET analyzer: 4 failures
- Reporting/analytics: 5 failures
- Config validation: 1 failure (brittle Pydantic assertion)
- Utils/misc: 107 failures

**Action**: Run `pytest tests/unit --lf` to see last failed tests, fix systematically

### 2. Add Test Markers
**Impact**: Can't skip slow tests, no smoke test suite

**Missing markers**:
```python
@pytest.mark.smoke      # Critical path (5-10 tests)
@pytest.mark.slow       # Tests >5s
@pytest.mark.regression # Known bug prevention
@pytest.mark.weekly     # Long-running tests
```

**Action**: Add to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
markers = [
    "smoke: Critical path smoke tests",
    "slow: Tests that take >5 seconds",
    "regression: Regression prevention tests",
    "weekly: Long-running tests for weekly CI",
    "integration: Integration tests",
    "e2e: End-to-end tests",
]
```

### 3. Brittle Assertions
**Impact**: Tests break with library updates

**Example** (tests/unit/config/test_schemas.py):
```python
# Bad: Breaks when Pydantic changes error format
assert 'must be a number' in str(exc_info.value)

# Good: Check exception type and key info
assert isinstance(exc_info.value, ValidationError)
assert 'completeness' in str(exc_info.value)
```

**Action**: Search for string assertions in error messages, replace with type checks

## High Priority (Week 1-2)

### 4. Add Smoke Tests (5-10 tests)
**Impact**: Fast feedback on critical paths

**Needed**:
- SBIR ingestion happy path
- Enrichment pipeline basic flow
- Neo4j connection and basic query
- Config loading
- Asset dependency resolution

**Template**:
```python
@pytest.mark.smoke
def test_sbir_ingestion_happy_path(tmp_path):
    """Verify core SBIR ingestion works end-to-end."""
    # Extract → Validate → Load (minimal data)
    pass
```

### 5. Missing Integration Tests (30+ needed)
**Impact**: No multi-component validation

**Critical gaps**:
- Full ETL pipeline (Extract → Validate → Enrich → Transform → Load)
- Quality gate blocking
- Enrichment fallback chain
- Asset dependency execution order
- S3/local fallback
- API rate limiting/retry

### 6. Missing E2E Tests (11+ needed)
**Impact**: No production workflow validation

**Critical gaps**:
- Weekly data refresh workflow
- Incremental enrichment pipeline
- CET classification full pipeline
- Patent ETL full pipeline
- Failure recovery scenarios

## Medium Priority (Month 1)

### 7. Coverage Gaps (0% coverage)
**Modules with 0% coverage**:
- `src/validators/` (all modules)
- `src/utils/reporting/` (all formats)
- `src/utils/text_normalization.py`
- `src/utils/usaspending_cache.py`
- `src/utils/statistical_reporter.py`

**Action**: Add unit tests for these modules first (highest ROI)

### 8. Test Organization
**Issues**:
- Duplicate fixtures across conftest.py files
- No shared test utilities
- Inconsistent mock patterns

**Action**: Create `tests/utils/` with:
- `builders.py` - Test data builders
- `assertions.py` - Custom assertions
- `mocks.py` - Mock factories

## Quick Wins (Can Do Today)

1. **Run and fix failing tests**:
   ```bash
   pytest tests/unit --lf -v  # Show last failed
   ```

2. **Add pytest markers to pyproject.toml** (see above)

3. **Mark existing slow tests**:
   ```bash
   # Find slow tests
   pytest tests/unit --durations=20
   # Add @pytest.mark.slow to tests >5s
   ```

4. **Fix brittle Pydantic assertion**:
   ```bash
   # tests/unit/config/test_schemas.py line ~150
   # Change string assertion to type check
   ```

5. **Add 1 smoke test** for SBIR ingestion

## Success Metrics (3 Months)

| Metric | Current | Target |
|--------|---------|--------|
| Pass rate | 89% | 100% |
| Coverage | 21% | 85%+ |
| Integration tests | 20 | 50+ |
| E2E tests | 9 | 20+ |
| CI time | ~60s | <15min |
| Flaky rate | Unknown | <1% |

## Priority Order

1. ✅ **Fix 131 failing tests** (blocks everything)
2. ✅ **Add test markers** (enables selective test runs)
3. ✅ **Add 5 smoke tests** (fast feedback)
4. ⬜ **Add 10 integration tests** (ETL, DB, API)
5. ⬜ **Add 5 e2e tests** (production workflows)
6. ⬜ **Increase coverage to 50%** (validators, utils)
7. ⬜ **Add 20 more integration tests**
8. ⬜ **Add 6 more e2e tests**
9. ⬜ **Increase coverage to 85%**

## Next Steps

**This Week**:
1. Fix failing tests (2-3 hours)
2. Add pytest markers (30 min)
3. Add 1 smoke test (1 hour)

**Next Week**:
1. Add 4 more smoke tests
2. Add 5 integration tests (ETL, quality gates)
3. Fix brittle assertions

**Month 1**:
1. Add 25 integration tests
2. Add 11 e2e tests
3. Increase coverage to 50%

See `docs/testing/test-evaluation-2025-01.md` for detailed analysis and specific test examples.
