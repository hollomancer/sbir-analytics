# Testing the Fiscal StateIO Pipeline

## Overview

The fiscal stateio pipeline transforms SBIR awards into economic impact estimates and federal tax return calculations. This guide explains how to test the complete end-to-end pipeline.

## Quick Start (30 seconds)

```bash
# Run the complete fiscal pipeline test
pytest tests/e2e/test_fiscal_stateio_pipeline.py -v -s
```

**Expected output:**
```
[Step 1] Enriching SBIR awards with USAspending data...
  ✓ Enriched 4 awards with USAspending data
  ✓ State coverage: 4/4

[Step 2] Enriching with SAM.gov data (NAICS codes)...
  ✓ NAICS coverage: 4/4 (100.0%)

[Step 3] Mapping NAICS codes to BEA sectors...
  ✓ BEA mapping coverage: 4/4 (100.0%)

[Step 4] Calculating fiscal years...
  ✓ Fiscal years: [2023 2024]

[Step 5] Aggregating awards into economic shocks...
  ✓ Created 4 economic shocks
  ✓ States: ['VA' 'CA' 'MA' 'TX']
  ✓ Total shock amount: $2,200,000.00

[Step 6] Calculating tax estimates...
  ✓ Total investment: $2,200,000.00
  ✓ Estimated tax receipts: $660,000.00

[Step 7] Calculating ROI metrics...
  ✓ ROI Ratio: 30.00%
  ✓ Benefit-Cost Ratio: 1.30
  ✓ Payback Period: 3.33 years

✅ COMPLETE PIPELINE TEST: PASSED
```

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  FISCAL STATEIO PIPELINE                     │
└─────────────────────────────────────────────────────────────┘

Step 1: SBIR Awards (Primary Data)
  ├─ Company: "Quantum Dynamics Inc"
  ├─ Award Amount: $150,000
  ├─ Award Date: "2023-03-15"
  └─ UEI: "Q1U2A3N4T5U6M7D8"

        ↓ [USAspending Enrichment]

Step 2: + Location Data
  ├─ State: "VA"
  ├─ City: "Arlington"
  └─ ZIP: "22201"

        ↓ [SAM.gov Enrichment]

Step 3: + NAICS Code
  ├─ Primary NAICS: "541712"
  └─ Description: "R&D in Physical Sciences"

        ↓ [NAICS-to-BEA Mapping]

Step 4: + BEA Sector
  ├─ BEA Code: "54"
  └─ Sector: "Professional, Scientific, Technical Services"

        ↓ [Fiscal Year Calculation]

Step 5: + Fiscal Year
  └─ FY 2023 (award date: March 2023)

        ↓ [Economic Shock Aggregation]

Step 6: Economic Shock (by State-Sector-Year)
  ├─ State: "VA"
  ├─ BEA Sector: "54"
  ├─ Fiscal Year: 2023
  ├─ Shock Amount: $150,000
  └─ Number of Awards: 1

        ↓ [StateIO Model - MOCKED IN TEST]

Step 7: Economic Components (Output Multipliers)
  ├─ Wage Impact: $60,000 (40% multiplier)
  ├─ Proprietor Income: $22,500 (15% multiplier)
  └─ Corporate Profits: $15,000 (10% multiplier)

        ↓ [Tax Estimation]

Step 8: Federal Tax Receipts
  ├─ Individual Income Tax: ~$18,000
  ├─ Payroll Tax: ~$9,000
  ├─ Corporate Income Tax: ~$3,000
  └─ Total: ~$30,000

        ↓ [ROI Calculation]

Step 9: Fiscal Return Metrics
  ├─ ROI Ratio: 30%
  ├─ Benefit-Cost Ratio: 1.30
  └─ Payback Period: 3.33 years
