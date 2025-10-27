# SBIR ETL Pipeline

## CET (Critical and Emerging Technologies) Pipeline

This repository includes an end-to-end CET pipeline that classifies SBIR awards into CET areas, aggregates company-level CET profiles, and loads both enrichment properties and relationships into Neo4j.

### Run the full CET pipeline

You can execute the full CET job via Dagster:

```
dagster job execute -f src/definitions.py -j cet_full_pipeline_job
```

Requirements:
- Neo4j reachable via environment variables:
  - NEO4J_URI (e.g., bolt://localhost:7687)
  - NEO4J_USERNAME
  - NEO4J_PASSWORD
- Minimal CET configs under config/cet:
  - taxonomy.yaml
  - classification.yaml

Alternatively, run from the Dagster UI and select the job “cet_full_pipeline_job”.

### Assets included in the CET pipeline

The job orchestrates these assets in dependency order:
- cet_taxonomy
- cet_award_classifications
- cet_company_profiles
- neo4j_cetarea_nodes
- neo4j_award_cet_enrichment
- neo4j_company_cet_enrichment
- neo4j_award_cet_relationships
- neo4j_company_cet_relationships

### Neo4j schema for CET

See the CET graph schema documentation:
- docs/schemas/cet-neo4j-schema.md

This document covers:
- CETArea node schema and constraints
- Award/Company CET enrichment properties
- Award → CETArea APPLICABLE_TO relationships
- Company → CETArea SPECIALIZES_IN relationships
- Idempotent MERGE semantics and re-run safety

### CI

A dedicated CI workflow runs a tiny-fixture CET pipeline to catch regressions end-to-end:
- .github/workflows/cet-pipeline-ci.yml

This spins up a Neo4j service, builds minimal CET configs and sample awards, and executes the cet_full_pipeline_job, uploading resulting artifacts (processed outputs and Neo4j checks).

Performance baseline initialization

To enable automated regression detection against a baseline, initialize the CET performance baseline from existing processed artifacts. The initializer computes baseline coverage and specialization thresholds and writes them to `reports/benchmarks/baseline.json`. Run the initializer locally or in CI (after producing the processed artifacts) with:

    python scripts/init_cet_baseline.py \
      --awards-parquet data/processed/cet_award_classifications.parquet \
      --companies-path data/processed/cet_company_profiles.parquet

Once the baseline is created, the performance/regression job will compare current runs to the saved baseline and surface alerts when thresholds are exceeded. The baseline file is retained by CI artifacts and can be updated with the `--force` or `--set-thresholds` flags as needed.

A robust ETL (Extract, Transform, Load) pipeline for processing SBIR (Small Business Innovation Research) program data into Neo4j graph database.

### Why This Project?

The federal government provides a vast amount of data on innovation and government funding. However, this data is spread across multiple sources and formats, making it difficult to analyze. This project provides a unified and enriched view of the SBIR ecosystem by:

*   **Connecting disparate data sources:** Integrating SBIR awards, USAspending contracts, USPTO patents, and other publicly available data.
*   **Building a knowledge graph:** Structuring the data in a Neo4j graph database to reveal complex relationships.
*   **Enabling powerful analysis:** Allowing for queries that trace funding, track technology transitions, and analyze patent ownership chains.

## Overview

This project implements a five-stage ETL pipeline that processes SBIR award data from multiple government sources and loads it into a Neo4j graph database for analysis and visualization.

### Pipeline Stages

1. **Extract**: Download and parse raw data (SBIR.gov CSV, USAspending PostgreSQL dump, USPTO patent DTAs)
2. **Validate**: Schema validation and data quality checks
3. **Enrich**: Augment data with fuzzy matching and external enrichment
4. **Transform**: Business logic and graph-ready entity preparation
5. **Load**: Write to Neo4j with idempotent operations and relationship chains

```
+-----------+      +------------+      +----------+      +-------------+      +--------+
|  Extract  |----->|  Validate  |----->|  Enrich  |----->|  Transform  |----->|  Load  |
+-----------+      +------------+      +----------+      +-------------+      +--------+
    |                  |                   |                   |                  |
 (Python/           (Pydantic)         (DuckDB/            (Python/           (Neo4j/
  Pandas)                             Fuzzy-matching)      Pandas)            Cypher)
```

## Features

- **Dagster Orchestration**: Asset-based pipeline with dependency management and observability
- **DuckDB Processing**: Efficient querying of CSV and PostgreSQL dump data
- **Neo4j Graph Database**: Patent chains, award relationships, technology transition tracking
- **Pydantic Configuration**: Type-safe YAML configuration with environment overrides
- **Docker Deployment**: Multi-stage build with dev, test, and prod profiles

#### Quality Gates

Configurable thresholds enforce data quality:

```yaml
# config/base.yaml
enrichment:
  match_rate_threshold: 0.70      # Min 70% match rate

validation:
  pass_rate_threshold: 0.95       # Min 95% pass rate

loading:
  load_success_threshold: 0.99    # Min 99% load success
```

**Asset Checks:**
- `enrichment_quality_regression_check` — Compare to baseline
- `patent_load_success_rate` — Verify Neo4j load success
- `assignment_load_success_rate` — Verify relationship creation

## Quick Start

### Prerequisites

- **Python**: 3.11 or 3.12
- **Poetry**: For dependency management
- **Docker**: For containerized development
- **Neo4j**: 5.x (provided via Docker Compose)

### Container Development (Recommended)

The project provides Docker Compose for a consistent development and testing environment.

1. **Set up environment:**
   ```bash
   cp .env.example .env
   # Edit .env: set NEO4J_USER, NEO4J_PASSWORD
   ```

2. **Build and start services:**
   ```bash
   make docker-build
   make docker-up-dev
   ```

3. **Run the pipeline:**
   Open your browser to [http://localhost:3000](http://localhost:3000) and materialize the assets to run the pipeline.

4. **Run tests in container:**
   ```bash
   make docker-test
   ```

5. **View logs:**
   ```bash
   make docker-logs SERVICE=dagster-webserver
   ```

See `docs/deployment/containerization.md` for full details.

### Local Development (Alternative)

1. **Clone and install dependencies:**
   ```bash
   git clone <repository-url>
   cd sbir-etl
   poetry install
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with Neo4j credentials and data paths
   ```

3. **Start Dagster UI:**
   ```bash
   poetry run dagster dev
   # Open http://localhost:3000 and materialize the assets.
   ```

4. **Run tests:**
   ```bash
   pytest -v --cov=src --cov-report=html
   ```

## Bulk Data Sources

### SBIR Awards
- **Source**: [SBIR.gov Awards Database](https://www.sbir.gov/awards)
- **Format**: CSV with 42 columns
- **Records**: ~533,000 awards (1983–present)
- **Update**: Monthly exports available

### USAspending
- **Source**: PostgreSQL database dump
- **Size**: 51GB compressed
- **Purpose**: Award enrichment, transaction tracking, technology transition detection
- **Coverage**: Federal contract and grant transactions

### USPTO Patents
- **Source**: [USPTO Patent Assignment Dataset](https://www.uspto.gov/learning-and-resources/patent-assignment-data)
- **Format**: CSV, Stata (.dta), Parquet
- **Purpose**: Patent ownership chains, SBIR-funded patent tracking

## Configuration

Configuration uses a three-layer system:

```
config/
├── base.yaml          # Defaults (version controlled)
├── dev.yaml           # Development overrides
└── prod.yaml          # Production settings
```

Environment variables override YAML using `SBIR_ETL__SECTION__KEY=value`:

```bash
export SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
export SBIR_ETL__ENRICHMENT__MATCH_RATE_THRESHOLD=0.75
```

## Testing

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=src --cov-report=html

# Run specific test
poetry run pytest tests/unit/test_config.py -v

# Container tests
make docker-test
```

**Test Suite:**
- 29 tests across unit, integration, and E2E
- Coverage target: ≥80% (CI enforced)
- Serial execution: ~8-12 minutes in CI

## Project Structure

```
sbir-etl/
├── src/
│   ├── extractors/              # Stage 1: Data extraction
│   ├── validators/              # Stage 2: Schema validation
│   ├── enrichers/               # Stage 3: External enrichment
│   │   └── chunked_enrichment.py  # Memory-adaptive processing
│   ├── transformers/            # Stage 4: Business logic
│   ├── loaders/                 # Stage 5: Neo4j loading
│   ├── assets/                  # Dagster asset definitions
│   │   ├── sbir_ingestion.py
│   │   ├── sbir_usaspending_enrichment.py  # w/ metrics
│   │   └── uspto_*.py
│   ├── config/                  # Configuration management
│   ├── models/                  # Pydantic data models
│   └── utils/
│       ├── performance_monitor.py      # Timing/memory tracking
│       ├── performance_alerts.py       # Alert collection
│       ├── quality_baseline.py         # Baseline management
│       └── quality_dashboard.py        # Plotly dashboards
│
├── config/                      # YAML configuration
│   ├── base.yaml                # Defaults + thresholds
│   ├── dev.yaml                 # Development overrides
│   └── prod.yaml                # Production settings
│
├── tests/                       # Test suite (29 tests)
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── scripts/
│   ├── benchmark_enrichment.py           # Baseline creation
│   └── detect_performance_regression.py  # CI regression check
│
├── docs/
│   ├── data/                    # Data dictionaries
│   ├── deployment/              # Container guides
│   └── schemas/                 # Neo4j schema docs
│
├── reports/                     # Generated artifacts (gitignored)
│   ├── benchmarks/baseline.json     # Cached baseline
│   ├── alerts/                      # Performance alerts
│   └── dashboards/                  # Quality dashboards
│
├── .github/workflows/
│   ├── ci.yml                       # Standard CI
│   ├── container-ci.yml             # Docker test runner
│   ├── neo4j-smoke.yml              # Integration tests
│   ├── performance-regression-check.yml  # Benchmark pipeline
│   └── secret-scan.yml
│
└── openspec/                    # Specifications (see openspec/AGENTS.md)
    ├── specs/                   # Current capabilities
    └── changes/                 # Proposed changes
```

## Neo4j Graph Model

**Node Types:**
- `Award` — SBIR/STTR awards with company, agency, phase, amount
- `Company` — Awardee companies with contact info, location
- `Patent` — USPTO patents linked to SBIR-funded research
- `PatentAssignment` — Patent transfer transactions
- `PatentEntity` — Assignees and assignors (normalized names)

**Relationship Types:**
- `RECEIVED` — Company → Award
- `GENERATED_FROM` — Patent → Award (SBIR-funded patents)
- `OWNS` — Company → Patent (current ownership)
- `ASSIGNED_VIA` — Patent → PatentAssignment
- `ASSIGNED_FROM` — PatentAssignment → PatentEntity
- `ASSIGNED_TO` — PatentAssignment → PatentEntity
- `CHAIN_OF` — PatentAssignment → PatentAssignment (ownership history)

**Query Examples:**

```cypher
# Find all awards for a company
MATCH (c:Company {name: "Acme Inc"})-[:RECEIVED]->(a:Award)
RETURN a.title, a.amount, a.phase

# Trace patent ownership chain
MATCH path = (p:Patent)-[:ASSIGNED_VIA*]->(pa:PatentAssignment)
WHERE p.grant_doc_num = "7123456"
RETURN path

# Find SBIR-funded patents with assignments
MATCH (a:Award)<-[:GENERATED_FROM]-(p:Patent)-[:ASSIGNED_VIA]->(pa:PatentAssignment)
WHERE a.company_name = "Acme Inc"
RETURN p.title, pa.assignee_name, pa.recorded_date
```

## Continuous Integration

GitHub Actions workflows:

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | Push to main/develop, PRs | Standard CI (lint, test, security) |
| `container-ci.yml` | Push to main/develop, PRs | Docker build + test (serial, ~8-12 min) |
| `neo4j-smoke.yml` | Push to main/develop, PRs | Neo4j integration tests |
| `performance-regression-check.yml` | PRs (enrichment changes) | Benchmark + regression detection |
| `secret-scan.yml` | Push to main/develop, PRs | Secret leak detection |

**Performance Regression CI:**
- Runs on enrichment/asset changes
- Compares to cached baseline (`reports/benchmarks/baseline.json`)
- Posts PR comment with duration/memory/match_rate deltas
- Sets GitHub Check status (success/failure)
- Uploads artifacts (regression JSON, HTML report)


## Documentation

- **Data Sources**: `docs/data/usaspending-evaluation.md`, `data/raw/uspto/README.md`
- **Deployment**: `docs/deployment/containerization.md`
- **Schemas**: `docs/schemas/patent-neo4j-schema.md`
- **OpenSpec**: `openspec/AGENTS.md` (change proposal workflow)

## Contributing

1. Follow code quality standards (black, ruff, mypy, bandit)
2. Write tests for new functionality (≥80% coverage)
3. Update documentation as needed
4. Use OpenSpec for architectural changes (see `openspec/AGENTS.md`)
5. Ensure performance regression checks pass in CI

## License

This project is licensed under the [MIT License](LICENSE). Copyright (c) 2025 Conrad Hollomon.
