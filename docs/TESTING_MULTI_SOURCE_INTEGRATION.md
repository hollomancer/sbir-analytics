# Testing Multi-Source Data Integration

This guide explains how to test the integration of SBIR, USAspending, and SAM.gov data sources.

## Overview

The SBIR Analytics pipeline enriches SBIR award data with information from multiple government data sources:

```
SBIR Awards (Primary)
    ├─> USAspending (Contract & recipient details)
    └─> SAM.gov (Company registration & NAICS codes)
         └─> Enriched Dataset
```

## Test Levels

### 1. Unit Tests (Fast)
Test individual components in isolation:

```bash
# Test SBIR extractor
pytest tests/unit/extractors/test_sbir_extractor.py -v

# Test USAspending extractor
pytest tests/unit/extractors/test_usaspending_extractor.py -v

# Test SAM.gov extractor
pytest tests/unit/extractors/test_sam_gov_extractor.py -v
```

### 2. Integration Tests (Medium)
Test pairwise data source integrations:

```bash
# Test SBIR + USAspending enrichment
pytest tests/unit/enrichers/test_usaspending_matching.py -v

# Test SBIR enrichment pipeline
pytest tests/integration/test_sbir_enrichment_pipeline.py -v

# Test SAM.gov integration
pytest tests/integration/test_sam_gov_integration.py -v
```

### 3. End-to-End Tests (Comprehensive)
Test the complete multi-source enrichment pipeline:

```bash
# Run all E2E tests with sample data
pytest tests/e2e/test_multi_source_enrichment.py -v

# Run specific test class
pytest tests/e2e/test_multi_source_enrichment.py::TestMultiSourceEnrichmentPipeline -v

# Run with detailed output
pytest tests/e2e/test_multi_source_enrichment.py -v -s
```

## Sample Data vs Real Data

### Using Sample Data (Default, Fast)

All E2E tests use **sample fixtures** by default for speed:

```bash
pytest tests/e2e/test_multi_source_enrichment.py -v
```

Sample data includes:
- 4 SBIR awards (covering different agencies)
- 4 USAspending recipients (matching UEI/DUNS patterns)
- 4 SAM.gov entities (with CAGE codes and NAICS)

### Using Real Data (Slower, More Comprehensive)

To test with actual production data:

```bash
# Set environment variable
export USE_REAL_SBIR_DATA=1

# Run real data tests
pytest tests/e2e/test_multi_source_enrichment.py -m real_data -v
```

Real data requirements:
1. **SBIR Data**: `data/raw/sbir/award_data.csv` (~381MB, Git LFS)
2. **USAspending Data**: Database dump in S3 or `data/usaspending/`
3. **SAM.gov Data**: `data/raw/sam_gov/sam_entity_records.parquet` (~500MB)

## Understanding the Test Data

### Sample SBIR Awards

```python
{
    "Company": "Quantum Dynamics Inc",
    "UEI": "Q1U2A3N4T5U6M7D8",
    "Duns": "111222333",
    "Contract": "W31P4Q-23-C-0001",
    "Agency": "DOD",
    "Award Amount": 150000.0,
    "Phase": "Phase I"
}
```

### Sample USAspending Recipients

```python
{
    "recipient_name": "Quantum Dynamics Incorporated",
    "recipient_uei": "Q1U2A3N4T5U6M7D8",  # Matches SBIR UEI
    "recipient_city": "Arlington",
    "recipient_state": "VA",
    "business_types": "Small Business"
}
```

### Sample SAM.gov Entities

```python
{
    "unique_entity_id": "Q1U2A3N4T5U6M7D8",  # Matches SBIR UEI
    "cage_code": "1QD45",
    "legal_business_name": "QUANTUM DYNAMICS INC",
    "primary_naics": "541712",
    "business_type_string": "2X,A5"
}
```

## Test Scenarios Covered

### 1. Exact UEI Matching
Tests that SBIR awards with valid UEIs match correctly to USAspending and SAM.gov data.

**Test**: `test_sbir_plus_usaspending_enrichment`
```python
# Award with UEI "Q1U2A3N4T5U6M7D8" should match
assert enriched["_usaspending_match_method"].iloc[0] == "uei-exact"
assert enriched["_usaspending_match_score"].iloc[0] == 100
```

### 2. DUNS Matching (Legacy)
Tests fallback to DUNS when UEI is unavailable.

**Test**: `test_exact_duns_match`
```python
# Award with DUNS "111222333" should match
assert enriched["_usaspending_match_method"].iloc[0] == "duns-exact"
```

### 3. Fuzzy Name Matching
Tests matching by company name when identifiers are missing.

**Test**: `test_sbir_plus_usaspending_enrichment` (4th award)
```python
# Award with no UEI/DUNS should match by fuzzy name
assert enriched["_usaspending_match_method"].iloc[3] in ["name-fuzzy-high", "name-fuzzy-low"]
```

### 4. SAM.gov CAGE Code Enrichment
Tests that SAM.gov data adds CAGE codes and NAICS codes.

**Test**: `test_sbir_plus_sam_gov_enrichment`
```python
assert enriched["sam_cage_code"].iloc[0] == "1QD45"
assert enriched["sam_primary_naics"].iloc[0] == "541712"
```