```

## Pipeline Steps Explained

### Step 1: Load SBIR Awards

**Purpose:** Start with SBIR award data (company, amount, date, identifiers)

**Test:** `test_step1_enrich_with_usaspending`

**Sample Data:**
```python
{
    "Company": "Quantum Dynamics Inc",
    "UEI": "Q1U2A3N4T5U6M7D8",
    "Award Amount": 150000.0,
    "Award Date": "2023-03-15",
    "Agency": "DOD"
}
```

### Step 2: Enrich with USAspending

**Purpose:** Add recipient location data (state, city, ZIP)

**Test:** `test_step1_enrich_with_usaspending`

**Required for:** Geographic allocation to state IO tables

**Quality Threshold:** ≥90% state coverage

**Added Fields:**
- `usaspending_recipient_recipient_state` (VA, CA, MA, TX)
- `usaspending_recipient_recipient_city`
- `usaspending_recipient_recipient_zip`

### Step 3: Enrich with SAM.gov

**Purpose:** Add NAICS codes for industry classification

**Test:** `test_step2_enrich_with_sam_gov`

**Required for:** NAICS-to-BEA sector mapping

**Quality Threshold:** ≥85% NAICS coverage

**Added Fields:**
- `sam_primary_naics` (541712, 541511, 541714, etc.)
- `sam_cage_code`
- `sam_legal_business_name`

### Step 4: Map NAICS to BEA Sectors

**Purpose:** Convert NAICS industry codes to BEA economic sectors

**Test:** `test_step3_map_naics_to_bea`

**Required for:** StateIO model input (BEA uses own sector classification)

**Quality Threshold:** ≥90% BEA mapping rate

**Mapping Example:**
```
NAICS 541712 → BEA Sector 54 (Professional Services)
NAICS 541511 → BEA Sector 54 (Professional Services)
NAICS 541714 → BEA Sector 54 (Professional Services)
```

### Step 5: Calculate Fiscal Years

**Purpose:** Determine government fiscal year from award date

**Test:** `test_step4_calculate_fiscal_years`

**Fiscal Year Rules:**
- FY runs Oct 1 - Sep 30
- Oct-Dec dates → next calendar year FY
- Jan-Sep dates → same calendar year FY

**Examples:**
- `2023-03-15` → FY 2023
- `2023-10-01` → FY 2024
- `2023-11-10` → FY 2024

### Step 6: Aggregate into Economic Shocks

**Purpose:** Group awards by state-sector-fiscal year for StateIO model

**Test:** `test_step5_aggregate_into_shocks`

**Aggregation:**
```python
shocks = awards.groupby(['state', 'bea_sector', 'fiscal_year']).agg({
    'Award Amount': 'sum',
    'Contract': 'count'
})
```

**Output:**
```
State | BEA Sector | FY   | Shock Amount | Awards
------|------------|------|--------------|-------
VA    | 54         | 2023 | $150,000     | 1
CA    | 54         | 2023 | $750,000     | 1
MA    | 54         | 2024 | $300,000     | 1
TX    | 54         | 2023 | $1,000,000   | 1
```

### Step 7: Calculate Tax Estimates

**Purpose:** Estimate federal tax receipts from economic activity

**Test:** `test_step6_calculate_tax_estimates`

**Tax Components:**
1. **Individual Income Tax** (from wage impacts)
   - Base rate: 22% effective
   - Progressive brackets for high income

2. **Payroll Tax** (from wage impacts)
   - Rate: 15.3% (Social Security + Medicare)
   - Employer + employee portions

3. **Corporate Income Tax** (from corporate profits)
   - Rate: 21% federal rate
   - Applied to gross operating surplus

**Simplified Calculation:**
```python
wage_impact = shock_amount × 0.40  # 40% multiplier
individual_tax = wage_impact × 0.22
payroll_tax = wage_impact × 0.153
corporate_tax = corporate_profits × 0.21
```

### Step 8: Calculate ROI Metrics

**Purpose:** Compute return on investment for SBIR program

**Test:** `test_step7_calculate_roi_metrics`

**Metrics:**

1. **ROI Ratio**
   ```
   ROI = (Total Tax Receipts - Investment) / Investment
   ```

2. **Benefit-Cost Ratio**
   ```
   B/C = Total Tax Receipts / Investment
   ```

3. **Payback Period**
   ```
   Years = Investment / Annual Tax Receipts
   ```

4. **Net Present Value (NPV)**
   ```
   NPV = Σ (Tax Receipts / (1 + discount_rate)^year)
   ```

## Quality Thresholds

The pipeline validates against configured thresholds from `config/base.yaml`:

```yaml
fiscal_analysis:
  quality_thresholds:
    naics_coverage_rate: 0.85      # 85% minimum
    geographic_resolution_rate: 0.90  # 90% minimum
    bea_sector_mapping_rate: 0.90   # 90% minimum
```

**Tested by:** `TestFiscalDataQualityThresholds`

## Running Individual Tests

### Test Specific Steps

```bash
# Step 1: USAspending enrichment
pytest tests/e2e/test_fiscal_stateio_pipeline.py::TestFiscalStateIOPipelineE2E::test_step1_enrich_with_usaspending -v

# Step 2: SAM.gov enrichment
pytest tests/e2e/test_fiscal_stateio_pipeline.py::TestFiscalStateIOPipelineE2E::test_step2_enrich_with_sam_gov -v

# Step 3: NAICS-to-BEA mapping
pytest tests/e2e/test_fiscal_stateio_pipeline.py::TestFiscalStateIOPipelineE2E::test_step3_map_naics_to_bea -v

# Step 4: Fiscal year calculation
pytest tests/e2e/test_fiscal_stateio_pipeline.py::TestFiscalStateIOPipelineE2E::test_step4_calculate_fiscal_years -v

# Step 5: Economic shock aggregation
pytest tests/e2e/test_fiscal_stateio_pipeline.py::TestFiscalStateIOPipelineE2E::test_step5_aggregate_into_shocks -v

# Step 6: Tax estimation
pytest tests/e2e/test_fiscal_stateio_pipeline.py::TestFiscalStateIOPipelineE2E::test_step6_calculate_tax_estimates -v

# Step 7: ROI calculation
pytest tests/e2e/test_fiscal_stateio_pipeline.py::TestFiscalStateIOPipelineE2E::test_step7_calculate_roi_metrics -v
```

### Test Quality Thresholds

```bash
# Test all quality thresholds
pytest tests/e2e/test_fiscal_stateio_pipeline.py::TestFiscalDataQualityThresholds -v

