# Fiscal Impact Analysis Granularity

## Summary

| Dimension | Currently Supported | Granularity Level | Notes |
|-----------|-------------------|------------------|-------|
| **Geographic (State)** | ✅ **YES** | State-level | 50 states + DC + territories |
| **Geographic (Congressional District)** | ❌ **NO** | Not implemented | Can be added (see below) |
| **Industry/Sector** | ✅ **YES** | BEA 71-sector | NAICS → BEA mapping |
| **Time** | ✅ **YES** | Fiscal year | Year-over-year analysis |

## Current Capabilities

### ✅ State-Level Analysis

The system **fully supports state-level fiscal impact analysis**:

```python
# Example: Aggregate impacts by state
state_summary = calculator.calculate_summary_by_state(impacts)

# Output columns:
# - state: Two-letter state code (CA, NY, TX, etc.)
# - total_awards: Total SBIR funding in that state
# - total_tax_impact: Tax revenue generated
# - total_jobs_created: Employment created
# - total_wage_impact: Wage income generated
# - total_production_impact: Total economic output
```

**State Resolution Process:**
- Extracts state from company address, city/state fields, or ZIP code
- Validates against 50 states + DC + territories (PR, VI, GU, AS, MP)
- Uses GeographicResolver with 90%+ resolution rate
- Confidence scores track resolution quality

**Data Sources for State:**
1. Direct state field in SBIR data
2. Parsed from company address
3. City/state field combinations
4. ZIP code lookup (if implemented)
5. Enriched company data from SAM.gov

### ✅ Industry/Sector Analysis

The system **fully supports industry-level fiscal impact analysis** using BEA sectors:

```python
# Example: Aggregate impacts by industry sector
sector_summary = calculator.calculate_summary_by_sector(impacts)

# Output columns:
# - bea_sector: BEA sector code (54, 31-33, 62, etc.)
# - sector_description: Human-readable name
# - total_awards: Total SBIR funding in that sector
# - total_tax_impact: Tax revenue from that sector
# - total_jobs_created: Employment in that sector
```

**Sector Mapping Process:**
1. SBIR awards contain NAICS codes (6-digit industry codes)
2. `NAICSBEAMapper` maps NAICS → BEA Summary sectors
3. BEA has ~71 sectors (Agriculture, Manufacturing, Professional Services, Healthcare, etc.)
4. Economic models (StateIO/USEEIOR) use BEA sectors for I-O calculations

**Example NAICS → BEA Mappings:**
- NAICS 541512 (Computer Systems Design) → BEA 54 (Professional/Scientific/Technical)
- NAICS 334220 (Broadcasting Equipment Mfg) → BEA 31-33 (Manufacturing)
- NAICS 621111 (Physician Offices) → BEA 62 (Healthcare)
- NAICS 541714 (Biotech R&D) → BEA 54 (Professional/Scientific/Technical)

### ✅ Combined State × Industry Analysis

The system produces **cross-tabulated results** showing impacts by state AND sector:

```python
# Detailed impacts DataFrame includes both dimensions:
impacts_df = calculator.calculate_impacts_from_sbir_awards(awards)

# Output includes:
# - state: CA, NY, TX, etc.
# - bea_sector: 54, 31-33, 62, etc.
# - fiscal_year: 2023, 2024, etc.
# - award_total: Total SBIR $ for this state/sector/year
# - production_impact: Economic output multiplier effect
# - wage_impact: Labor income generated
# - tax_impact: Tax revenue (federal + state)
# - jobs_created: Employment (FTE)
```

This allows you to answer questions like:
- "What's the fiscal impact of biotech SBIR awards in Massachusetts?"
- "Which states generate the most tax revenue from manufacturing SBIR awards?"
- "How do economic multipliers vary by state and industry?"

### ✅ Time-Series Analysis

The system supports **year-over-year comparisons**:

