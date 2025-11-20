# StateIO API Reference

This document provides reference information for the StateIO (`stateior`) R package based on actual package exploration.

## Package Information

- **Package**: `stateior`
- **Version**: Tested with v0.4.0+
- **GitHub**: https://github.com/USEPA/stateio
- **Purpose**: Generate US state Make and Use tables for building regionalized input-output models

## Key Functions for Fiscal Analysis

### Building State Models

#### `buildFullTwoRegionIOTable(state, year, iolevel = "Summary", specs, ICF_sensitivity_analysis = FALSE, adjust_by = 0, domestic = TRUE, model = NULL, disagg = NULL)`

Build a full two-region IO table for specified state and rest of US for a given year.

### Parameters

- `state`: Two-letter state code (e.g., "CA", "NY")
- `year`: Year of interest (numeric)
- `iolevel`: BEA sector level - currently only "Summary" (can be "Detail" or "Sector" in future)
- `specs`: List of model specs including 'BaseIOSchema'
- `ICF_sensitivity_analysis`: Logical, conduct sensitivity analysis on ICF
- `adjust_by`: Numeric 0-1, manual adjustment to ICF if SA conducted
- `domestic`: Logical, use Domestic Use tables (default TRUE)
- `model`: Optional model object with state tables
- `disagg`: Optional disaggregation specs

**Returns**: A list containing two-region IO tables:
- Make tables (state and RoW)
- Use tables (state and RoW)
- Domestic Use tables
- Commodity and industry outputs
- Other regionalized components

### Example

```r
ca_io <- buildFullTwoRegionIOTable(
  state = "CA",
  year = 2023,
  iolevel = "Summary",
  specs = list(BaseIOSchema = "2017")
)
```

#### `buildStateUseModel(year, specs, ...)`

Build a state use model for all 52 states/regions (including DC and Overseas).

### Parameters

- `year`: Year of interest
- `specs`: Model specifications

**Returns**: List of state use models

#### `buildStateSupplyModel(year, specs, ...)`

Build a state supply model for all 52 states/regions.

#### `buildTwoRegionUseModel(state, year, iolevel, specs, ...)`

Build a two-region Use model for a specific state.

### Assembling IO Tables

#### `assembleTwoRegionIO(state, year, iolevel, specs, ...)`

Assemble two-region make, use, domestic use, and Use tables as well as commodity and industry outputs.

### Value Added and Economic Components

#### `getStateGVA(state, year, specs)`

Get state Gross Value Added (GVA) data.

**Returns**: GVA components including:
- Employee compensation (wages)
- Proprietor income
- Gross operating surplus (GOS)
- Taxes

#### `getStateEmpCompensation(state, year, specs)`

Get state employee compensation by BEA Summary sector.

#### `getStateGOS(state, year, specs)`

Get state Gross Operating Surplus by BEA Summary sector.

#### `getStateTax(state, year, specs)`

Get state tax data by BEA Summary sector.

#### `assembleStateSummaryGrossValueAdded(year, specs)`

Assemble Summary-level gross value added sectors (V001, V002, V003) for all states.

### Employment Data

#### `getStateEmploymentTable(year, specs)`

Get a table of state employment by BEA Summary sector.

**Returns**: Data frame with employment count by state and BEA Summary sector.

#### `getStateEmploymentbyBEASummary(state, year, specs)`

Get state employment by BEA Summary sector for a specific state.

### Data Loading

#### `loadStateIODataFile(filename, ver = NULL)`

Load StateIO data file from Data Commons or local data directory.

### Parameters

- `filename`: Filename string (e.g., "State_Summary_Use_2017")
- `ver`: Optional version string (default NULL, can be "v0.1.0")

**Available files** (from Data Commons):
- Use tables
- DomesticUse tables
- IndustryOutput tables
- Other state IO data products

**Returns**: StateIO data product (usually a list of dataframes)


## Workflow for Fiscal Returns Analysis

### Step 1: Build State Two-Region Model

```r

## Build full two-region IO table for California, 2023

ca_model <- buildFullTwoRegionIOTable(
  state = "CA",
  year = 2023,
  iolevel = "Summary",
  specs = list(BaseIOSchema = "2017")
)
```

### Step 2: Get Value Added Components

```r

## Get Gross Value Added (includes wages, proprietor income, GOS, taxes)

ca_gva <- getStateGVA(state = "CA", year = 2023, specs = specs)

## Or get components separately

wages <- getStateEmpCompensation(state = "CA", year = 2023, specs = specs)
gos <- getStateGOS(state = "CA", year = 2023, specs = specs)
taxes <- getStateTax(state = "CA", year = 2023, specs = specs)
```

