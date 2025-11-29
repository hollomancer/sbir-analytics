# Skipped Tests Analysis

**Date:** 2025-11-29
**Total Skipped:** 34 test cases

## Summary by Category

### 🔴 Missing Data Files (15 tests - 44%)

#### USAspending Data Missing (4 tests)
**Files:**
- `tests/unit/test_naics_enricher.py` (2 tests)
- `tests/unit/test_usaspending_index.py` (2 tests)

**Reason:** `usaspending zip not present`
**Impact:** Can't test USAspending enrichment logic
**Fix:** Add fixture or mock data

#### SBIR Sample Data Missing (2 tests)
**Files:**
- `tests/conftest.py` (2 fixtures)

**Reason:** `SBIR sample fixture not found` / `Real SBIR award data not found`
**Impact:** Tests that need real SBIR data can't run
**Fix:** Generate sample fixtures or use mocked data

#### NAICS Index Missing (2 tests)
**Files:**
- `tests/integration/test_naics_integration.py` (2 tests)

**Reason:** `naics index parquet not present`
**Impact:** Can't test NAICS enrichment integration
**Fix:** Generate index fixture or mock

#### BEA Excel File Missing (3 tests)
**Files:**
- `tests/unit/test_naics_to_bea.py` (3 tests)

**Reason:** `BEA Excel file not found` / `openpyxl not available` / `could not be loaded`
**Impact:** Can't test NAICS to BEA mapping
**Fix:** Add BEA fixture or mock

#### Multi-Source Enrichment Data Missing (2 tests)
**Files:**
- `tests/e2e/test_multi_source_enrichment.py` (2 tests)

**Reason:** Missing enrichment data sources
**Impact:** Can't test end-to-end enrichment
**Fix:** Add fixtures or mock external APIs

#### USPTO Data Missing (2 tests)
**Files:**
- `tests/unit/ml/test_uspto_ai_loader_dta.py` (2 tests)

**Reason:** `uspto_ai_loader module not importable` / `ingest_dta_to_duckdb not implemented`
**Impact:** Can't test USPTO AI loader
**Fix:** Implement or add fixtures

### 🟡 Missing Dependencies (5 tests - 15%)

#### Neo4j Driver Missing (3 tests)
**Files:**
- `tests/unit/test_cet_award_relationships.py` (2 tests)
- `tests/conftest.py` (1 fixture)

**Reason:** `neo4j driver missing` / `Neo4j not available`
**Impact:** Can't test Neo4j integration
**Fix:** Already handled with `@pytest.mark.skipif(not HAVE_NEO4J)` - correct approach

#### Pandas Not Available (2 tests)
**Files:**
- `tests/unit/utils/test_date_utils.py` (2 tests)

**Reason:** `pandas not available`
**Impact:** Can't test pandas-specific date utilities
**Fix:** Pandas should be in dependencies - investigate why it's missing

### 🟢 Intentionally Disabled (9 tests - 26%)

#### Validation No Longer Enforced (2 tests)
**Files:**
- `tests/unit/test_rawaward_parsing.py` (2 tests)

**Reason:** `Date validation no longer enforced` / `UEI validation no longer enforced`
**Impact:** Tests for removed validation logic
**Action:** ✅ Remove these tests (testing removed features)

#### Schema Changes (2 tests)
**Files:**
- `tests/unit/config/test_schemas.py` (2 tests)

**Reason:** `Schema no longer has generation attribute` / `Schema no longer has modules attribute`
**Impact:** Tests for removed schema fields
**Action:** ✅ Remove these tests (testing removed features)

#### Methods Not Implemented (3 tests)
**Files:**
- `tests/unit/extractors/test_usaspending_extractor.py` (3 tests)

**Reason:** `escape_identifier method doesn't exist` / `escape_string_literal method doesn't exist` / `columns parameter not implemented`
**Impact:** Tests for unimplemented features
**Action:** Either implement features or remove tests

#### USPTO Asset Checks Not Found (3 tests)
**Files:**
- `tests/unit/test_uspto_assets.py` (3 tests)

**Reason:** `uspto_rf_id_asset_check not found` / `uspto_completeness_asset_check not found` / `uspto_referential_asset_check not found`
**Impact:** Tests for removed/renamed asset checks
**Action:** Update tests to match current implementation or remove

### 🔵 Environment-Dependent (5 tests - 15%)

#### HuggingFace Token Required (1 test)
**Files:**
- `tests/integration/test_paecter_client.py` (1 test)

**Reason:** `HF_TOKEN environment variable required for API mode`
**Impact:** Can't test PaECTER API integration without token
**Action:** ✅ Correct - should skip without token

#### R Reference Implementation (1 test)
**Files:**
- `tests/validation/test_fiscal_reference_validation.py` (1 test)

**Reason:** `Requires R reference implementation`
**Impact:** Can't validate fiscal calculations against R
**Action:** ✅ Correct - optional validation

#### Parquet Unavailable (1 test)
**Files:**
- `tests/unit/ml/test_taxonomy_asset.py` (1 test)

**Reason:** `Parquet unavailable; checks JSON present but does not expose row data`
**Impact:** Can't test parquet-specific functionality
**Action:** Investigate why parquet is unavailable

