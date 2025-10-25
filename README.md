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