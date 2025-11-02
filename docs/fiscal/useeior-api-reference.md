# USEEIOR API Reference

This document provides reference information for the USEEIOR R package based on actual package exploration.

## Package Information

- **Package**: `useeior`
- **Version**: Tested with v1.7.0+
- **GitHub**: https://github.com/USEPA/useeior
- **Purpose**: National-level Environmentally-Extended Input-Output models

## Key Functions for Fiscal Analysis

### Model Building

#### `buildModel(modelname, configpaths = NULL)`

Build an EEIO model with complete components.

**Parameters**:
- `modelname`: Name of the model from a config file
- `configpaths`: Optional paths to model configuration files

**Returns**: A list of EEIO model complete components and attributes

**Example**:
```r
model <- buildModel("USEEIO2012")
```

#### `buildTwoRegionModels(modelname, configpaths = NULL, validate = FALSE, year = NULL)`

Build two-region models for all 50 states based on a single config reference file.

**Parameters**:
- `modelname`: Name of the model from a config file
- `configpaths`: Optional paths to configuration files
- `validate`: If TRUE, print validation results for each model
- `year`: Optional year to run the models

**Returns**: A list of EEIO models for each state

**Use Case**: Creates state-specific models for fiscal returns analysis

### Impact Calculation

#### `calculateEEIOModel(model, perspective, demand, location = NULL, use_domestic_requirements = FALSE, household_emissions = FALSE, show_RoW = FALSE)`

Calculate total emissions/resources (LCI) and total impacts (LCIA) for an EEIO model.

**Parameters**:
- `model`: A complete EEIO model (list with USEEIO model components)
- `perspective`: "DIRECT" or "FINAL"
  - "DIRECT": Results align with sectors where impacts are produced
  - "FINAL": Results align with sectors consumed by final user
- `demand`: Demand vector - can be:
  - Name of built-in vector: "Production", "Consumption", "CompleteProduction", "CompleteConsumption"
  - Actual demand vector with sector names and USD values
- `location`: Optional location code for demand vector (required for two-region models)
- `use_domestic_requirements`: If TRUE, use domestic demand and L_d matrix
- `household_emissions`: If TRUE, include household emissions
- `show_RoW`: If TRUE, include Rest of World rows

**Returns**: A list with LCI and LCIA results (data.frame format) containing:
- `N`: Direct+indirect flows (LCI)
- `L`: Total requirements matrix
- `H_r`: Total impacts (DIRECT perspective)
- `H_l`: Total impacts (FINAL perspective)

**Example**:
```r
# Calculate impacts for a demand vector
result <- calculateEEIOModel(
  model = state_model,
  perspective = "DIRECT",
  demand = custom_demand_vector,
  location = "CA"
)
```

### Demand Vector Functions

#### `formatDemandVector(model, demand)`

Format a demand vector for use with calculateEEIOModel.

#### `extractAndFormatDemandVector(model, demand_name)`

Extract and format a built-in demand vector from the model.

### Available Models

#### `seeAvailableModels()`

List all available model specifications.

## Model Structure

A USEEIO model object contains:

- **Matrices**:
  - `L`: Leontief inverse (total requirements matrix)
  - `L_d`: Domestic Leontief inverse
  - `B`: Satellite matrix (environmental flows)
  - `M`: Total flows matrix
  - `V`: Market shares matrix
  - `N`: Direct+indirect flows

- **Demand Vectors** (in `DemandVectors`):
  - `Production`: US production
  - `Consumption`: US consumption
  - `CompleteProduction`: Complete production
  - `CompleteConsumption`: Complete consumption

- **Sectors**: List of BEA sector codes
- **Indicators**: Environmental impact indicators
- **Metadata**: Model year, version, etc.

## Integration with StateIO

USEEIOR's `buildTwoRegionModels()` can create state-specific models. These can then be used with `calculateEEIOModel()` using state-specific demand vectors.

**Pattern**:
```r
# Build state models (all states at once)
state_models <- buildTwoRegionModels("USEEIO2012", year = 2023)

# Get California model
ca_model <- state_models[["CA"]]

# Create demand vector for shocks
demand <- formatDemandVector(ca_model, shocks_dataframe)

# Calculate impacts
impacts <- calculateEEIOModel(
  model = ca_model,
  perspective = "DIRECT",
  demand = demand,
  location = "CA"
)
```

## Impact Component Extraction

From `calculateEEIOModel()` results:

- **Economic components** may be in:
  - `N` matrix: Commodity outputs (can derive production impact)
  - Model `L` matrix: Total requirements
  - Value added components: Wages, taxes, GOS (from model metadata or separate extraction)

- **Note**: USEEIOR primarily focuses on environmental impacts. Economic components (wages, income, taxes) may need extraction from:
  - Model value added tables
  - Separate calculation using model matrices
  - Integration with StateIO value added functions

## Additional Functions

### Analysis Functions
- `calculateFlowContributiontoImpact()` - Flow contribution analysis
- `calculateSectorContributiontoImpact()` - Sector contribution analysis
- `calculateMarginSectorImpacts()` - Margin sector impacts

### Validation Functions
- `compareFlowTotals()` - Compare flow totals
- `printValidationResults()` - Print validation results

### Export Functions
- `writeModeltoXLSX()` - Write model to Excel
- `writeModelMatrices()` - Write matrices to CSV
- `writeModelforAPI()` - Write model for API

## Notes for Fiscal Returns Integration

1. **State-Level Models**: Use `buildTwoRegionModels()` to create state-specific models
2. **Demand Vectors**: Format spending shocks as demand vectors
3. **Economic Components**: May need to extract value added components separately from environmental impacts
4. **Perspective**: Use "DIRECT" for fiscal analysis (aligns with where production occurs)
5. **Location Code**: Required for two-region models (e.g., "CA" for California)

