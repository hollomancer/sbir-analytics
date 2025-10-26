# SBIR ETL Pipeline

A robust ETL (Extract, Transform, Load) pipeline for processing SBIR (Small Business Innovation Research) program data into Neo4j graph database.

## Overview

This project implements a five-stage ETL pipeline that processes SBIR award data from multiple government sources and loads it into a Neo4j graph database for analysis and visualization.

### Pipeline Stages

1. **Extract**: Download and parse raw data from sources (SBIR.gov CSV, USAspending PostgreSQL dump)
2. **Validate**: Schema validation and data quality checks
3. **Enrich**: Augment data with external APIs (SAM.gov, USAspending)
4. **Transform**: Business logic and graph-ready entity preparation
5. **Load**: Write to Neo4j with relationships and constraints

## Architecture

- **Orchestration**: Dagster asset-based pipeline
- **Data Processing**: DuckDB for efficient querying of CSV and PostgreSQL dump data
- **Configuration**: Pydantic-validated YAML configuration with environment overrides
- **Logging**: Structured logging with loguru (JSON for production, pretty for development)
- **Quality Gates**: Configurable data quality checks at each pipeline stage

## SBIR Data Ingestion

### Data Source

The pipeline processes SBIR (Small Business Innovation Research) and STTR (Small Business Technology Transfer) award data from the official SBIR.gov database. The primary data source is a comprehensive CSV export containing historical award information from 1983 to present.

**Data Source**: [SBIR.gov Awards Database](https://www.sbir.gov/awards)
- **Format**: CSV with 42 columns
- **Record Count**: ~533,000 awards (as of 2024)
- **Update Frequency**: Monthly exports available
- **Coverage**: All federal agencies participating in SBIR/STTR programs

### CSV Structure

The SBIR awards CSV contains the following data categories:

| Category | Fields | Description |
|----------|--------|-------------|
| **Company Info** | 7 fields | Company name, address, website, employee count |
| **Award Details** | 7 fields | Title, abstract, agency, phase, program, topic code |
| **Financial** | 2 fields | Award amount, award year |
| **Timeline** | 5 fields | Award date, end date, solicitation dates |
| **Tracking** | 4 fields | Agency tracking number, contract, solicitation info |
| **Identifiers** | 2 fields | UEI (Unique Entity ID), DUNS number |
| **Classifications** | 3 fields | HUBZone, disadvantaged, woman-owned status |
| **Contacts** | 8 fields | Primary contact and PI information |
| **Research Institution** | 3 fields | RI name, POC details (STTR only) |

### Usage Instructions

1. **Download Data**:
   ```bash
   # Download from SBIR.gov (manual process)
   # Place in data/raw/sbir/awards_data.csv
   ```

2. **Configure Pipeline**:
   ```yaml
   # config/base.yaml
   sbir:
     csv_path: "data/raw/sbir/awards_data.csv"
     duckdb:
       database_path: ":memory:"
       table_name: "sbir_awards"
   ```

3. **Run Ingestion**:
   ```bash
   # Start Dagster UI
   poetry run dagster dev

   # Materialize SBIR assets in order:
   # 1. raw_sbir_awards
   # 2. validated_sbir_awards
   # 3. sbir_validation_report
   ```

4. **Monitor Quality**:
   - Check validation pass rate (target: ≥95%)
   - Review quality report for issues
   - Monitor asset check results

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry (for dependency management)
- Docker and Docker Compose (for local development)

### Setup

1. **Clone and install dependencies:**
   ```bash
   git clone <repository-url>
   cd sbir-etl
   poetry install
   ```

2. **Set up data sources:**
   - Download SBIR CSV from SBIR.gov
   - Obtain USAspending PostgreSQL dump
   - Place files in `data/raw/` directory

3. **Configure environment:**
   ```bash
   cp config/dev.yaml config/local.yaml
   # Edit local.yaml with your settings
   ```

4. **Start local services:**
   ```bash
   docker-compose up -d
   ```

5. **Run the pipeline:**
   ```bash
   poetry run dagster dev
   ```

## Configuration

Configuration uses a three-layer system:

- `config/base.yaml`: Default settings (version controlled)
- `config/dev.yaml`: Development overrides
- `config/prod.yaml`: Production settings

Environment variables override YAML values using `SBIR_ETL__SECTION__KEY=value` pattern.

## Development

### Code Quality

```bash
# Format code
poetry run black src tests

# Lint code
poetry run ruff check src tests

# Type check
poetry run mypy src

# Security check
poetry run bandit -r src

# Run tests
poetry run pytest
```

### Continuous Integration

The project uses GitHub Actions for CI/CD with the following checks:

- **Test**: Runs pytest with coverage on Python 3.11 and 3.12
- **Lint**: Code formatting, linting, and type checking
- **Security**: Bandit security vulnerability scanning
- **Docker**: Build verification

CI runs on pushes to `main`/`develop` branches and pull requests.

### Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src --cov-report=html

# Run specific test file
poetry run pytest tests/unit/test_config.py
```

## Project Structure

```
src/
├── extractors/           # Stage 1: Data extraction
├── validators/           # Stage 2: Schema and quality validation
├── enrichers/            # Stage 3: External API enrichment
├── transformers/         # Stage 4: Business logic
├── loaders/              # Stage 5: Neo4j loading
├── assets/               # Dagster asset definitions
├── config/               # Configuration management
├── models/               # Pydantic data models
└── utils/                # Shared utilities

config/                   # Configuration files
├── base.yaml
├── dev.yaml
└── prod.yaml

tests/                    # Test suite
├── unit/
├── integration/
└── e2e/

data/                     # Local data storage (gitignored)
├── raw/
├── validated/
├── enriched/
└── transformed/
```

## Contributing

1. Follow the established code quality standards
2. Write tests for new functionality
3. Update documentation as needed
4. Ensure pipeline stages maintain clear boundaries

## License

[License information]