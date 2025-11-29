# Action Plan for Remaining 96 Test Failures

## Current Status
- **Passing**: 3,515 / 3,611 (97.3%)
- **Failing**: 96 (2.7%)
- **Infrastructure**: ✅ Complete

## Failure Categories

### High Priority (Quick Wins - 20 tests)

#### 1. Inflation Adjuster (6 tests)
**Issue**: Logic/assertion mismatches
- `test_adjust_single_award_success` - Award year extraction failing
- `test_extract_award_year_from_year_column` - Column name mismatch
- `test_validate_adjustment_quality*` (3 tests) - Validation logic
- `test_adjust_awards_dataframe` - DataFrame processing

**Fix**: Review column name expectations and validation logic

#### 2. Chunked Enrichment (4 tests)
**Issue**: Assertion mismatches, KeyError
- `test_log_progress` - Logging assertion
- `test_enrich_chunk_success` - Count mismatch
- `test_process_to_dataframe_empty` - Missing column
- `test_process_streaming` - Count mismatch

**Fix**: Update test expectations or fix implementation

#### 3. Neo4j Client (3 tests)
**Issue**: Assertion mismatches
- `test_batch_upsert_handles_missing_key` - Error count
- `test_batch_upsert_tracks_creates_and_updates` - Count mismatch

**Fix**: Review batch operation logic

#### 4. NAICS Core (5 tests)
**Issue**: Logic issues
- `test_process_line_normalizes_naics_codes` - Set membership
- `test_process_line_filters_invalid_naics` - Filtering logic
- `test_load_from_zip_missing_file` - File system mock
- `test_load_handles_corrupt_zip_member` - KeyError
- `test_enrich_awards_empty_dataframe` - Column assertion

**Fix**: Review NAICS processing logic

#### 5. USAspending Client (2 tests)
**Issue**: Initialization and matching
- `test_initialization_from_get_config` - Config loading
- `test_exact_duns_match` - Matching logic

**Fix**: Review initialization and matching logic

### Medium Priority (Domain Logic - 40 tests)

#### Transition Detection (11 tests)
- Patent analyzer (4)
- CET analyzer (4)
- Detector (3)

**Issue**: Feature extraction and detection logic
**Fix**: Review transition detection algorithms

#### USPTO Extractors (7 tests)
- AI extractor (6)
- USAspending extractor (4)
- USPTO extractor (1)

**Issue**: Data extraction logic
**Fix**: Review extraction patterns

#### Quality/Dashboard (4 tests)
- Dashboard (3)
- Validators (1)

**Issue**: Quality metric calculations
**Fix**: Review quality thresholds

### Lower Priority (Integration/E2E - 36 tests)

#### E2E Tests (10 tests)
- Transition tests (6)
- Multi-source enrichment (2)
- Fiscal pipeline (1)
- Enrichment job (1)

**Issue**: End-to-end workflow issues
**Fix**: May pass once unit tests fixed

#### Integration Tests (2 tests)
- Transition MVP chain (2)

**Issue**: Integration workflow
**Fix**: Review integration patterns

#### Functional Tests (3 tests)
**Issue**: Functional workflow
**Fix**: Review functional patterns

#### Scattered Unit Tests (21 tests)
Various single failures across different modules

**Issue**: Domain-specific logic
**Fix**: Case-by-case review

## Recommended Approach

### Phase 1: Quick Wins (Target: 20 tests, 2-3 hours)
1. Fix inflation adjuster column names and logic (6 tests)
2. Fix chunked enrichment assertions (4 tests)
3. Fix Neo4j batch operation logic (3 tests)
4. Fix NAICS processing logic (5 tests)
5. Fix USAspending client issues (2 tests)

### Phase 2: Domain Logic (Target: 40 tests, 4-5 hours)
1. Review and fix transition detection logic (11 tests)
2. Review and fix USPTO extraction logic (7 tests)
3. Fix quality/dashboard calculations (4 tests)
4. Fix scattered unit test issues (18 tests)

### Phase 3: Integration/E2E (Target: 36 tests, 3-4 hours)
1. Re-run E2E tests after unit fixes (may auto-pass)
2. Fix remaining integration issues
3. Fix functional test issues

## Estimated Total Time
- **Phase 1**: 2-3 hours (20 tests)
- **Phase 2**: 4-5 hours (40 tests)
- **Phase 3**: 3-4 hours (36 tests)
- **Total**: 9-12 hours to reach 100% pass rate

## Next Steps

1. Start with Phase 1 (Quick Wins)
2. Focus on one category at a time
3. Commit after each category is fixed
4. Re-run full suite after each phase
5. Adjust plan based on results

## Notes

- Infrastructure is complete (fixtures, mocking, async support)
- Remaining failures are primarily logic/assertion issues
- Many E2E tests may pass once unit tests are fixed
- Test suite is already in good health at 97.3%