### Step 3: Apply Shocks and Calculate Impacts

StateIO creates the IO tables, and impact calculation uses direct matrix multiplication:

```r

## Get Leontief inverse from assembled IO tables

L <- solve(I - A)  # Where A is technical coefficients matrix

## Apply demand shock

production_impact <- L %*% demand_vector

## Extract value added components

wage_impact <- wages_ratio %*% production_impact
gos_impact <- gos_ratio %*% production_impact
tax_impact <- taxes_ratio %*% production_impact
```

## Sector Codes

StateIO uses BEA sector codes at Summary level (15 sectors) or Detail level (71 sectors).

Common formats:

- Summary: "11", "21", "22", etc. (2-digit codes)
- With location: "11/CA", "21/CA" (for two-region models)
- Full format: May include "/US" suffix

## Integration Patterns

### Direct StateIO Matrix Calculation

1. Build state IO tables
2. Extract technical coefficients matrix (A)
3. Calculate Leontief inverse (L = (I-A)^-1)
4. Apply demand shocks
5. Extract value added components from model tables

## Key Exported Functions (102 total)

### Model Building

- `buildFullTwoRegionIOTable()` - Primary function for state IO tables
- `buildStateUseModel()` - Build use models for all states
- `buildStateSupplyModel()` - Build supply models for all states
- `buildTwoRegionUseModel()` - Build two-region use model
- `assembleTwoRegionIO()` - Assemble complete IO tables

### Value Added/Economic Data

- `getStateGVA()` - Gross Value Added
- `getStateEmpCompensation()` - Employee compensation (wages)
- `getStateGOS()` - Gross Operating Surplus
- `getStateTax()` - Tax data
- `getStateEmploymentTable()` - Employment data

### Data Loading

- `loadStateIODataFile()` - Load from Data Commons or local

### Formatting


## Notes for Fiscal Returns Integration

1. **State Codes**: Use 2-letter abbreviations (CA, NY, TX, etc.)
2. **Year**: Ensure year matches available data
3. **Sector Level**: Currently "Summary" level (15 sectors) supported
4. **Model Building**: `buildFullTwoRegionIOTable()` is the primary entry point
5. **Value Added**: Use `getStateGVA()` or individual component functions
6. **Integration**: Use direct StateIO matrix calculation for economic impact analysis
7. **Caching**: Model building can be expensive - cache results

## Python Integration

The Python adapter (`RStateIOAdapter`) uses direct StateIO matrix calculation:

1. Builds state IO table with `buildFullTwoRegionIOTable()`
2. Extracts Use table and industry output vectors
3. Calculates technical coefficients matrix: `A[i,j] = Use[i,j] / Output[j]`
4. Computes Leontief inverse: `L = (I - A)^(-1)`
5. Applies demand shocks: `production = L * demand`
6. Applies StateIO GVA ratios for value added components

### Value Added Ratio Extraction

The adapter uses actual StateIO data:
1. Fetches GVA components (wages, GOS, taxes) from StateIO for each state
2. Converts R data structures to pandas DataFrames
3. Calculates sector-specific ratios of each component relative to total value added
4. Applies these actual ratios instead of hardcoded defaults

### Quality Flags

Impact results include quality flags indicating computation method:

- `stateio_direct_with_ratios`: Direct matrix calculation + actual GVA ratios (highest quality)
- `stateio_direct_default_ratios`: Direct matrix calculation + default ratios (medium quality)
- `stateio_failed:{error}`: StateIO computation failed
- `placeholder_computation`: R packages unavailable (lowest quality)

### Example Usage

```python
from src.transformers.r_stateio_adapter import RStateIOAdapter
import pandas as pd
from decimal import Decimal

adapter = RStateIOAdapter()

shocks = pd.DataFrame({
    "state": ["CA"],
    "bea_sector": ["11"],
    "fiscal_year": [2023],
    "shock_amount": [Decimal("1000000")]
})

results = adapter.compute_impacts(shocks)
# Results include sector-specific value added impacts with quality flags
# Uses direct StateIO matrix calculation
```

### Matrix Calculation Functions

New helper functions for direct StateIO calculations:

- `extract_use_table_from_model()`: Extract Use table from StateIO model
- `extract_industry_output_from_model()`: Extract industry output vector
- `calculate_technical_coefficients()`: Calculate A matrix from Use table
- `calculate_leontief_inverse()`: Calculate L = (I-A)^-1
- `apply_demand_shocks()`: Apply shocks using matrix multiplication
