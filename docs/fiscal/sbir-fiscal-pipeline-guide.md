## SBIR Fiscal Impact Pipeline Guide

Complete guide to calculating tax revenue and job creation impacts from SBIR awards using StateIO economic models.

## Overview

This pipeline transforms SBIR award data into actionable fiscal and employment impact estimates by state and industry sector.

### Pipeline Flow

```text
SBIR Awards (with NAICS codes)
    ↓
[NAICS → BEA Sector Mapping]
    ↓
Aggregate by State/Sector/Year
    ↓
[StateIO Economic Models]
    ↓
Economic Impacts (tax, wages, production)
    ↓
[Employment Calculation]
    ↓
Results: Tax Revenue + Jobs Created by Region/Industry
```

## Input Requirements

### SBIR Awards DataFrame

Required columns:

- **award_id**: Unique identifier for each award
- **award_amount**: Dollar amount of award (numeric)
- **state**: Two-letter state code (e.g., "CA", "NY")
- **naics_code**: NAICS industry classification (2-6 digits)
- **fiscal_year**: Award fiscal year (e.g., 2023)

Optional columns:

- company_name, award_title, etc. (preserved but not used in calculations)

### Example Input

```python
awards_df = pd.DataFrame({
    "award_id": ["SBIR-2023-001", "SBIR-2023-002"],
    "award_amount": [1000000, 500000],
    "state": ["CA", "NY"],
    "naics_code": ["541512", "621111"],
    "fiscal_year": [2023, 2023]
})
```

## Usage

### Basic Usage

```python
from src.transformers.sbir_fiscal_pipeline import SBIRFiscalImpactCalculator

# Initialize calculator
calculator = SBIRFiscalImpactCalculator()

# Calculate impacts
impacts = calculator.calculate_impacts_from_sbir_awards(awards_df)

# Results include:
# - state, bea_sector, fiscal_year
# - award_total (sum of SBIR awards)
# - production_impact (economic multiplier)
# - wage_impact, tax_impact, jobs_created
# - model_version, confidence, quality_flags
```

### Summary Statistics

```python
# State-level summary
state_summary = calculator.calculate_summary_by_state(impacts)
# Returns: state, total_awards, total_tax_impact, total_jobs_created, etc.

# Sector-level summary
sector_summary = calculator.calculate_summary_by_sector(impacts)
# Returns: bea_sector, sector_description, totals by sector
```

## Output Columns

### Detailed Impacts DataFrame

| Column | Description | Units |
|--------|-------------|-------|
| state | Two-letter state code | String |
| bea_sector | BEA I-O sector code | String |
| fiscal_year | Fiscal year | Integer |
| award_total | Sum of SBIR awards | Dollars |
| production_impact | Total production multiplier effect | Dollars |
| wage_impact | Wage and salary impacts | Dollars |
| proprietor_income_impact | Proprietor income impacts | Dollars |
| gross_operating_surplus | Business surplus impacts | Dollars |
| tax_impact | Tax revenue (state + federal) | Dollars |
| consumption_impact | Consumption effects | Dollars |
| jobs_created | Employment created | Count |
| model_version | Economic model version | String |
| confidence | Confidence score (0-1) | Float |
| quality_flags | Data quality indicators | String |

### Quality Flags

Indicates computation method and data quality:

- **stateio_direct_with_ratios**: Highest quality (Direct StateIO + actual ratios)
- **stateio_direct_default_ratios**: Medium quality (Direct StateIO + defaults)
- **stateio_failed**: Computation failure (contains error details)
- **placeholder_computation**: R packages unavailable (lowest quality)

## NAICS to BEA Mapping

### Mapping Logic

NAICS codes (6-digit industry codes) are mapped to BEA Summary-level I-O sectors (approximately 71 sectors):

| NAICS Prefix | BEA Sector | Description |
|--------------|------------|-------------|
| 11xxxx | 11 | Agriculture, forestry, fishing |
| 21xxxx | 21 | Mining, oil and gas |
| 22xxxx | 22 | Utilities |
| 23xxxx | 23 | Construction |
| 31-33xxxx | 31-33 | Manufacturing |
| 54xxxx | 54 | Professional, scientific, technical services |
| 62xxxx | 62 | Health care and social assistance |

See `src/transformers/naics_bea_mapper.py` for complete mapping.

### Custom Concordance

To use a custom NAICS-BEA concordance:

```python
from src.transformers.naics_bea_mapper import NAICSBEAMapper

mapper = NAICSBEAMapper(concordance_path="/path/to/concordance.csv")
calculator = SBIRFiscalImpactCalculator(naics_mapper=mapper)
```

## Employment Calculation

Jobs created are estimated from wage impacts:

```
jobs_created = wage_impact / average_wage
```

Default average wage: $100,000 (varies by sector and state in practice)

