# Test Data Guide

This document explains how test data is organized and how to use real SBIR data in tests.

## Overview

Tests can use two types of SBIR data:

1. **Sample Fixtures** (default) - Small, fast test data for unit and integration tests
2. **Real Data** - Full production SBIR datasets for comprehensive testing

## Data Sources

### Sample Fixtures

Located in `tests/fixtures/`:

- `sbir_sample.csv` - 100 representative SBIR award records
- Includes edge cases and validation test scenarios
- Fast to load (<1 second)
- Always committed to Git

### Real Data

Located in `data/raw/sbir/`:

- `award_data.csv` - Full SBIR award dataset (~381MB, millions of records)
- `*-company_search_*.csv` - Agency-specific company data files
  - NSF, NASA, DOD (AF, Army/Navy, Other), HHS/NIH, NIH Other, Other agencies

## Test Fixtures

The `tests/conftest.py` provides several fixtures for accessing SBIR data:

### Basic Fixtures

#### `sbir_sample_csv_path`

Returns path to the small sample fixture (100 records).

```python
def test_my_feature(sbir_sample_csv_path):
    df = pd.read_csv(sbir_sample_csv_path)
    assert len(df) == 100
```

#### `sbir_award_data_csv_path`

Returns path to the real award data (full dataset).

```python
@pytest.mark.real_data
def test_with_real_data(sbir_award_data_csv_path):
    df = pd.read_csv(sbir_award_data_csv_path)
    # Test with millions of real records
```

#### `sbir_company_csv_paths`

Returns dictionary of agency-specific company data paths.

```python
def test_company_data(sbir_company_csv_paths):
    if 'nsf' in sbir_company_csv_paths:
        nsf_df = pd.read_csv(sbir_company_csv_paths['nsf'])
        # Test with NSF company data
```

### Smart Fixture (Recommended)

#### `sbir_csv_path`

Automatically selects sample or real data based on test markers or environment.

```python
# Uses sample data by default (fast)
def test_basic_feature(sbir_csv_path):
    df = pd.read_csv(sbir_csv_path)
    assert len(df) > 0

# Uses real data when marked
@pytest.mark.real_data
def test_with_production_data(sbir_csv_path):
    df = pd.read_csv(sbir_csv_path)
    # Automatically gets real data
```

## Using Real Data in Tests

### Method 1: Pytest Marker (Recommended)

Mark individual tests or test classes to use real data:

```python
@pytest.mark.real_data
def test_large_dataset_handling(sbir_csv_path):
    """This test will use real SBIR data."""
    df = pd.read_csv(sbir_csv_path)
    # Process real data
```

### Method 2: Environment Variable

Set environment variable to use real data for all tests:

```bash
# Use real data for all tests
USE_REAL_SBIR_DATA=1 pytest tests/

# Use real data for specific test file
USE_REAL_SBIR_DATA=1 pytest tests/integration/test_sbir_enrichment_pipeline.py
```

### Method 3: Direct Fixture Access

Access specific data sources directly:

```python
def test_specific_data_source(sbir_award_data_csv_path, sbir_company_csv_paths):
    # Always use real award data
    awards_df = pd.read_csv(sbir_award_data_csv_path)

    # Use NSF company data if available
    if 'nsf' in sbir_company_csv_paths:
        nsf_df = pd.read_csv(sbir_company_csv_paths['nsf'])
```

## Test Markers

Tests can use the following markers:

- `@pytest.mark.fast` - Fast unit tests using sample data
- `@pytest.mark.integration` - Integration tests (default: sample data)
- `@pytest.mark.real_data` - Tests that use real SBIR data
- `@pytest.mark.slow` - Long-running tests (may use real data)
- `@pytest.mark.e2e` - End-to-end tests (may use real data)

## Best Practices

### For Unit Tests

- Use `@pytest.mark.fast` and sample data
- Keep tests under 1 second
- Mock external dependencies

```python
@pytest.mark.fast
def test_validator_logic(sbir_sample_csv_path):
    df = pd.read_csv(sbir_sample_csv_path)
    # Fast validation test
```

### For Integration Tests

- Default to sample data for speed
- Use `@pytest.mark.real_data` for comprehensive testing
- Consider data sampling for large datasets

```python
@pytest.mark.integration
def test_pipeline_with_sample(sbir_csv_path):
    """Fast integration test with sample data."""
    df = pd.read_csv(sbir_csv_path)
    # Process with sample (default)

@pytest.mark.integration
@pytest.mark.real_data
@pytest.mark.slow
def test_pipeline_with_real_data(sbir_csv_path):
    """Comprehensive test with real data."""
    df = pd.read_csv(sbir_csv_path, nrows=10000)  # Sample for performance
    # Process real data sample
```

### For E2E Tests

- Use real data for production validation
- May require longer timeouts
- Should be run less frequently

```python
@pytest.mark.e2e
@pytest.mark.real_data
@pytest.mark.slow
def test_full_etl_pipeline(sbir_award_data_csv_path):
    """Full pipeline test with real data."""
    # Complete ETL workflow
```

## Performance Considerations

### Sample Data

- Load time: <1 second
- Memory usage: <10 MB
- Best for: unit tests, fast CI

### Real Data (Performance)

- Load time: 10-60 seconds (full dataset)
- Memory usage: 2-4 GB (full dataset)
- Best for: comprehensive validation, production testing

### Tips for Large Datasets

1. **Sample rows when possible:**

   ```python
   df = pd.read_csv(sbir_award_data_csv_path, nrows=1000)
   ```

1. **Use chunking for processing:**

   ```python
   for chunk in pd.read_csv(sbir_award_data_csv_path, chunksize=10000):
       process(chunk)
   ```

1. **Select specific columns:**

   ```python
   df = pd.read_csv(sbir_award_data_csv_path, usecols=["Company", "Award Amount"])
   ```

## Running Tests

```bash
# Fast tests only (sample data)
pytest -m fast

# Integration tests with sample data
pytest -m integration

# Integration tests with real data
USE_REAL_SBIR_DATA=1 pytest -m integration

# Specific test with real data
pytest -m real_data tests/integration/test_sbir_enrichment_pipeline.py

# All tests except slow ones
pytest -m "not slow"

# E2E tests with real data
pytest -m "e2e and real_data"
```

## CI/CD Considerations

### Pull Request CI

- Use sample data only for speed
- Run fast and integration tests
- Keep total time under 5 minutes

### Nightly/Weekly CI

- Use real data for comprehensive validation
- Run all test markers including slow and e2e
- Can take 30+ minutes

### Example GitHub Actions

```yaml
# Fast CI for PRs
- name: Run fast tests
  run: pytest -m fast

# Comprehensive nightly tests
- name: Run tests with real data
  run: |
    USE_REAL_SBIR_DATA=1 pytest -m "integration or e2e"
```

## Troubleshooting

### Missing data files

**Solution:** Ensure the data files are available in `data/raw/sbir/`.

### Tests are too slow

**Solution:**

- Ensure you're not accidentally using real data in fast tests
- Use `nrows` parameter to sample data
- Check test markers are correctly applied

### Missing fixture data

**Solution:**

- For sample data: Ensure `tests/fixtures/sbir_sample.csv` exists
- For real data: Ensure data files are available in `data/raw/sbir/`

## Data Quality

### Sample Fixture Quality

- Representative of production data structure
- Includes edge cases for validation testing
- Deterministic (generated with `random.seed(42)`)
- See `tests/fixtures/README.md` for details

### Real Data Quality

- Production SBIR.gov data
- May contain inconsistencies and edge cases
- Reflects actual data quality issues
- Good for comprehensive validation