```python
# Filter by fiscal year
impacts_2023 = impacts[impacts['fiscal_year'] == 2023]
impacts_2024 = impacts[impacts['fiscal_year'] == 2024]

# Compare growth rates
state_growth = (
    impacts.groupby(['state', 'fiscal_year'])['tax_impact']
    .sum()
    .unstack()
)
```

## Missing Capability: Congressional Districts

### ❌ Congressional District Analysis (Not Currently Supported - But Very Feasible!)

Congressional district-level analysis is **NOT implemented** but is **very feasible to add**.

**Why It's Very Feasible:**
1. ✅ SBIR award data **INCLUDES full addresses** (company_address, city, state, ZIP)
2. ✅ GeographicResolver infrastructure already exists for state resolution
3. ✅ Multiple free APIs available for geocoding (Census Geocoder)
4. ✅ Proof-of-concept implementation created (`examples/congressional_district_resolution.py`)

**Minor Considerations:**
- ZIP codes can span multiple congressional districts (use full address for accuracy)
- Congressional districts change every 10 years (track which Congress boundaries used)
- API rate limits (Census API is free but rate-limited)

**What Would Be Required:**

#### 1. Data Enrichment
Add congressional district to the Award model:

```python
# In src/models/award.py
class Award(BaseModel):
    # ... existing fields ...

    # New fields for congressional district
    congressional_district: str | None = Field(
        None,
        description="Congressional district (e.g., 'CA-12', 'NY-14')"
    )
    congressional_district_confidence: float | None = Field(
        None,
        description="Confidence in district assignment (0-1)"
    )
```

#### 2. Geographic Enrichment Service
Enhance GeographicResolver to resolve districts:

```python
# In src/enrichers/geographic_resolver.py
class GeographicResolver:
    def resolve_congressional_district(
        self,
        address: str = None,
        city: str = None,
        state: str = None,
        zip_code: str = None
    ) -> CongressionalDistrictResult:
        """Resolve congressional district from address components."""
        # Options:
        # 1. Use US Census Geocoder API (free, rate-limited)
        # 2. Use Google Civic Information API (requires API key)
        # 3. Use local ZIP-to-district mapping (approximate)
        # 4. Use full address geocoding + district shapefile lookup
```

#### 3. Data Sources

**Option A: ZIP Code Approximate Mapping**
- Pros: Fast, no API calls
- Cons: Approximate (ZIPs can span districts)
- Source: HUD ZIP-to-Congressional District crosswalk

**Option B: Census Geocoder API** (Recommended)
- Pros: Authoritative, free
- Cons: Rate limits, requires full address
- URL: https://geocoding.geo.census.gov/geocoder/geographies/address

**Option C: Google Civic Information API**
- Pros: Accurate, handles current districts
- Cons: Requires API key, costs money
- URL: https://developers.google.com/civic-information

#### 4. Update Fiscal Pipeline

```python
# In src/transformers/sbir_fiscal_pipeline.py
class SBIRFiscalImpactCalculator:
    def calculate_impacts_from_sbir_awards(
        self,
        awards_df: pd.DataFrame,
        granularity: str = "state"  # NEW: "state" or "district"
    ) -> pd.DataFrame:
        """Calculate impacts at specified geographic granularity."""

        if granularity == "district":
            # Resolve congressional districts
            awards_df = self._resolve_districts(awards_df)

            # Aggregate to district/sector/year
            shocks = self._aggregate_to_districts(awards_df)

            # Note: StateIO models work at state level only
            # Would need to either:
            # 1. Run state-level I-O, then allocate to districts
            # 2. Use simplified district-level multipliers
```

#### 5. Limitations with StateIO

**Important:** EPA's StateIO package provides economic models at the **state level only**, not district level.

Two approaches to handle this:

**Approach A: Allocation Method** (Recommended)
1. Calculate state-level impacts using StateIO
2. Allocate impacts to districts based on award distribution
3. Add metadata indicating this is an allocation

