# R Package Reference: StateIO and USEEIOR

This document provides reference information for EPA's StateIO (`stateior`) and USEEIOR (`useeior`) R packages used for economic input-output modeling in fiscal returns analysis.

## Overview

### StateIO (`stateior`)

**Purpose**: State-level input-output economic modeling
**Repository**: https://github.com/USEPA/stateior

### Installation

```r
install.packages("remotes")
remotes::install_github("USEPA/stateio")
```

StateIO constructs two-region models for a specific state and the rest of the U.S., detailing industries and commodities at the BEA summary level. It's used for state-level economic impact analysis.

### USEEIOR (`useeior`)

**Purpose**: U.S. Environmentally-Extended Input-Output models
**Repository**: https://github.com/USEPA/useeior

### Installation

```r
install.packages("remotes")
remotes::install_github("USEPA/useeior")
```

USEEIOR builds and uses national-level environmentally-extended input-output models, incorporating environmental data for comprehensive impact analysis.

## Actual API Functions

### StateIO (`stateior`) Functions

Key functions discovered from package exploration:

#### Model Building

- `buildFullTwoRegionIOTable(state, year, iolevel, specs)` - Build two-region IO table for a state
- `buildStateUseModel(year, specs)` - Build state use model for all states
- `buildStateSupplyModel(year, specs)` - Build state supply model
- `buildTwoRegionUseModel(state, year, iolevel, specs)` - Build two-region use model

#### Value Added Data

- `getStateGVA(state, year, specs)` - Get Gross Value Added data
- `getStateEmpCompensation(state, year, specs)` - Get employee compensation (wages)
- `getStateGOS(state, year, specs)` - Get Gross Operating Surplus
- `getStateTax(state, year, specs)` - Get tax data

#### Data Loading

- `loadStateIODataFile(filename, ver)` - Load StateIO data from Data Commons or local directory

### USEEIOR (`useeior`) Functions

Key functions discovered from package exploration:

#### Model Building

- `buildModel(modelname, configpaths)` - Build EEIO model
- `buildTwoRegionModels(modelname, configpaths, validate, year)` - Build models for all 50 states
- `buildIOModel(modelname, configpaths)` - Build IO model (economic components only)

#### Impact Calculation

- `calculateEEIOModel(model, perspective, demand, location, ...)` - Calculate impacts with demand vector
  - Returns list with `N` (LCI), `L` (requirements), `H_r` (DIRECT impacts), `H_l` (FINAL impacts)
- `formatDemandVector(model, demand)` - Format demand vector for use with calculateEEIOModel

#### Model Information

- `seeAvailableModels()` - List available model specifications

### Integration Pattern

**Recommended approach**: Use USEEIOR's `buildTwoRegionModels()` which integrates StateIO internally:

```r
library(useeior)
library(stateior)

## Build state models (integrates StateIO)

state_models <- buildTwoRegionModels("USEEIO2012", year = 2023)

## Get state-specific model

ca_model <- state_models[["CA"]]

## Create demand vector from shocks

demand <- formatDemandVector(ca_model, shocks_df)

## Calculate impacts

impacts <- calculateEEIOModel(
  model = ca_model,
  perspective = "DIRECT",
  demand = demand,
  location = "CA"
)

## Extract production impacts from N matrix

production_impacts <- impacts$N

## Get value added components from StateIO

va <- getStateGVA(state = "CA", year = 2023, specs = specs)
wages <- getStateEmpCompensation(state = "CA", year = 2023, specs = specs)
```

## Input Data Format

### StateIO Input Requirements

- **State Code**: Two-letter state abbreviation (e.g., "CA", "NY")
- **BEA Sector Code**: BEA Input-Output sector classification code
- **Fiscal Year**: Year for analysis (e.g., 2023)
- **Shock Amount**: Spending amount in dollars (inflation-adjusted)

Expected DataFrame structure:

```text
state | bea_sector | fiscal_year | shock_amount

------|------------|-------------|--------------

CA    | 11         | 2023        | 1000000
CA    | 21         | 2023        | 500000
```

### Output Data Format

Expected impact components:

- `wage_impact`: Wage and salary impacts
- `proprietor_income_impact`: Proprietor income impacts
- `gross_operating_surplus`: Business surplus impacts
- `consumption_impact`: Consumption effects
- `tax_impact`: Tax revenue impacts
- `production_impact`: Total production multiplier

## Implementation Notes

### rpy2 Integration

When using rpy2 to call R functions from Python:

```python
import rpy2.robjects as ro
from rpy2.robjects.packages import importr
from rpy2.robjects import pandas2ri

## Activate pandas conversion

pandas2ri.activate()

## Load R package

stateio = importr("stateior")

## Convert pandas DataFrame to R

r_shocks = pandas2ri.py2rpy(shocks_df)

## Call R function (example - actual function names may vary)

r_result = stateio.compute_impacts(model, r_shocks)

## Convert back to pandas

result_df = pandas2ri.rpy2py(r_result)
```