#### Index Has No Entries (1 test)
**Files:**
- `tests/integration/test_naics_integration.py` (1 test)

**Reason:** `index has no entries`
**Impact:** Can't test with empty index
**Action:** Generate test data or mock

#### Award IDs Not Discovered (1 test)
**Files:**
- `tests/unit/test_naics_enricher.py` (1 test)

**Reason:** `no award ids discovered during index build`
**Impact:** Can't test enrichment without award IDs
**Action:** Generate test data or mock

## Recommendations

### High Priority - Remove Dead Tests (7 tests)

These test removed features and should be deleted:

```bash
# Remove tests for removed validation
# tests/unit/test_rawaward_parsing.py:77, 129

# Remove tests for removed schema fields
# tests/unit/config/test_schemas.py:457, 465

# Remove tests for unimplemented methods (or implement them)
# tests/unit/extractors/test_usaspending_extractor.py:132, 177, 433
```

**Action:**
```bash
# Option 1: Remove dead tests
git rm tests/unit/test_rawaward_parsing.py  # If entire file is dead
# Or remove specific test functions

# Option 2: Mark as xfail if planning to implement
@pytest.mark.xfail(reason="Not yet implemented")
```

### Medium Priority - Add Fixtures (15 tests)

Create minimal test fixtures for:

1. **USAspending data** (4 tests)
   - Create `tests/fixtures/usaspending_sample.zip`
   - Or mock the data in tests

2. **SBIR sample data** (2 tests)
   - Already have fixture generation - ensure it runs in CI
   - Or use smaller embedded fixtures

3. **NAICS index** (2 tests)
   - Generate minimal index fixture
   - Or mock the index

4. **BEA Excel** (3 tests)
   - Add minimal BEA mapping fixture
   - Or mock the Excel reading

5. **USPTO data** (2 tests)
   - Add minimal USPTO fixtures
   - Or implement the loader

6. **Multi-source enrichment** (2 tests)
   - Mock external APIs
   - Or add cached response fixtures

### Low Priority - Investigate (5 tests)

1. **Pandas not available** (2 tests)
   - Pandas should be in dependencies
   - Investigate why it's missing in test environment

2. **Parquet unavailable** (1 test)
   - Should have pyarrow installed
   - Check dependencies

3. **Empty indexes** (2 tests)
   - Ensure test data generation works
   - Or mock non-empty indexes

### Already Correct (7 tests)

These are correctly skipped:
- ✅ Neo4j driver missing (optional dependency)
- ✅ HF_TOKEN required (environment-specific)
- ✅ R reference implementation (optional validation)

## Implementation Plan

### Phase 1: Clean Up Dead Tests (30 min)

```bash
# 1. Remove tests for removed features
# Edit or remove:
# - tests/unit/test_rawaward_parsing.py (lines 77, 129)
# - tests/unit/config/test_schemas.py (lines 457, 465)
# - tests/unit/extractors/test_usaspending_extractor.py (lines 132, 177, 433)
# - tests/unit/test_uspto_assets.py (entire file if all checks removed)

# 2. Commit cleanup
git add tests/
git commit -m "test: remove tests for removed features"
```

### Phase 2: Add Minimal Fixtures (2 hours)

```bash
# 1. Create fixtures directory
mkdir -p tests/fixtures

# 2. Generate minimal fixtures
# - USAspending sample (100 records)
# - NAICS index (50 mappings)
# - BEA mapping (20 codes)
# - USPTO sample (10 patents)

# 3. Update tests to use fixtures
# 4. Commit fixtures
git add tests/fixtures/
git commit -m "test: add minimal fixtures for skipped tests"
```

### Phase 3: Investigate Dependencies (30 min)

```bash
# 1. Check why pandas/pyarrow might be missing
uv pip list | grep -E "pandas|pyarrow"

# 2. Ensure they're in pyproject.toml dependencies
# 3. Fix if missing
```

## Expected Impact

| Category | Tests | Action | Impact |
|----------|-------|--------|--------|
| Dead tests | 7 | Remove | Cleaner test suite |
| Missing fixtures | 15 | Add fixtures | 15 more tests running |
| Dependencies | 5 | Investigate | 5 more tests running |
| Correct skips | 7 | Keep | No change |

**Total:** 20 tests could be enabled (59% of skipped tests)

## Monitoring

After fixes:
1. Run `pytest --collect-only -m "not slow"` to see test count
2. Check for remaining skips: `pytest -v | grep SKIPPED`
3. Ensure CI runs all non-skipped tests
4. Track test coverage improvement

## Files to Update

### Remove/Update:
- `tests/unit/test_rawaward_parsing.py`
- `tests/unit/config/test_schemas.py`
- `tests/unit/extractors/test_usaspending_extractor.py`
- `tests/unit/test_uspto_assets.py`

### Add Fixtures:
- `tests/fixtures/usaspending_sample.zip`
- `tests/fixtures/naics_index.parquet`
- `tests/fixtures/bea_mapping.xlsx`
- `tests/fixtures/uspto_sample.json`
- `tests/fixtures/sbir_sample.csv`

### Investigate:
- `pyproject.toml` (ensure pandas, pyarrow in dependencies)
- Test environment setup