```python
# Pseudo-code
state_impacts = stateio.calculate_impacts(state_shocks)

# Allocate to districts proportionally
district_allocation = (
    awards_by_district.groupby(['state', 'district'])['award_amount']
    .sum() / awards_by_state.groupby('state')['award_amount'].sum()
)

district_impacts = state_impacts.merge(district_allocation)
district_impacts['tax_impact'] = (
    district_impacts['state_tax_impact'] *
    district_impacts['allocation_share']
)
district_impacts['allocation_method'] = 'proportional'
```

**Approach B: Simplified Multipliers**
- Use national or state multipliers without full I-O modeling
- Faster but less accurate
- Document as "estimated" rather than "modeled"

#### 6. Example Implementation

```python
# examples/sbir_fiscal_impact_by_district.py

# Step 1: Enrich with congressional districts
from src.enrichers.geographic_resolver import CongressionalDistrictResolver

district_resolver = CongressionalDistrictResolver()
awards_with_districts = district_resolver.resolve_districts(awards_df)

# Step 2: Calculate state-level impacts (using StateIO)
calculator = SBIRFiscalImpactCalculator()
state_impacts = calculator.calculate_impacts_from_sbir_awards(awards_df)

# Step 3: Allocate to districts
from src.transformers.fiscal.district_allocator import allocate_to_districts

district_impacts = allocate_to_districts(
    state_impacts=state_impacts,
    awards_with_districts=awards_with_districts
)

# Step 4: Summary by district
district_summary = district_impacts.groupby('congressional_district').agg({
    'award_total': 'sum',
    'tax_impact_allocated': 'sum',
    'jobs_created_allocated': 'sum'
})

print(district_summary)
# Output:
#   congressional_district  award_total  tax_impact_allocated  jobs_created_allocated
#   CA-12                   $2,500,000   $650,000              19.2
#   CA-18                   $1,200,000   $312,000              9.1
#   NY-14                   $750,000     $195,000              5.8
```

## Use Cases by Granularity

### State-Level (✅ Supported)
- **Policy Analysis**: Compare state SBIR program effectiveness
- **Budget Allocation**: Justify federal R&D spending by state
- **Economic Development**: Show state-level return on investment
- **Legislative Reporting**: Report to state legislatures

### Congressional District (❌ Not Supported - But Can Add)
- **Congressional Reporting**: Show impact in each representative's district
- **Campaign Materials**: Document job creation in specific districts
- **Appropriations Justification**: Defend SBIR budget at district level
- **Constituent Services**: Answer "how many jobs in my district?"

### Industry/Sector (✅ Supported)
- **Technology Focus**: Compare biotech vs. IT vs. manufacturing impacts
- **Portfolio Analysis**: Understand which sectors have best ROI
- **Strategic Planning**: Identify high-multiplier sectors for targeting
- **Agency Comparison**: Compare DOD vs. NIH vs. NSF sector portfolios

### Combined Analysis (✅ Supported: State × Sector)
- **Cluster Analysis**: Identify regional industry clusters
- **Competitive Advantage**: Find state/sector combinations with highest impact
- **Gap Analysis**: Identify underserved state/sector combinations

## Recommendations

### For Immediate Use (Current System)
1. ✅ Use state-level analysis for geographic breakdowns
2. ✅ Use sector-level analysis for industry comparisons
3. ✅ Use state × sector cross-tabs for detailed insights
4. ✅ Export to CSV/Excel for further analysis in BI tools

### To Add Congressional District Support

**Good News:** A proof-of-concept implementation is available at `examples/congressional_district_resolution.py`

1. **Phase 1 (Quick Win)**: ZIP-to-District approximate mapping
   - Download HUD ZIP-to-Congressional District crosswalk file
   - Add `congressional_district` field to Award model
   - Extend GeographicResolver with `resolve_congressional_district()` method
   - Simple proportional allocation of state impacts
   - Timeline: **2-3 days** (since we already have addresses and infrastructure)

