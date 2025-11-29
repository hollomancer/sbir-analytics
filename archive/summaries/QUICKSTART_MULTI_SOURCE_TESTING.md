# Quick Start: Testing Multi-Source Data Integration

This is a quick guide to test how SBIR, USAspending, and SAM.gov data integrate together.

## 🚀 Fastest Way to Test (30 seconds)

```bash
# Run the comprehensive E2E test with sample data
pytest tests/e2e/test_multi_source_enrichment.py -v
```

**Expected output:**
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
```

## 🎯 Run the Demo Script

```bash
# Interactive demonstration with sample data
python examples/multi_source_enrichment_demo.py --use-sample-data

# Save enriched results to CSV
python examples/multi_source_enrichment_demo.py --use-sample-data --output-csv enriched_awards.csv
```

**Expected output:**
```
================================================================================
SBIR Multi-Source Data Enrichment Demonstration
================================================================================

Step 1: Loading SBIR Awards Data...
Loaded 3 sample SBIR awards

Step 2: Enriching with USAspending Data...
USAspending enrichment complete

Step 3: Enriching with SAM.gov Data...
SAM.gov matches: 3/3 (100.0%)
SAM.gov enrichment complete

================================================================================
ENRICHMENT SUMMARY
================================================================================
Total Awards: 3

USAspending Enrichment:
  Matched: 3/3 (100.0%)
    uei-exact: 3

SAM.gov Enrichment:
  Matched: 3/3 (100.0%)
  CAGE Codes: 3
  NAICS Codes: 3

Fully Enriched: 3/3 (100.0%)
================================================================================
```

## 📊 What Gets Tested

### Data Sources
1. **SBIR Awards** (Primary dataset)
   - Company names, UEIs, DUNS numbers
   - Contract IDs, award amounts
   - Agency and program information

2. **USAspending** (Contract details)
   - Recipient locations (city, state, ZIP)
   - Business types (Small Business, Woman Owned, etc.)
   - Matched by: UEI → DUNS → Fuzzy name

3. **SAM.gov** (Company registration)
   - CAGE codes, NAICS codes
   - Legal business names
   - Entity structure and business types
   - Matched by: UEI → CAGE

### Enrichment Flow

```
┌─────────────────┐
│  SBIR Awards    │  Company: "Quantum Dynamics Inc"
│  (4 records)    │  UEI: "Q1U2A3N4T5U6M7D8"
└────────┬────────┘
         │
         ├──────────────────┐
         │                  │
         ▼                  ▼
┌─────────────────┐  ┌──────────────────┐
│  USAspending    │  │    SAM.gov       │
│  (4 recipients) │  │  (4 entities)    │
└────────┬────────┘  └─────────┬────────┘
         │                     │
         │  Match by UEI       │  Match by UEI
         │  (or DUNS/name)     │  (or CAGE)
         │                     │
         └──────────┬──────────┘
                    ▼
         ┌─────────────────────┐
         │  Enriched Dataset   │
         │                     │
         │  Original SBIR data │
         │  + City, State, ZIP │
         │  + CAGE Code        │
         │  + NAICS Code       │
         │  + Business Types   │
         └─────────────────────┘
