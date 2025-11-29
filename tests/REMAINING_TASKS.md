# Remaining Test Optimization Tasks

## Completed ✅

### High Priority
- ✅ Created consolidated config mocking utilities (`tests/utils/config_mocks.py`)
- ✅ Expanded test data generators (`tests/utils/fixtures.py`)
- ✅ Created domain-specific conftest files (transition, fiscal, loaders, enrichers, integration)
- ✅ Added pytest markers to 30+ test files
- ✅ Migrated 8+ high-impact test files to use consolidated config mocks

### Medium Priority
- ✅ Batch-added pytest markers to many utility, model, and quality test files
- ✅ Migrated additional test files (extractors, CLI, enrichers, transformers)

## Remaining Tasks

### 1. Replace Inline DataFrame Creation (Medium Priority)

**Status**: 93 matches across 26 files still have inline DataFrame creation

**Target Files** (highest impact):
- `tests/unit/utils/test_asset_column_helper.py` (12 matches)
- `tests/unit/utils/test_column_finder.py` (11 matches)
- `tests/unit/transition/analysis/test_analytics.py` (12 matches)
- `tests/unit/test_validators.py` (11 matches)
- `tests/unit/loaders/neo4j/test_transitions.py` (6 matches)
- `tests/unit/enrichers/test_company_enricher.py` (6 matches)
- `tests/unit/transformers/test_fiscal_component_calculator.py` (has fixture but could use generator)
- `tests/unit/transformers/test_fiscal_tax_estimator.py` (has fixture but could use generator)
- `tests/unit/transformers/test_fiscal_roi_calculator.py` (has fixture but could use generator)
- `tests/unit/transformers/test_fiscal_uncertainty_quantifier.py` (has fixture but could use generator)

**Action**: Replace `pd.DataFrame([{...}])` patterns with `create_sample_*_df()` functions from `tests/utils/fixtures.py`

**Example**:
```python
# Before:
df = pd.DataFrame([
    {"award_id": "A1", "company": "Acme"},
    {"award_id": "A2", "company": "Beta"}
])

# After:
from tests.utils.fixtures import create_sample_sbir_data
df = create_sample_sbir_data(num_awards=2)
```

### 2. Migrate More Config Mocks (Low-Medium Priority)

**Status**: Several files still have inline config mocks

**Target Files**:
- `tests/unit/loaders/neo4j/test_patents.py` - Already has markers, but could use consolidated configs
- `tests/unit/loaders/neo4j/test_cet.py` - Already has markers, but could use consolidated configs
- `tests/unit/enrichers/naics/test_core.py` - Has `sample_config` fixture (NAICSEnricherConfig), could potentially use consolidated utilities
- `tests/unit/cli/test_commands.py` - May have config mocks
- `tests/unit/cli/test_display.py` - May have config mocks

**Note**: Some files use domain-specific configs (like `NAICSEnricherConfig`) that may not benefit from the consolidated `PipelineConfig` mocks. Evaluate case-by-case.

### 3. Create Additional Domain-Specific Conftest Files (Low Priority)

**Potential New Conftest Files**:
- `tests/unit/transformers/conftest.py` - For fiscal transformer fixtures
  - `sample_impacts_df`
  - `sample_components_df`
  - `sample_tax_estimates_df`
  - `sample_scenario_results_df`

- `tests/unit/models/conftest.py` - For shared model test fixtures
  - Common model instances
  - Validation test helpers

- `tests/unit/extractors/conftest.py` - Already exists, could expand
  - More extractor-specific fixtures

**Action**: Move common fixtures from individual test files to domain conftest files

### 4. Add More Pytest Markers (Low Priority)

**Status**: Most high-impact files now have markers, but some may still be missing

**Remaining**:
- Check integration test files for `@pytest.mark.integration`
- Check e2e test files for `@pytest.mark.e2e`
- Add domain-specific markers where appropriate:
  - `@pytest.mark.transition` to transition tests
  - `@pytest.mark.fiscal` to fiscal tests
  - `@pytest.mark.cet` to CET tests
  - `@pytest.mark.neo4j` to Neo4j tests

### 5. Consolidate Similar Fixtures (Low Priority)

**Status**: 218 `@pytest.fixture` matches across 66 files

**Opportunities**:
- Review fixtures in similar test files for duplication
- Move common fixtures to appropriate conftest files
- Create helper functions for complex fixture setup

**Example**: Multiple files might have similar `sample_awards_df` fixtures that could be consolidated.

## Priority Recommendations

### Immediate (Quick Wins)
1. **Replace inline DataFrames in high-impact files** (2-3 hours)
   - Focus on files with 6+ matches: `test_asset_column_helper.py`, `test_column_finder.py`, `test_analytics.py`, `test_validators.py`
   - Create additional fixture generators if needed

2. **Create transformers conftest** (1 hour)
   - Move fiscal transformer fixtures to `tests/unit/transformers/conftest.py`
   - Reduces duplication across 4-5 fiscal transformer test files

### Short-term (1-2 days)
3. **Review and migrate remaining config mocks** (2-3 hours)
   - Evaluate which files would benefit from consolidated configs
   - Migrate 5-10 more files

4. **Add domain-specific markers** (1 hour)
   - Add `@pytest.mark.transition`, `@pytest.mark.fiscal`, etc. to relevant tests
   - Enables better test filtering: `pytest -m transition`

### Long-term (Optional)
5. **Consolidate similar fixtures** (3-4 hours)
   - Review all fixtures for duplication
   - Create shared fixtures in conftest files
   - Document fixture usage patterns

## Impact Summary

### Completed So Far
- **Config mocks**: ~15-20% reduction in duplicate config code
- **Pytest markers**: 30+ files updated (enables better test filtering)
- **Conftest files**: 5 domain-specific conftest files created
- **Code reduction**: Estimated 10-15% reduction in duplicate code

### Potential Remaining Impact
- **DataFrame fixtures**: ~5-10% additional reduction if all inline DataFrames replaced
- **Fixture consolidation**: ~3-5% additional reduction
- **Total potential**: ~20-30% reduction in duplicate test code

## Notes

- All changes should be backward compatible
- Can be done incrementally - no need to update everything at once
- Focus on high-impact files first (most duplication, most frequently used)
- Test after each batch of changes to ensure nothing breaks