# Test specific threshold
pytest tests/e2e/test_fiscal_stateio_pipeline.py::TestFiscalDataQualityThresholds::test_naics_coverage_threshold -v
```

### Test Complete Pipeline

```bash
# Run complete integration test with verbose output
pytest tests/e2e/test_fiscal_stateio_pipeline.py::TestFiscalStateIOPipelineE2E::test_complete_pipeline_integration -v -s
```

## Sample Data

The test uses 4 sample SBIR awards:

| Company | Amount | State | NAICS | BEA Sector | FY |
|---------|--------|-------|-------|------------|-----|
| Quantum Dynamics | $150K | VA | 541712 | 54 | 2023 |
| Neural Networks | $750K | CA | 541511 | 54 | 2023 |
| BioMed Solutions | $300K | MA | 541714 | 54 | 2024 |
| AI Robotics | $1M | TX | 541715 | 54 | 2023 |

**Total Investment:** $2.2M

**Expected Results (30% effective return rate):**
- Tax Receipts: ~$660K
- ROI: 30%
- B/C Ratio: 1.30
- Payback: ~3.3 years

## Interpreting Results

### Good Results
- ✅ NAICS coverage ≥85%
- ✅ State coverage ≥90%
- ✅ BEA mapping ≥90%
- ✅ ROI > 0 (positive return)
- ✅ All quality thresholds passed

### Warning Signs
- ⚠️ NAICS coverage <85% → Need better SAM.gov enrichment
- ⚠️ State coverage <90% → Need better USAspending enrichment
- ⚠️ BEA mapping <90% → Need updated NAICS-BEA crosswalk
- ⚠️ ROI < 0 → Tax estimates may be incorrect

## Troubleshooting

### Low NAICS Coverage

**Problem:** `NAICS coverage below 85% threshold`

**Solutions:**
1. Check SAM.gov enrichment:
   ```bash
   pytest tests/integration/test_sam_gov_integration.py -v
   ```

2. Verify UEI matching:
   ```bash
   pytest tests/e2e/test_multi_source_enrichment.py::TestMultiSourceEnrichmentPipeline::test_sbir_plus_sam_gov_enrichment -v
   ```

### Low State Coverage

**Problem:** `State coverage below 90% threshold`

**Solutions:**
1. Check USAspending enrichment:
   ```bash
   pytest tests/unit/enrichers/test_usaspending_matching.py -v
   ```

2. Verify UEI/DUNS matching:
   ```bash
   pytest tests/e2e/test_multi_source_enrichment.py::TestMultiSourceEnrichmentPipeline::test_sbir_plus_usaspending_enrichment -v
   ```

### BEA Mapping Failures

**Problem:** `BEA mapping below 90% threshold`

**Solutions:**
1. Check NAICS-BEA crosswalk file exists:
   ```bash
   ls data/reference/bea/naics_to_bea_crosswalk_2017.csv
   ```

2. Test mapping directly:
   ```python
   from src.transformers.naics_to_bea import NAICSToBEAMapper
   mapper = NAICSToBEAMapper()
   result = mapper.map_code("541712")  # Should return "54"
   ```

### Negative ROI

**Problem:** `ROI < 0 or unreasonably low`

**Solutions:**
1. Check tax estimation parameters in config:
   ```yaml
   fiscal_analysis:
     tax_parameters:
       individual_income_tax:
         effective_rate: 0.22
   ```

2. Verify economic multipliers are reasonable
3. Check that shock amounts are properly aggregated

## Next Steps

After tests pass:

1. **Review Results**
   ```bash
   pytest tests/e2e/test_fiscal_stateio_pipeline.py -v -s > fiscal_test_results.txt
   ```

2. **Run with Real Data** (when ready)
   - Replace sample fixtures with actual SBIR/USAspending/SAM.gov data
   - Update NAICS-BEA crosswalk with latest version
   - Configure StateIO model connection

3. **Validate Against Known Benchmarks**
   - Compare ROI estimates with published SBIR studies
   - Verify multipliers match BEA input-output tables
   - Cross-check tax rates with IRS data

## References

- **Configuration:** `config/base.yaml` (lines 535-637)
- **Multi-Source Enrichment:** `tests/e2e/test_multi_source_enrichment.py`
- **Fiscal Components:** `src/transformers/fiscal/*.py`
- **NAICS-BEA Mapping:** `src/transformers/naics_to_bea.py`
- **Tax Estimation:** `src/transformers/fiscal/taxes.py`
- **ROI Calculation:** `src/transformers/fiscal/roi.py`

## Summary

This test validates the **complete fiscal stateio pipeline** from raw SBIR awards to economic impact estimates:

✅ Data enrichment (USAspending + SAM.gov)
✅ NAICS-to-BEA sector mapping
✅ Fiscal year calculation
✅ Economic shock aggregation
✅ Tax receipt estimation
✅ ROI metrics calculation
✅ Quality threshold validation

**Run:** `pytest tests/e2e/test_fiscal_stateio_pipeline.py -v -s`