For more accurate estimates, integrate with StateIO employment coefficients.

## Economic Multipliers

### Production Multiplier

Total economic output generated per dollar of SBIR investment:

```text
Production Multiplier = Total Production Impact / Total Awards
```

Typical range: 1.5x - 3.0x depending on sector

### Tax Revenue Multiplier

Tax revenue generated per dollar of SBIR investment:

```text
Tax Multiplier = Total Tax Impact / Total Awards
```

Typical range: $0.10 - $0.30 per $1 invested

### Jobs Multiplier

Jobs created per million dollars of SBIR investment:

```text
Jobs per $1M = (Total Jobs / Total Awards) * 1,000,000
```

Typical range: 5-15 jobs per $1M

## Example Analysis

See `examples/sbir_fiscal_impact_example.py` for complete working example.

### Run Example

```bash
python examples/sbir_fiscal_impact_example.py
```

### Example Output

```console
IMPACT RESULTS
state  bea_sector  award_total  production_impact  wage_impact  tax_impact  jobs_created
CA     54          1,500,000    3,000,000         800,000      300,000     8.0
NY     62          750,000      1,500,000         400,000      150,000     4.0
TX     31-33       1,200,000    2,400,000         600,000      240,000     6.0

KEY METRICS
  Total SBIR Awards:        $3,450,000
  Total Production Impact:  $6,900,000
  Total Tax Revenue Impact: $690,000
  Total Jobs Created:       18.0 jobs

  Production Multiplier:    2.00x
  Tax Revenue Multiplier:   0.20x ($20.00 per $100 invested)
  Jobs per $1M Investment:  5.2 jobs
```

## Integration with Existing Pipeline

### With USAspending Enrichment

```python
# After enriching SBIR data with NAICS from USAspending:
enriched_awards = enrich_sbir_with_usaspending(sbir_data)

# Calculate fiscal impacts
calculator = SBIRFiscalImpactCalculator()
impacts = calculator.calculate_impacts_from_sbir_awards(enriched_awards)
```

### With Dagster

```python
from dagster import asset

@asset
def sbir_fiscal_impacts(enriched_sbir_awards: pd.DataFrame) -> pd.DataFrame:
    """Calculate fiscal impacts from SBIR awards."""
    calculator = SBIRFiscalImpactCalculator()
    return calculator.calculate_impacts_from_sbir_awards(enriched_sbir_awards)

@asset
def state_summary(sbir_fiscal_impacts: pd.DataFrame) -> pd.DataFrame:
    """Summarize impacts by state."""
    calculator = SBIRFiscalImpactCalculator()
    return calculator.calculate_summary_by_state(sbir_fiscal_impacts)
```

## Performance Considerations

### Model Caching

Economic models are built once and cached:

- First run: ~30-60 seconds per state
- Subsequent runs: <1 second (cache hit)

### Batch Processing

Process large award datasets in batches:

```python
# Process 1000 awards at a time
chunk_size = 1000
results = []

for i in range(0, len(awards_df), chunk_size):
    chunk = awards_df.iloc[i:i+chunk_size]
    impacts = calculator.calculate_impacts_from_sbir_awards(chunk)
    results.append(impacts)

all_impacts = pd.concat(results, ignore_index=True)
```

### Parallelization

Process multiple states in parallel (future enhancement).

## Validation and Quality Checks

### Input Validation

```python
# Automatic validation on pipeline run
# Checks for:
# - Required columns present
# - No null values in required fields
# - Valid state codes
# - Positive award amounts
```

### Output Validation

```python
# Check quality flags
high_quality = impacts[
    impacts["quality_flags"].str.contains("stateio_ratios")
]

# Check confidence scores
reliable = impacts[impacts["confidence"] > 0.7]
```

## Troubleshooting

### R Packages Not Available

```console
Error: StateIO R package not loaded
```

**Solution**: Install R and required packages

```bash
# Install R packages
R -e "remotes::install_github('USEPA/stateior')"

# Install Python rpy2
uv sync --extra r
```

### NAICS Mapping Warnings

```console
Warning: No BEA mapping found for NAICS 999999
```

**Solution**: Check NAICS code validity or provide custom concordance

### Low Confidence Scores

```console
Average Confidence Score: 0.40
```

**Causes**:

- StateIO data unavailable for state/year
- Fallback to default ratios
- R packages not installed

**Solutions**:

- Install R packages
- Use more recent fiscal year (better data availability)
- Accept lower precision or exclude low-confidence records

## References

- **BEA I-O Accounts**: <https://www.bea.gov/industry/input-output-accounts-data>
- **NAICS Codes**: <https://www.census.gov/naics/>
- **StateIO Package**: <https://github.com/USEPA/stateior>
- **StateIO API Reference**: `docs/fiscal/stateio-api-reference.md`
