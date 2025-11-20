# R Package Reference: StateIO

This document provides reference information for EPA's StateIO (`stateior`) R package used for economic input-output modeling in fiscal returns analysis.

## Overview

### StateIO (`stateior`)

**Purpose**: State-level input-output economic modeling
**Repository**: https://github.com/USEPA/stateior

### Installation

```r
options(repos = c(CRAN = "https://cloud.r-project.org"))
install.packages("remotes")
remotes::install_github("USEPA/stateio")
```

> Setting the `CRAN` mirror once per session with `options(repos = c(CRAN = "https://cloud.r-project.org"))`
> avoids non-interactive installation failures when R has not been configured with a default mirror.

StateIO constructs two-region models for a specific state and the rest of the U.S., detailing industries and commodities at the BEA summary level. It's used for state-level economic impact analysis.

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

### Integration Pattern

**Direct StateIO approach**: Build state models and calculate impacts using StateIO directly:

```r
library(stateior)

## Build state two-region IO table

ca_model <- buildFullTwoRegionIOTable(
  state = "CA",
  year = 2023,
  iolevel = "Summary",
  specs = list(BaseIOSchema = "2017")
)

## Extract Use table and industry output

use_table <- ca_model$DomesticUseTransactions
industry_output <- ca_model$IndustryOutput

## Calculate technical coefficients: A[i,j] = Use[i,j] / Output[j]

tech_coeff <- use_table / industry_output

## Calculate Leontief inverse: L = (I - A)^(-1)

identity <- diag(nrow(tech_coeff))
leontief_inv <- solve(identity - tech_coeff)

## Apply demand shocks: production = L * demand

production_impacts <- leontief_inv %*% demand_vector

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
3. **R Packages**: Install StateIO in R environment

### Docker Installation (Recommended)

The Docker container includes R, rpy2, and the required R package (stateior) pre-installed. No additional setup is needed when using Docker.

```bash
# Build the container (includes R integration)
docker build -t sbir-analytics:latest .

# Run with Docker Compose
docker compose --profile dev up
```

The R packages are installed during the Docker build process in the builder stage and copied to the runtime image. The `r` optional dependency is included in the requirements, so `rpy2` is automatically installed.

### Local Installation (Non-Docker)

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

Start an R console and configure the CRAN mirror (needed for non-interactive sessions) before installing packages:

```r
options(repos = c(CRAN = "https://cloud.r-project.org"))
install.packages("remotes")

## Install StateIO

remotes::install_github("USEPA/stateio")

## Verify installation
library(stateior)
```

**Non-interactive example**:

```bash
R -e "options(repos = c(CRAN = 'https://cloud.r-project.org')); install.packages('remotes'); remotes::install_github('USEPA/stateio')"
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
- rpy2 Documentation: https://rpy2.github.io/

## Implementation Details

### Function Discovery

The actual functions were discovered by:

1. Running `names(getNamespace("stateior"))` in R to list all exported functions
2. Examining function help with `help(function_name)` in R
3. Testing with sample data

### BEA Sector Code Format

- **Summary level**: 2-digit codes like "11", "21", "22"
- **Detail level**: 3-digit codes with optional location suffix
- StateIO expects numeric codes at Summary level for most functions

### Impact Component Extraction

StateIO provides economic components (wages, income, taxes) that can be extracted from:

1. Production impacts from `N` matrix (commodity outputs)
2. Value added ratios from StateIO functions (`getStateGVA`, `getStateEmpCompensation`)
3. Model metadata or separate value added tables

See `docs/fiscal/stateio-api-reference.md` for detailed API documentation.

## References

- **StateIO API Reference**: `docs/fiscal/stateio-api-reference.md`
- StateIO GitHub: https://github.com/USEPA/stateio
- rpy2 Documentation: https://rpy2.github.io/
