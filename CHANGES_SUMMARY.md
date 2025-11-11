# Test Data Infrastructure Update

## Summary

Updated the test suite to support using real SBIR data from `data/raw/sbir/` in addition to the existing sample fixtures. This enables more comprehensive testing with production data while maintaining fast unit tests.

## Changes Made

### 1. Enhanced Test Fixtures (`tests/conftest.py`)

Added new pytest fixtures for flexible data source selection:

- **`sbir_sample_csv_path`** - Path to small sample fixture (100 records)
- **`sbir_award_data_csv_path`** - Path to real award data (~381MB, millions of records)
- **`sbir_company_csv_paths`** - Dictionary of agency-specific company CSV paths
- **`use_real_sbir_data`** - Helper to determine data source based on markers/env
- **`sbir_csv_path`** - Smart fixture that auto-selects sample or real data

### 2. Pytest Marker Configuration (`pyproject.toml`)

Added new test marker:
```python
"real_data: tests that use real SBIR data from data/raw/sbir/ instead of fixtures"
```

### 3. Updated Integration Tests

Modified integration tests to use new fixtures:

#### `tests/integration/test_sbir_ingestion_assets.py`
- Replaced hard-coded fixture path with `sbir_csv_path` fixture
- Removed assumption of 100 rows (now works with both sample and real data)
- Tests default to sample data but can use real data with `@pytest.mark.real_data`

#### `tests/integration/test_sbir_enrichment_pipeline.py`
- Replaced hard-coded fixture path with `sbir_csv_path` fixture
- Updated to support both sample and real data sources
- Tests remain fast by default, comprehensive when marked

### 4. Documentation

#### New: `tests/TEST_DATA.md`
Comprehensive guide covering:
- Overview of sample vs. real data
- How to use each fixture type
- Three methods for using real data (markers, env vars, direct access)
- Best practices for unit, integration, and E2E tests
- Performance considerations and optimization tips
- CI/CD recommendations
- Troubleshooting guide

#### Updated: `tests/fixtures/README.md`
- Added reference to main test data documentation
- Points users to real data options

## Usage Examples

### Default Behavior (Fast Tests)
```python
# Uses sample data (100 records)
def test_my_feature(sbir_csv_path):
    df = pd.read_csv(sbir_csv_path)
    # Fast test with sample data
```

### Using Real Data with Marker
```python
@pytest.mark.real_data
def test_with_production_data(sbir_csv_path):
    df = pd.read_csv(sbir_csv_path)
    # Uses real SBIR data from data/raw/sbir/
```

### Using Real Data with Environment Variable
```bash
USE_REAL_SBIR_DATA=1 pytest tests/integration/
```

### Direct Access to Specific Data
```python
def test_specific_source(sbir_award_data_csv_path, sbir_company_csv_paths):
    awards = pd.read_csv(sbir_award_data_csv_path)
    if 'nsf' in sbir_company_csv_paths:
        nsf_companies = pd.read_csv(sbir_company_csv_paths['nsf'])
```

## Benefits

1. **Flexibility** - Tests can use sample or real data without code changes
2. **Speed** - Unit tests remain fast with sample data by default
3. **Comprehensiveness** - Integration/E2E tests can use real data for validation
4. **Backwards Compatible** - Existing tests work without modification
5. **Well-Documented** - Clear guidelines for when and how to use each approach

## Git LFS Considerations

Real data files are stored in Git LFS:
```bash
git lfs pull --include="data/raw/sbir/*.csv"
```

Tests automatically skip if LFS files aren't available, preventing failures in environments without Git LFS.

## Test Organization

- **Unit tests** (`@pytest.mark.fast`) - Always use sample data
- **Integration tests** (`@pytest.mark.integration`) - Default to sample, optionally real
- **E2E tests** (`@pytest.mark.e2e`) - Often use real data with `@pytest.mark.real_data`

## Future Enhancements

Potential improvements:
1. Add fixture for sampling real data (e.g., first N rows)
2. Create agency-specific sample fixtures
3. Add performance benchmarking fixtures
4. Cache parsed real data for session reuse
