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

## USAspending Data Evaluation

The pipeline uses USAspending data for SBIR award enrichment and technology transition detection. Due to the dataset size (~51GB compressed), evaluation is performed directly from removable media without copying to local storage.

### Removable Media Workflow

1. **Mount Drive**:
   ```bash
   # Insert "X10 Pro" drive - automatically mounts at /Volumes/X10 Pro
   ls /Volumes/X10\ Pro/usaspending-db-subset_20251006.zip
   ```

2. **Profile Dataset**:
   ```bash
   # Generate profiling report
   python scripts/profile_usaspending_dump.py --output reports/usaspending_subset_profile.json

   # Check profiling stats
   python scripts/get_usaspending_stats.py --check-available
   ```

3. **Assess Coverage**:
   ```bash
   # Evaluate enrichment potential
   python scripts/assess_usaspending_coverage.py --output reports/usaspending_coverage_assessment.json
   ```

### Key Findings

- **Data Source**: PostgreSQL dump subset with transaction, award, and recipient tables
- **Coverage Target**: ≥70% match rate between SBIR awards and USAspending transactions
- **Enrichment Fields**: UEI/DUNS matching, NAICS codes, place of performance, agency details
- **Transition Detection**: Competition data, award history, obligated amounts

### Documentation

- **Evaluation Guide**: `docs/data/usaspending-evaluation.md`
- **Profiling Report**: `reports/usaspending_subset_profile.md`
- **Coverage Assessment**: `reports/usaspending_coverage_assessment.json`

## Quick Start

### Prerequisites

- Python 3.11+
- Poetry (for dependency management)
- Docker and Docker Compose (for local development)

### Recommended workflows

This project supports two primary development workflows: a local Python-based workflow (Poetry + local services) and a containerized workflow (Docker Compose). Use the containerized workflow for consistent dev/test environments and for CI parity; use the local Python workflow when iterating on quick code changes without rebuilding images.

### Local (Poetry) Setup

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

4. **Start local services (if using Docker for services):**
   ```bash
   docker-compose up -d
   ```

5. **Run the pipeline (Dagster dev):**
   ```bash
   poetry run dagster dev
   ```

### Container quick-start (recommended)

The repository provides Compose overlays and Makefile helpers to run the project inside containers for development and CI. See `docs/deployment/containerization.md` for full details.

1. Copy the environment template and set local test credentials (do not commit `.env`):
   ```bash
   cp .env.example .env
   # Edit .env and set NEO4J_USER / NEO4J_PASSWORD (local dev values)
   ```

2. Build the runtime image (multi-stage Dockerfile):
   ```bash
   make docker-build
   # or use the CI-friendly build script:
   ./scripts/ci/build_container.sh
   ```

3. Start the development stack (bind-mounts for live-editing):
   ```bash
   make docker-up-dev
   # OR
   docker compose --env-file .env --profile dev -f docker-compose.yml -f docker/docker-compose.dev.yml up --build
   ```

4. Run an ad-hoc ETL command inside the image:
   ```bash
   docker compose -f docker-compose.yml -f docker/docker-compose.dev.yml run --rm etl-runner -- python -m src.scripts.run_some_job --arg value
   ```

5. Run containerized tests (ephemeral Neo4j + pytest inside the built image):
   ```bash
   make docker-test
   # OR
   docker compose --env-file .env -f docker-compose.yml -f docker/docker-compose.test.yml up --abort-on-container-exit --build
   ```

6. Tail logs or exec into a running service:
   ```bash
   make docker-logs SERVICE=dagster-webserver
   make docker-exec SERVICE=dagster-webserver CMD="sh"
   # Dagster UI should be available at http://localhost:3000 by default
   ```

### Configuration and docs

- Use `config/docker.yaml` for non-sensitive container defaults. Do not store secrets in config files.
- The entrypoint scripts load `.env` and `/run/secrets/*` and will wait for Neo4j and Dagster web to be healthy before starting services.
- For full operational details, healthcheck semantics, and troubleshooting steps, see:
  `docs/deployment/containerization.md`


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

This project is licensed under the [MIT License](LICENSE). Copyright (c) 2025 Conrad Hollomon.