### 5. Complete Multi-Source Enrichment
Tests the full pipeline with all three data sources.

**Test**: `test_complete_multi_source_enrichment`
```python
# Verify all enrichment columns present
assert "_usaspending_match_method" in enriched.columns
assert "sam_cage_code" in enriched.columns
assert "sam_primary_naics" in enriched.columns
```

### 6. Enrichment Quality Metrics
Tests that enrichment meets quality thresholds.

**Test**: `test_enrichment_metrics`
```python
usaspending_match_rate = enriched["_usaspending_match_method"].notna().sum() / total
assert usaspending_match_rate >= 0.75  # At least 75% match rate
```

## Expected Test Results

When you run the E2E tests, you should see output like:

```
tests/e2e/test_multi_source_enrichment.py::TestMultiSourceEnrichmentPipeline::test_sbir_plus_usaspending_enrichment PASSED
tests/e2e/test_multi_source_enrichment.py::TestMultiSourceEnrichmentPipeline::test_sbir_plus_sam_gov_enrichment PASSED
tests/e2e/test_multi_source_enrichment.py::TestMultiSourceEnrichmentPipeline::test_complete_multi_source_enrichment PASSED
tests/e2e/test_multi_source_enrichment.py::TestMultiSourceEnrichmentPipeline::test_enrichment_metrics PASSED

=== Enrichment Metrics ===
Total Awards: 4
USAspending Match Rate: 100.0%
SAM.gov Match Rate: 75.0%
High-Confidence Match Rate: 75.0%
NAICS Coverage Rate: 75.0%

4 passed in 0.15s
```

## Running Tests in CI/CD

The tests are designed to run in CI/CD pipelines:

```yaml
# .github/workflows/ci.yml
- name: Run multi-source integration tests
  run: |
    pytest tests/e2e/test_multi_source_enrichment.py -v --tb=short
```

## Interactive Testing with Jupyter

For exploratory testing, you can use the sample data interactively:

```python
import pandas as pd
from src.enrichers.usaspending import enrich_sbir_with_usaspending

# Load sample data
sbir_df = pd.read_csv("tests/fixtures/sbir_sample.csv")
usaspending_df = ...  # Load from test fixture

# Enrich
enriched = enrich_sbir_with_usaspending(sbir_df, usaspending_df)

# Explore results
print(enriched[["Company", "_usaspending_match_method", "_usaspending_match_score"]].head())
```

## Troubleshooting

### Import Errors

**Error**: `ModuleNotFoundError: No module named 'src'`

**Solution**: The `conftest.py` automatically adds the repo root to sys.path. Ensure you're running pytest from the repository root:

```bash
cd /path/to/sbir-analytics
pytest tests/e2e/test_multi_source_enrichment.py
```

### Missing Fixtures

**Error**: `FileNotFoundError: SBIR sample fixture not found`

**Solution**: Ensure test fixtures exist:

```bash
ls tests/fixtures/sbir_sample.csv
```

If missing, check if Git LFS is configured:

```bash
git lfs install
git lfs pull
```

### Real Data Tests Skipped

**Message**: `SKIPPED [1] test requires real data files`

**Solution**: This is expected. Real data tests are skipped by default unless:
1. Test is marked with `@pytest.mark.real_data`, AND
2. Environment variable `USE_REAL_SBIR_DATA=1` is set, OR
3. `--run-real-data` flag is passed

### Low Match Rates

If enrichment metrics show low match rates:

1. **Check UEI Format**: UEIs should be exactly 16 characters
2. **Check Data Quality**: Ensure test fixtures have matching UEIs
3. **Check Column Names**: Verify column names match expected schema
4. **Enable Debug Logging**: Run with `-s` flag to see detailed output

```bash
pytest tests/e2e/test_multi_source_enrichment.py -v -s
```

## Performance Benchmarks

Typical test execution times:

| Test Level | Test Count | Duration | Data Size |
|------------|-----------|----------|-----------|
| Unit Tests | ~50 | < 5 seconds | Sample only |
| Integration Tests | ~20 | 10-30 seconds | Sample + small extracts |
| E2E Tests (sample) | ~8 | 1-2 seconds | Sample fixtures |
| E2E Tests (real) | ~2 | 5-10 minutes | Full datasets |

## Additional Resources

- **SBIR Enrichment Pipeline**: `tests/integration/test_sbir_enrichment_pipeline.py`
- **USAspending Matching**: `tests/unit/enrichers/test_usaspending_matching.py`
- **SAM.gov Integration**: `tests/integration/test_sam_gov_integration.py`
- **Configuration**: `tests/conftest.py` (fixtures and markers)

## Next Steps

After understanding the tests:

1. **Explore Sample Data**: Review `tests/fixtures/sbir_sample.csv`
2. **Run Unit Tests**: Start with individual extractor tests
3. **Run Integration Tests**: Test pairwise enrichments
4. **Run E2E Tests**: Test complete pipeline
5. **Modify Test Data**: Create custom scenarios for your use case
6. **Run with Real Data**: Validate with production datasets

## Questions?

- Review test docstrings for detailed explanations
- Check inline comments for specific assertions
- Run tests with `-v -s` for verbose output
- Examine test fixtures in `tests/fixtures/`