### Error Handling

Common R package errors:

- Package not installed: `Error in library(stateior) : there is no package called 'stateior'`
- Missing dependencies: Check for required R dependencies
- Invalid inputs: R functions may throw errors for invalid sector codes or states

### Caching Considerations

- Model building can be expensive - cache model objects
- Impact computations for identical shocks should be cached
- Cache keys should include: state, sector, year, shock_amount, model_version

## Installation Instructions

### System Requirements

1. **R Runtime**: Install R (https://www.r-project.org/)
2. **Python rpy2**: `uv sync --extra r` or `pip install rpy2`
3. **R Packages**: Install StateIO and USEEIOR in R environment

### Step-by-Step Installation

#### 1. Install R

### macOS

```bash
brew install r
```

### Linux

```bash
sudo apt-get update
sudo apt-get install r-base
```

**Windows**: Download from https://cran.r-project.org/bin/windows/base/

#### 2. Install R Packages

Start R console and run:

```r

## Install remotes if needed

install.packages("remotes")

## Install StateIO

remotes::install_github("USEPA/stateio")

## Install USEEIOR

remotes::install_github("USEPA/useeior")

## Verify installation

library(stateior)
library(useeior)
```

###3. Install Python rpy2

```bash
uv sync --extra r

## or

pip install rpy2
```

###4. Verify Installation

Test R integration:

```python
from rpy2.robjects.packages import importr

try:
    stateio = importr("stateior")
    print("StateIO package loaded successfully")
except Exception as e:
    print(f"Error loading StateIO: {e}")
```

## Troubleshooting

### Common Issues

1. **rpy2 Import Error**
   - Ensure R is installed and in PATH
   - Install rpy2: `uv sync --extra r`
   - Check R_HOME environment variable if needed

2. **R Package Not Found**
   - Verify packages installed in correct R library
   - Check R library path: `Rscript -e ".libPaths()"`
   - Reinstall packages in R console

3. **Data Conversion Errors**
   - Ensure pandas2ri.activate() is called
   - Check DataFrame column types match R expectations
   - Verify Decimal values converted to float for R

4. **Model Loading Failures**
   - Check model version compatibility
   - Verify state codes are valid (2-letter abbreviations)
   - Ensure BEA sector codes match model specifications

### Debug Mode

Enable R debug output:

```python
import rpy2.robjects as ro
ro.r('options(warn = 2)')  # Convert warnings to errors
ro.r('options(show.error.messages = TRUE)')  # Show error messages
```

## References

- StateIO GitHub: https://github.com/USEPA/stateio
- USEEIOR GitHub: https://github.com/USEPA/useeior
- USEEIO Project: https://github.com/USEPA/USEEIO
- rpy2 Documentation: https://rpy2.github.io/

## Implementation Details

### Function Discovery

The actual functions were discovered by:

1. Running `names(getNamespace("stateior"))` in R to list all exported functions
2. Running `names(getNamespace("useeior"))` in R to list all exported functions
3. Examining function help with `help(function_name)` in R
4. Testing with sample data

### BEA Sector Code Format

- **Summary level**: 2-digit codes like "11", "21", "22"
- **Detail level**: 3-digit codes with optional location suffix
- StateIO expects numeric codes at Summary level for most functions
- USEEIOR models may use different sector coding schemes depending on model version

### Model Versions

Available USEEIOR models (from `seeAvailableModels()`):

- `USEEIO2012` - 2012 base model
- `USEEIOv2.0.1-411` - Version 2.0.1 with 411 sectors
- `USEEIOv2.3-GHG` - Version 2.3 with GHG focus
- `USEEIOv2.3-s-GHG-19` - State-level version

### Impact Component Extraction

USEEIOR's `calculateEEIOModel()` primarily returns environmental impacts. Economic components (wages, income, taxes) need to be extracted from:

1. Production impacts from `N` matrix (commodity outputs)
2. Value added ratios from StateIO functions (`getStateGVA`, `getStateEmpCompensation`)
3. Model metadata or separate value added tables

See `docs/fiscal/useeior-api-reference.md` and `docs/fiscal/stateio-api-reference.md` for detailed API documentation.

## References

- **StateIO API Reference**: `docs/fiscal/stateio-api-reference.md`
- **USEEIOR API Reference**: `docs/fiscal/useeior-api-reference.md`
- StateIO GitHub: https://github.com/USEPA/stateio
- USEEIOR GitHub: https://github.com/USEPA/useeior
- rpy2 Documentation: https://rpy2.github.io/
