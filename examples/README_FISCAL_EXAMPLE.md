# SBIR Fiscal Impact Example

This directory contains examples demonstrating the SBIR fiscal impact analysis pipeline.

## Files

- **`sbir_fiscal_impact_example.py`** - Full example requiring R and StateIO packages
- **`sbir_fiscal_impact_example_mock.py`** - Demo version using mock economic multipliers (no R required)

## Quick Start (Mock Version - No R Required)

The mock version provides a demonstration of the pipeline without requiring R installation:

```bash
# Ensure dependencies are installed
uv sync

# Run the mock example
.venv/bin/python examples/sbir_fiscal_impact_example_mock.py
```

The mock version uses simplified economic multipliers to demonstrate the pipeline flow. It's perfect for:

- Understanding how the pipeline works
- Testing integration with your SBIR data
- Development and debugging without R setup

## Running with Real Economic Models (Docker)

For actual fiscal impact calculations using EPA's USEEIOR and StateIO packages, use Docker:

### Prerequisites

- Docker and Docker Compose installed
- 4GB+ available RAM

### Steps

1. **Build the Docker image** (includes R and all required packages):

```bash
docker compose --profile dev build
```

1. **Start the services**:

```bash
docker compose --profile dev up -d
```

1. **Run the real example inside the container**:

```bash
docker compose exec dagster-webserver python examples/sbir_fiscal_impact_example.py
```

The Docker image includes:

- R runtime
- EPA StateIO package (`USEPA/stateior`)
- EPA USEEIOR package (`USEPA/useeior`)
- rpy2 Python-R bridge
- All required R dependencies

## Running with Local R Installation

If you prefer running outside Docker, you need to install R and the required packages:

### 1. Install R

**Ubuntu/Debian:**

```bash
sudo apt-get install r-base r-base-dev
```

**macOS:**

```bash
brew install r
```

**Windows:**
Download from <https://www.r-project.org/>

### 2. Install R Packages

Open R and run:

```r
install.packages('remotes')
remotes::install_github('USEPA/stateior')
remotes::install_github('USEPA/useeior')
```

### 3. Install Python Dependencies

```bash
uv sync --extra r
```

### 4. Run the Example

```bash
.venv/bin/python examples/sbir_fiscal_impact_example.py
```

## Understanding the Output

Both examples produce the following outputs:

### Detailed Impacts

Shows economic impacts by state and BEA sector:

- **award_total**: Total SBIR funding for state/sector
- **production_impact**: Total economic output (GDP contribution)
- **wage_impact**: Labor income generated
- **tax_impact**: Tax revenue (federal + state)
- **jobs_created**: Employment created (full-time equivalents)

### State-Level Summary

Aggregates impacts by state to show regional economic effects.

### Sector-Level Summary

Aggregates impacts by industry sector (BEA classification).

### Key Metrics

- **Production Multiplier**: Total economic output per dollar of SBIR investment
  - Typical range: 1.5x - 3.0x depending on sector
- **Tax Revenue Multiplier**: Tax revenue per dollar invested
  - Typical range: $0.10 - $0.30 per dollar
- **Jobs per $1M**: Employment created per million dollars invested
  - Typical range: 5-15 jobs per $1M

## Differences Between Mock and Real Versions

| Feature | Mock Version | Real Version (R + StateIO) |
|---------|-------------|---------------------------|
| R Installation | Not required | Required |
| Economic Model | Simplified multipliers | EPA USEEIOR/StateIO |
| Accuracy | Demonstration only | Research-grade |
| Speed | Fast (~1 second) | Slower (10-60 seconds) |
| Sector-specific | Basic variation | Detailed 71-sector I-O tables |
| Regional variation | None | State-specific models |
| Use case | Development, testing | Production, research |

## Customizing for Your Data

To use with your own SBIR data:

1. **Load your awards data** into a DataFrame with these required columns:
   - `award_id`: Unique identifier
   - `award_amount`: Dollar amount
   - `state`: Two-letter state code (e.g., "CA")
   - `naics_code`: NAICS industry code (2-6 digits)
   - `fiscal_year`: Year of award

2. **Replace the sample data** in the example:

```python
# Instead of:
awards = create_sample_sbir_awards()

# Use your data:
awards = pd.read_csv("your_sbir_data.csv")
```

1. **Run the calculator**:

```python
calculator = SBIRFiscalImpactCalculator()
impacts = calculator.calculate_impacts_from_sbir_awards(awards)
```

## Troubleshooting

### "rpy2 is not installed" Error

- **Solution 1** (Recommended): Use Docker (see above)
- **Solution 2**: Install R and run `uv sync --extra r`
- **Solution 3**: Use the mock version for development

### R Package Installation Fails

If StateIO/USEEIOR installation fails in R:

```r
# Try installing dependencies first
install.packages(c('arrow', 'dplyr', 'tidyr', 'data.table'))

# Then try again
remotes::install_github('USEPA/stateior')
```

### Memory Issues

StateIO can use significant RAM for state models. If you encounter memory errors:

- Increase Docker memory limit to 4GB+
- Process states in smaller batches
- Use the mock version for development

## Additional Resources

- [EPA USEEIOR Documentation](https://github.com/USEPA/useeior)
- [EPA StateIO Documentation](https://github.com/USEPA/stateior)
- [Project Dockerfile](../Dockerfile) - See how R packages are installed
- [Fiscal Analysis Documentation](../docs/fiscal/) - Technical details

## Questions or Issues?

- Check the [main project README](../README.md)
- Review the [Dockerfile](../Dockerfile) for R setup details
- See `src/transformers/sbir_fiscal_pipeline.py` for implementation details
