# Congressional District Analysis Quick Start Guide

This guide shows you how to analyze SBIR fiscal impacts by congressional district.

## Overview

The congressional district analysis feature allows you to:
- Resolve company addresses to congressional districts
- Calculate fiscal impacts (tax revenue, jobs) at the district level
- Compare districts within a state
- Answer questions like "how many jobs were created in my district?"

## Prerequisites

- SBIR awards data with addresses (company_address, city, state, ZIP)
- Python environment with sbir-etl installed

## Quick Start (5 Minutes)

### Step 1: Setup

Download the HUD ZIP-to-Congressional District crosswalk:

```bash
python scripts/setup_congressional_districts.py
```

This downloads and validates the crosswalk file to `data/reference/ZIP_CD_118.csv`.

### Step 2: Run the Example

```bash
python examples/sbir_fiscal_impact_by_district_example.py
```

This demonstrates the full pipeline with sample data.

### Step 3: Use with Your Data

```python
import pandas as pd
from src.transformers.sbir_fiscal_pipeline import SBIRFiscalImpactCalculator

# Load your SBIR awards (must have addresses)
awards = pd.read_csv("your_sbir_awards.csv")

# Calculate district-level impacts
calculator = SBIRFiscalImpactCalculator()
district_impacts = calculator.calculate_district_impacts(awards)

# Summarize by district
district_summary = calculator.calculate_summary_by_district(district_impacts)
print(district_summary)
```

## Resolution Methods

### Method 1: ZIP Crosswalk (Recommended for Bulk Processing)

**Pros:**
- Fast (no API calls)
- Works offline
- ~80-90% accurate for most use cases

**Cons:**
- Some ZIPs span multiple districts
- Requires HUD crosswalk file

**Usage:**
```python
from src.enrichers.congressional_district_resolver import CongressionalDistrictResolver

resolver = CongressionalDistrictResolver(
    method="zip_crosswalk",
    crosswalk_path="data/reference/ZIP_CD_118.csv"
)

awards_with_districts = resolver.enrich_awards_with_districts(awards_df)
```

### Method 2: Census Geocoder API (Most Accurate)

**Pros:**
- Very accurate (uses full address)
- Free and authoritative
- No API key required

**Cons:**
- Rate-limited (~5 requests/second)
- Requires internet connection
- Slower for large datasets

**Usage:**
```python
resolver = CongressionalDistrictResolver(
    method="census_api",
    census_api_delay=0.2  # Seconds between requests
)

awards_with_districts = resolver.enrich_awards_with_districts(awards_df)
```

### Method 3: Auto (Recommended for Production)

Tries multiple methods with automatic fallback:

```python
resolver = CongressionalDistrictResolver(
    method="auto",
    crosswalk_path="data/reference/ZIP_CD_118.csv"  # Optional
)

awards_with_districts = resolver.enrich_awards_with_districts(awards_df)
```

## Common Use Cases

### Use Case 1: Find Impact in a Specific District

```python
# Calculate impacts
district_impacts = calculator.calculate_district_impacts(awards_df)

# Filter to specific district
ca12 = district_impacts[district_impacts['congressional_district'] == 'CA-12']

# Get totals
total_tax = ca12['tax_impact_allocated'].sum()
total_jobs = ca12['jobs_created_allocated'].sum()
total_awards = ca12['district_award_total'].sum()

print(f"District CA-12:")
print(f"  SBIR Awards: ${total_awards:,.2f}")
print(f"  Tax Revenue: ${total_tax:,.2f}")
print(f"  Jobs Created: {total_jobs:.1f}")
```

### Use Case 2: Compare All Districts in a State

```python
from src.transformers.fiscal.district_allocator import compare_districts_within_state

# Compare all Texas districts
tx_districts = compare_districts_within_state(district_impacts, "TX")

print(tx_districts[['congressional_district', 'total_tax_impact', 'total_jobs_created', 'tax_impact_rank']])
```

### Use Case 3: Top Districts Nationwide

```python
from src.transformers.fiscal.district_allocator import summarize_by_district

# Get national district summary
district_summary = summarize_by_district(district_impacts)

# Top 10 by tax revenue
top_10 = district_summary.nlargest(10, 'total_tax_impact')

for _, row in top_10.iterrows():
    print(f"{row['congressional_district']}: ${row['total_tax_impact']:,.2f} tax impact")
```

### Use Case 4: Export for Congressional Reporting

```python
# Full district summary
district_summary = calculator.calculate_summary_by_district(district_impacts)

# Export to Excel for sharing
district_summary.to_excel("sbir_impact_by_district_2023.xlsx", index=False)

# Export to CSV
district_summary.to_csv("sbir_impact_by_district_2023.csv", index=False)

# Create a simple report
for _, row in district_summary.iterrows():
    print(f"""
Congressional District {row['congressional_district']} ({row['state']})
  Total SBIR Awards: ${row['total_awards']:,.2f}
  Tax Revenue Generated: ${row['total_tax_impact']:,.2f}
  Jobs Created: {row['total_jobs_created']:.1f}
  Active Sectors: {row['sector_count']}
  Confidence Score: {row['avg_confidence']:.1%}
""")
```

### Use Case 5: Multi-Year Trend Analysis

```python
# Calculate impacts for multiple years
years = [2021, 2022, 2023]
all_impacts = []

for year in years:
    awards_year = awards_df[awards_df['fiscal_year'] == year]
    impacts_year = calculator.calculate_district_impacts(awards_year)
    all_impacts.append(impacts_year)

combined = pd.concat(all_impacts)

# Analyze trends
trend = combined.groupby(['congressional_district', 'fiscal_year'])['tax_impact_allocated'].sum()
trend_pivot = trend.unstack()

print(trend_pivot.head())
```

