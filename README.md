# SBIR ETL Pipeline

A robust ETL (Extract, Transform, Load) pipeline for processing SBIR (Small Business Innovation Research) program data into Neo4j graph database.

### Why This Project?

The federal government provides a vast amount of data on innovation and government funding. However, this data is spread across multiple sources and formats, making it difficult to analyze. This project provides a unified and enriched view of the SBIR ecosystem by:

*   **Connecting disparate data sources:** Integrating SBIR awards, USAspending contracts, and USPTO patent data.
*   **Building a knowledge graph:** Structuring the data in a Neo4j graph database to reveal complex relationships.
*   **Enabling powerful analysis:** Allowing for queries that trace funding, track technology transitions, and analyze patent ownership chains.

## Overview

This project implements a five-stage ETL pipeline that processes SBIR award data from multiple government sources and loads it into a Neo4j graph database for analysis and visualization.

### Pipeline Stages

1. **Extract**: Download and parse raw data (SBIR.gov CSV, USAspending PostgreSQL dump, USPTO patents)
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

### Core Capabilities
- **Dagster Orchestration**: Asset-based pipeline with dependency management and observability
- **DuckDB Processing**: Efficient querying of CSV and PostgreSQL dump data
- **Neo4j Graph Database**: Patent chains, award relationships, technology transition tracking
- **Pydantic Configuration**: Type-safe YAML configuration with environment overrides
- **Docker Deployment**: Multi-stage build with dev, test, and prod profiles

### Performance & Quality
- **Performance Monitoring**: Automatic timing, memory tracking, and alert generation
- **Quality Baselines**: Historical baseline tracking with regression detection
- **CI Regression Pipeline**: Automated performance benchmarking in pull requests
- **Chunked Processing**: Memory-adaptive enrichment with spill-to-disk for large datasets
- **Configurable Thresholds**: Duration warnings, memory limits, and quality gates

#### Enrichment Performance

The enrichment stage includes resilience features for large datasets:

- **Chunked Processing**: Process recipients in batches (default 10k)
- **Memory Monitoring**: Track memory usage via `psutil`
- **Adaptive Chunk Sizing**: Reduce chunk size under memory pressure
- **Spill-to-Disk**: Write chunks to Parquet when memory critical
- **Checkpointing**: Resume from last successful chunk on failure
- **Progress Tracking**: Expose completion percentage and ETA

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

#### Monitoring & Alerts

Performance alerts are generated automatically:

**Alert Types:**
- `DURATION_WARNING` — Enrichment took >5 min
- `MEMORY_WARNING` — Memory increase >500 MB
- `QUALITY_REGRESSION` — Match rate dropped >5%
- `LOAD_FAILURE` — Neo4j load success <99%

**Alert Artifacts:**
```json
{
  "timestamp": "2024-10-26T12:00:00",
  "alert_type": "DURATION_WARNING",
  "severity": "WARNING",
  "message": "Enrichment took 380s (threshold: 300s)",
  "metadata": {
    "duration_seconds": 380,
    "threshold_seconds": 300,
    "records_processed": 533000
  }
}
```

Alerts saved to `reports/alerts/<timestamp>.json` and attached to Dagster asset metadata.


### Observability
- **Alerts**: JSON artifacts with severity levels (INFO, WARNING, FAILURE)
- **Dashboards**: Plotly-based quality dashboards (HTML + JSON fallback)
- **Metrics**: Asset-level performance metrics (duration, records/sec, memory usage)
- **Regression Detection**: Automated comparison against baseline with PR comments

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

## Data Sources

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

### Performance Configuration

Key thresholds in `config/base.yaml`:

```yaml
performance:
  duration_warning_seconds: 300           # Alert if enrichment >5min
  memory_delta_warning_mb: 500            # Alert if memory increase >500MB
  memory_pressure_warn_percent: 75        # Adaptive chunk resize
  memory_pressure_critical_percent: 90    # Spill to disk
  regression_threshold_percent: 5.0       # Fail CI if >5% regression

enrichment:
  match_rate_threshold: 0.70              # Min 70% match rate
  chunk_size: 10000                       # Records per chunk
```

## Development

### Code Quality

```bash
# Format code
poetry run black src tests

# Lint code
poetry run ruff check src tests

# Type check
poetry run mypy src

# Security scan
poetry run bandit -r src

# Run all checks
black src tests && ruff check src tests && mypy src
```

### Testing

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

### Performance Monitoring

The pipeline includes comprehensive performance instrumentation:

**Built-in Monitoring:**
- `src/utils/performance_monitor.py` — Decorators and context managers
- `src/utils/performance_alerts.py` — Alert collection and severity tracking
- `src/utils/quality_baseline.py` — Baseline storage and comparison
- `src/utils/quality_dashboard.py` — Plotly-based dashboards

**Usage in Assets:**
```python
from src.utils.performance_monitor import monitor_performance
from src.utils.performance_alerts import AlertCollector

@monitor_performance
def my_asset(context):
    alert_collector = AlertCollector()
    # ... processing logic ...
    alert_collector.add_alert("duration", duration_seconds, severity="WARNING")
    alert_collector.save_alerts("reports/alerts/")
```

**CI Performance Pipeline:**
- Workflow: `.github/workflows/performance-regression-check.yml`
- Runs on PRs affecting enrichment/assets
- Compares current run to cached baseline
- Posts PR comments with regression analysis
- Fails CI on FAILURE severity regressions

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
