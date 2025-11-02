# R Package Reference: StateIO and USEEIOR

This document provides reference information for EPA's StateIO (`stateior`) and USEEIOR (`useeior`) R packages used for economic input-output modeling in fiscal returns analysis.

## Overview

### StateIO (`stateior`)

**Purpose**: State-level input-output economic modeling  
**Repository**: https://github.com/USEPA/stateior  
**Installation**:
```r
install.packages("remotes")
remotes::install_github("USEPA/stateio")
```

StateIO constructs two-region models for a specific state and the rest of the U.S., detailing industries and commodities at the BEA summary level. It's used for state-level economic impact analysis.

### USEEIOR (`useeior`)

**Purpose**: U.S. Environmentally-Extended Input-Output models  
**Repository**: https://github.com/USEPA/useeior  
**Installation**:
```r
install.packages("remotes")
remotes::install_github("USEPA/useeior")
```

USEEIOR builds and uses national-level environmentally-extended input-output models, incorporating environmental data for comprehensive impact analysis.

## Expected API Patterns

Based on typical input-output modeling patterns, these packages likely provide functions to:

1. **Load/Create Models**: Build or load state-specific or national models
2. **Apply Shocks**: Input spending shocks by sector and location
3. **Compute Multipliers**: Calculate direct, indirect, and induced effects
4. **Extract Impacts**: Retrieve wage, income, tax, and production impacts

### Typical Function Structure

For StateIO (state-level analysis):
```r
# Expected pattern (actual function names may vary):
library(stateior)

# Build or load state model
model <- loadStateModel(state = "CA", year = 2023)

# Apply spending shock
shocks <- data.frame(
  sector = c("11", "21"),
  amount = c(1000000, 500000),
  state = "CA"
)

# Compute impacts
impacts <- computeImpacts(model, shocks)
# Returns: wage_impact, income_impact, tax_impact, production_impact, etc.
```

For USEEIOR (national-level analysis):
```r
# Expected pattern:
library(useeior)

# Load national model
model <- loadUSEEIOModel(year = 2023)

# Apply shocks (national-level, no state dimension)
shocks <- data.frame(
  sector = c("11", "21"),
  amount = c(1000000, 500000)
)

# Compute impacts
impacts <- computeImpacts(model, shocks)
```

## Input Data Format

### StateIO Input Requirements

- **State Code**: Two-letter state abbreviation (e.g., "CA", "NY")
- **BEA Sector Code**: BEA Input-Output sector classification code
- **Fiscal Year**: Year for analysis (e.g., 2023)
- **Shock Amount**: Spending amount in dollars (inflation-adjusted)

Expected DataFrame structure:
```
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

# Activate pandas conversion
pandas2ri.activate()

# Load R package
stateio = importr("stateior")

# Convert pandas DataFrame to R
r_shocks = pandas2ri.py2rpy(shocks_df)

# Call R function (example - actual function names may vary)
r_result = stateio.compute_impacts(model, r_shocks)

# Convert back to pandas
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
2. **Python rpy2**: `poetry install --extras r` or `pip install rpy2`
3. **R Packages**: Install StateIO and USEEIOR in R environment

### Step-by-Step Installation

#### 1. Install R

**macOS**:
```bash
brew install r
```

**Linux**:
```bash
sudo apt-get update
sudo apt-get install r-base
```

**Windows**: Download from https://cran.r-project.org/bin/windows/base/

#### 2. Install R Packages

Start R console and run:
```r
# Install remotes if needed
install.packages("remotes")

# Install StateIO
remotes::install_github("USEPA/stateio")

# Install USEEIOR
remotes::install_github("USEPA/useeior")

# Verify installation
library(stateior)
library(useeior)
```

#### 3. Install Python rpy2

```bash
poetry install --extras r
# or
pip install rpy2
```

#### 4. Verify Installation

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
   - Install rpy2: `poetry install --extras r`
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

## Notes

- Actual function names and APIs should be verified by examining package documentation or source code
- Model versions may affect function signatures
- Some functions may require additional parameters (e.g., year, model type)
- Environmental extensions in USEEIOR add additional output dimensions

