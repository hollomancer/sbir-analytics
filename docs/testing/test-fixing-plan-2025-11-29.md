# Test Fixing Plan - 2025-11-29

## Current Status
- **Total tests**: 3,479
- **Passing**: 3,407 (97.9%)
- **Failing**: 40 (1.2%)
- **Skipped**: 34
- **Coverage**: 59%

## Goal
- **Target**: 100% passing tests
- **Coverage target**: Maintain or improve 59%

## Failure Categories

### 1. Missing Dependencies (3 tests)
- **plotly** module not installed
  - `test_generate_trend_dashboard_with_plotly`
  - `test_generate_distribution_dashboard`
  - `test_generate_comparison_dashboard`
- **Fix**: Add plotly to dev dependencies or skip tests if not installed

### 2. Missing/Moved Files (2 tests)
- `src/enrichers/naics_enricher.py` doesn't exist
  - `test_build_index_sampled`
  - `test_enrich_awards_with_index`
- **Fix**: Update imports or remove obsolete tests

### 3. Mock Configuration Issues (8 tests)
- Mock objects not properly configured
  - `test_extract_usaspending_from_config` - dict vs object attribute
  - `test_query_awards_empty_result` - Mock has no len()
  - `test_initialization_from_get_config` - missing _rate_limiter_lock
  - `test_enrich_award_extracts_metadata` - missing modification_number key
  - `test_load_parquet_s3_first` - missing function attribute
  - `test_get_nested_returns_default_when_not_found` - Mock comparison issue
  - `test_asset_uses_fixture` - Dagster context not provided
  - `test_transformation_assets_pipeline` - Dagster context not provided
- **Fix**: Update mock setup to match actual implementation

### 4. Assertion/Logic Errors (15 tests)
- Tests expecting different values than actual
  - `test_exact_duns_match` - expects 'duns-exact', gets 'uei-exact'
  - `test_handle_error_continue_on_error_true` - assert 0 > 0
  - `test_batch_detection_generator` - assert 0 > 0
  - `test_simple_phase_i_to_ii_progression` - 'transaction_id' vs 'award_id'
  - `test_map_hierarchical_4_digit` - returns None
  - `test_map_naics_to_bea_hierarchical` - 'default_fallback' vs 'hierarchical'
  - `test_apply_agency_branch_priors` - 80.0 vs 75.0
  - `test_batch_upsert_tracks_creates_and_updates` - 3 vs 1
  - `test_batch_upsert_handles_missing_key` - assertion failure
  - `test_compute_company_transition_rate_sorted` - True is True (always passes)
  - `test_compute_company_transition_rate_multiple_awards_per_company` - True is True
  - `test_calculate_category_distribution` - 0.2 not in dict values
  - `test_extract_signals_with_patents` - 2 vs 1
  - `test_calculate_patent_score_maximum` - 0.9 vs 0.89999...
  - `test_calculate_patent_score_with_tech_transfer` - 0.2 vs 0.19999...
- **Fix**: Update test expectations or fix implementation

### 5. Missing Attributes/Functions (3 tests)
- `test_format_demand_vector_empty_dataframe` - missing format_demand_vector_from_shocks
- `test_missing_confidence_field` - KeyError: 'confidence'
- `test_map_bea_excel` - assert 'NAICS' in columns
- **Fix**: Add missing functions or update test data

### 6. API/Network Errors (2 tests)
- `test_retry_on_timeout` - HTTP 404
- `test_rate_limit_error_raised` - HTTP 404
- **Fix**: Mock API responses properly

### 7. File Path Issues (3 tests)
- `test_set_saves_dataframe` - path comparison with glob pattern
- `test_generate_json_report` - path mismatch
- `test_build_matrix_with_no_cets` - False is False (always passes)
- **Fix**: Update path assertions

### 8. Validation Errors (2 tests)
- `test_valid_report_collection` - Pydantic validation error
- `test_signals_and_boosts_for_name_fuzzy` - context assertion
- **Fix**: Update test data to match schema

### 9. Caching Issues (1 test)
- `test_generate_embeddings_caching` - caching not working
- **Fix**: Update cache mock or implementation

## Priority Order

### High Priority (Quick Wins - 13 tests)
1. Add plotly to dev deps or skip (3 tests)
2. Remove/update obsolete naics_enricher tests (2 tests)
3. Fix simple assertion mismatches (8 tests)
   - UEI vs DUNS
   - Float precision (0.9 vs 0.89999)
   - Column name changes

### Medium Priority (Mock Fixes - 10 tests)
4. Fix mock configuration issues
5. Add missing Dagster context
6. Update mock API responses

### Low Priority (Complex Fixes - 17 tests)
7. Fix logic errors in complex tests
8. Update test data for validation
9. Fix path comparison issues
10. Investigate caching issues

## Estimated Effort
- **High Priority**: 1-2 hours
- **Medium Priority**: 2-3 hours
- **Low Priority**: 3-5 hours
- **Total**: 6-10 hours for 100% passing

## Recommendation
Given time constraints, focus on High Priority fixes first to get to ~90% passing rate quickly, then tackle Medium Priority for ~95%, and Low Priority as time allows.