```

## 📝 Sample Test Data

### SBIR Award Example
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

### After USAspending Enrichment
```python
{
    # Original fields...
    "_usaspending_match_method": "uei-exact",
    "_usaspending_match_score": 100,
    "usaspending_recipient_recipient_city": "Arlington",
    "usaspending_recipient_recipient_state": "VA",
    "usaspending_recipient_business_types": "Small Business"
}
```

### After SAM.gov Enrichment
```python
{
    # Previous fields...
    "sam_cage_code": "1QD45",
    "sam_legal_business_name": "QUANTUM DYNAMICS INC",
    "sam_primary_naics": "541712",
    "sam_naics_code_string": "541712,541330"
}
```

## 🎨 Test Scenarios Covered

| Scenario | Test | What It Validates |
|----------|------|-------------------|
| **Exact UEI Match** | `test_sbir_plus_usaspending_enrichment` | Awards with UEIs match to both USAspending and SAM.gov |
| **DUNS Match** | `test_exact_duns_match` | Legacy DUNS identifiers work as fallback |
| **Fuzzy Name Match** | `test_sbir_plus_usaspending_enrichment` (4th award) | Companies without UEI/DUNS match by name |
| **CAGE Code Enrichment** | `test_sbir_plus_sam_gov_enrichment` | SAM.gov adds CAGE codes and NAICS |
| **Complete Pipeline** | `test_complete_multi_source_enrichment` | All three sources integrate correctly |
| **Quality Metrics** | `test_enrichment_metrics` | Match rates meet ≥75% threshold |

## 🔍 Verify the Results

After running the demo, check the enriched CSV:

```bash
# View the enriched data
head -20 enriched_awards.csv | column -t -s,

# Count enrichment coverage
python -c "
import pandas as pd
df = pd.read_csv('enriched_awards.csv')
print(f'Total awards: {len(df)}')
print(f'USAspending matches: {df[\"_usaspending_match_method\"].notna().sum()}')
print(f'SAM.gov matches: {df[\"sam_cage_code\"].notna().sum()}')
print(f'Full enrichment: {(df[\"_usaspending_match_method\"].notna() & df[\"sam_cage_code\"].notna()).sum()}')
"
```

## 🏃 Next Steps

### 1. Run All Integration Tests
```bash
# Unit tests (individual extractors)
pytest tests/unit/extractors/ -v

# Integration tests (pairwise enrichment)
pytest tests/integration/test_sbir_enrichment_pipeline.py -v
pytest tests/integration/test_sam_gov_integration.py -v

# E2E tests (complete pipeline)
pytest tests/e2e/test_multi_source_enrichment.py -v
```

### 2. Test with Your Own Data

Modify the demo script to load your own data:

```python
# In examples/multi_source_enrichment_demo.py
# Replace create_sample_data() with:

sbir_awards = pd.read_csv("path/to/your/sbir_data.csv")
usaspending_recipients = pd.read_csv("path/to/your/usaspending_data.csv")
sam_entities = pd.read_parquet("path/to/your/sam_gov_data.parquet")
```

### 3. Explore the Enrichment Pipeline

Check the source code to understand how it works:

```bash
# USAspending enrichment logic
cat src/enrichers/usaspending.py

# SAM.gov extractor
cat src/extractors/sam_gov.py

# Test fixtures
cat tests/e2e/test_multi_source_enrichment.py
```

## 📚 Full Documentation

- **Testing Guide**: `docs/TESTING_MULTI_SOURCE_INTEGRATION.md`
- **SAM.gov Integration**: `docs/SAM_GOV_INTEGRATION.md`
- **Test Source**: `tests/e2e/test_multi_source_enrichment.py`
- **Demo Script**: `examples/multi_source_enrichment_demo.py`

## ❓ Troubleshooting

**Tests fail with import errors:**
```bash
# Ensure you're in the repo root
cd /path/to/sbir-analytics
pytest tests/e2e/test_multi_source_enrichment.py
```

**Want to see verbose output:**
```bash
pytest tests/e2e/test_multi_source_enrichment.py -v -s
```

**Low match rates in your data:**
- Check that UEIs are exactly 16 characters
- Verify column names match expected schema
- Review test fixtures for examples: `tests/e2e/test_multi_source_enrichment.py`

## 🎉 Success!

If tests pass, you've successfully validated that:
- ✅ SBIR awards can be loaded and parsed
- ✅ USAspending data enriches awards with location/business info
- ✅ SAM.gov data enriches awards with CAGE codes and NAICS
- ✅ The complete pipeline achieves ≥75% match rates
- ✅ All three data sources integrate seamlessly

Ready to process real data at scale!