2. **Phase 2 (Production Quality)**: Full geocoding with Census API
   - Integrate Census Geocoder API (free, authoritative)
   - Already have address validation in GeographicResolver
   - Track resolution confidence scores (pattern already established)
   - Add rate limiting and caching
   - Timeline: **1-2 weeks** (infrastructure exists, just need API integration)

3. **Phase 3 (Advanced)**: District-specific modeling
   - Research district-level economic data sources
   - Develop district-level multipliers (if possible)
   - Validate against known outcomes
   - Timeline: 3-6 months (research project)

## Available Address Data

SBIR awards include complete address information:

```python
# Fields available in Award model:
- company_address / address1 / address2  # Street address
- company_city                           # City
- company_state                          # State (2-letter code)
- company_zip                            # ZIP code (5 or 9 digit)
```

This means we have everything needed to resolve congressional districts!

See `examples/congressional_district_resolution.py` for a working proof-of-concept.

## Example Queries Supported

### ✅ Currently Supported
```python
# "What's the total tax impact by state?"
impacts.groupby('state')['tax_impact'].sum().sort_values(ascending=False)

# "Which industry sectors create the most jobs per million invested?"
(impacts.groupby('bea_sector')['jobs_created'].sum() /
 impacts.groupby('bea_sector')['award_total'].sum() * 1_000_000)

# "Show California's professional services impacts"
ca_prof = impacts[
    (impacts['state'] == 'CA') &
    (impacts['bea_sector'] == '54')
]

# "Compare 2023 vs 2024 tax revenue by state"
impacts.pivot_table(
    values='tax_impact',
    index='state',
    columns='fiscal_year',
    aggfunc='sum'
)
```

### ⚠️ NOT Currently Supported (But Easy to Add - See examples/congressional_district_resolution.py)
```python
# "What's the tax impact in Nancy Pelosi's district (CA-11)?"
# → Add CongressionalDistrictResolver (2-3 days work)

# "How many jobs created in swing district NY-19?"
# → Add CongressionalDistrictResolver (2-3 days work)

# "Compare impacts across all Texas congressional districts"
# → Add CongressionalDistrictResolver (2-3 days work)

# Proof-of-concept implementation:
from examples.congressional_district_resolution import CongressionalDistrictResolver

resolver = CongressionalDistrictResolver(method="census_api")
enriched = resolver.enrich_awards_with_districts(awards_df)

# Then aggregate by district
district_impacts = enriched.groupby('congressional_district').agg({
    'award_amount': 'sum',
    'tax_impact_allocated': 'sum'
})
```

## Implementation Priority

Based on typical stakeholder needs:

1. **High Priority** (Already implemented ✅)
   - State-level reporting
   - Industry/sector analysis
   - State × Sector cross-tabs
   - Time-series analysis

2. **Medium Priority** (Could add if needed)
   - Congressional district allocation
   - Metro area analysis
   - County-level breakdowns

3. **Low Priority** (Usually not needed)
   - ZIP code level (too granular, privacy concerns)
   - Census tract level (micro-level analysis)

## Questions?

- **"Can I see impacts for my state?"** → ✅ YES, fully supported
- **"Can I compare biotech vs. software impacts?"** → ✅ YES, via BEA sectors
- **"Can I see impacts by congressional district?"** → ❌ NO, not currently supported, but can be added (see above)
- **"Can I see year-over-year trends?"** → ✅ YES, via fiscal_year grouping
- **"Can I export to Excel for my own analysis?"** → ✅ YES, all results are pandas DataFrames

---

**Bottom Line:**
- ✅ State + Industry analysis: Fully supported, production-ready
- ❌ Congressional district: Not currently supported, but feasible to add with 1-6 weeks of work depending on accuracy needs
- ✅ The mock example demonstrates all currently supported granularity levels