## Understanding the Output

### District Impacts DataFrame

Columns:
- `congressional_district`: District code (e.g., "CA-12")
- `state`: Two-letter state code
- `bea_sector`: BEA economic sector
- `fiscal_year`: Year
- `district_award_total`: Total SBIR awards in district/sector/year
- `allocation_share`: Proportion of state awards in this district (0-1)
- `tax_impact_allocated`: Allocated tax revenue
- `jobs_created_allocated`: Allocated jobs created
- `allocation_confidence`: Confidence score (0-1)

### District Summary DataFrame

Columns:
- `congressional_district`: District code
- `state`: State code
- `total_awards`: Total SBIR funding
- `total_tax_impact`: Total tax revenue
- `total_jobs_created`: Total jobs
- `sector_count`: Number of active sectors
- `avg_confidence`: Average confidence score

## Data Quality and Confidence Scores

### Confidence Score Components

The `allocation_confidence` score is calculated from:
1. **District Resolution Confidence** (40%): How confident we are in the district assignment
   - ZIP crosswalk: 0.7-1.0 (based on allocation ratio)
   - Census API: 0.95
   - Google Civic: 0.98

2. **Economic Model Confidence** (40%): StateIO model confidence
   - Typically 0.85 for mock data
   - Higher for real StateIO calculations

3. **Allocation Share** (20%): Penalizes very small allocations
   - Formula: 0.7 + 0.3 × allocation_share
   - Prevents noise from tiny allocations

### Interpreting Confidence Scores

- **0.85-1.0**: High confidence, suitable for public reporting
- **0.70-0.85**: Medium confidence, suitable with caveats
- **Below 0.70**: Low confidence, investigate or exclude

### Improving Data Quality

1. **Use Census API for critical districts**:
   ```python
   # Resolve important districts with Census API
   important_districts = ["CA-12", "TX-21", "NY-14"]

   for district in important_districts:
       # Use Census API for high accuracy
       resolver = CongressionalDistrictResolver(method="census_api")
       # ... process awards
   ```

2. **Filter by confidence**:
   ```python
   high_confidence = district_impacts[district_impacts['allocation_confidence'] >= 0.85]
   ```

3. **Validate against known data**:
   ```python
   # Check resolution rate
   resolved = awards_with_districts['congressional_district'].notna().sum()
   total = len(awards_with_districts)
   print(f"Resolution rate: {resolved/total:.1%}")

   # Aim for >90% resolution rate
   ```

## Troubleshooting

### Problem: Low resolution rate

**Solution:** Check address data quality

```python
# Check for missing addresses
missing = awards_df[
    awards_df['company_address'].isna() |
    awards_df['company_city'].isna() |
    awards_df['company_state'].isna()
]
print(f"Missing address data: {len(missing)} awards")
```

### Problem: Census API timeouts

**Solution:** Increase timeout and add retries

```python
resolver = CongressionalDistrictResolver(
    method="census_api",
    census_api_delay=0.5  # Slower rate
)
```

### Problem: Crosswalk file not found

**Solution:** Run setup script

```bash
python scripts/setup_congressional_districts.py
```

Or download manually:
1. Visit: https://www.huduser.gov/portal/datasets/usps_crosswalk.html
2. Download latest ZIP-to-Congressional District file
3. Save to: `data/reference/ZIP_CD_118.csv`

### Problem: Different Congress boundaries

HUD updates the crosswalk for each Congress (every 2 years):
- 118th Congress: 2023-2025
- 117th Congress: 2021-2023
- 116th Congress: 2019-2021

Make sure to use the crosswalk matching your data's time period.

## Performance Tips

### For Large Datasets (100k+ awards)

1. **Use ZIP crosswalk** (much faster than API):
   ```python
   resolver = CongressionalDistrictResolver(method="zip_crosswalk")
   ```

2. **Batch processing** with Census API:
   ```python
   # Process in batches of 1000
   batch_size = 1000
   for i in range(0, len(awards_df), batch_size):
       batch = awards_df[i:i+batch_size]
       batch_enriched = resolver.enrich_awards_with_districts(batch)
       # Save batch results
   ```

3. **Cache results**:
   ```python
   # Save enriched data to avoid re-resolving
   awards_with_districts.to_parquet("awards_with_districts.parquet")

   # Load cached data
   awards_with_districts = pd.read_parquet("awards_with_districts.parquet")
   ```

### For Real-Time Analysis

Use ZIP crosswalk for instant results:
```python
resolver = CongressionalDistrictResolver(
    method="zip_crosswalk",
    crosswalk_path="data/reference/ZIP_CD_118.csv"
)

# Resolves 10,000 awards in ~1 second
```

## Next Steps

1. **Test with your data**: Run through the examples with your SBIR awards
2. **Review results**: Check confidence scores and resolution rates
3. **Customize**: Adjust methods and thresholds for your use case
4. **Deploy**: Integrate into your reporting pipeline
5. **Validate**: Cross-check a sample against known outcomes

## Additional Resources

- Full implementation: `examples/sbir_fiscal_impact_by_district_example.py`
- API documentation: `src/enrichers/congressional_district_resolver.py`
- Allocation logic: `src/transformers/fiscal/district_allocator.py`
- Granularity guide: `docs/FISCAL_IMPACT_GRANULARITY.md`
- HUD crosswalk: https://www.huduser.gov/portal/datasets/usps_crosswalk.html
- Census Geocoder: https://geocoding.geo.census.gov/geocoder/
