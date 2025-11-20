# Design: Initial Technical Architecture

## Context

The sbir-analytics project processes SBIR (Small Business Innovation Research) program data from multiple government sources into a Neo4j graph database. The pipeline must:

- Handle 250k+ awards with 2.5M+ relationships
- Ingest SBIR data from bulk CSV files (SBIR.gov)
- Query USAspending data from compressed PostgreSQL database
- Enrich data via SAM.gov API
- Support incremental updates
- Maintain high data quality (≥95% completeness)
- Be reproducible and auditable

This is a greenfield project drawing patterns from three production SBIR systems (sbir-fiscal-returns, sbir-transition-classifier, sbir-cet-classifier).

**Stakeholders**: Data engineering team, analysts querying Neo4j graph

**Constraints**:
- Python 3.11+ required
- Neo4j as target database
- Government API rate limits
- Large SBIR CSV files from bulk export
- USAspending provided as compressed PostgreSQL database

## Goals / Non-Goals

**Goals**:
- Establish clear five-stage ETL architecture
- Implement type-safe configuration management
- Set up Dagster orchestration with asset-based design
- Create data quality framework with configurable thresholds
- Enable structured, queryable logging
- Support both full and incremental processing modes

**Non-Goals**:
- Implementing actual data extractors (future changes)
- Building UI/dashboard (Dagster UI sufficient initially)
- Real-time streaming ingestion (batch processing only)
- Multi-tenant support (single deployment)

## Decisions

### 1. Five-Stage ETL Pipeline

**Decision**: Adopt five distinct pipeline stages: Extract → Validate → Enrich → Transform → Load

**Why**:
- Clear separation of concerns
- Quality gates between stages prevent bad data propagation
- Easy to debug (inspect intermediate outputs)
- Supports parallel execution within stages
- Follows proven pattern from production SBIR projects

**Alternatives considered**:
- Three-stage (Extract → Transform → Load): Too coarse-grained, mixes concerns
- Monolithic pipeline: Difficult to debug, no quality gates

**Stage boundaries**:
```
Extract      → raw/*.csv          (files downloaded, basic parsing)
Validate     → validated/pass/    (schema valid, quality checks passed)
Enrich       → enriched/          (external data added)
Transform    → transformed/       (business logic applied, graph-ready)
Load         → Neo4j              (nodes and relationships created)
```

### 2. Dagster for Orchestration

**Decision**: Use Dagster with asset-based design (not op-based)

**Why**:
- Asset-based design naturally maps to data entities (awards, companies, patents)
- Declarative dependency management
- Built-in asset checks for data quality
- Excellent UI for monitoring and debugging
- Native support for partitioning and incremental updates
- Strong typing with Python

**Alternatives considered**:
- Airflow: Heavier operational overhead, task-based (not asset-based)
- Prefect: Less mature, smaller ecosystem
- Plain Python scripts: No orchestration, manual dependency management

**Asset structure**:
```python
@asset
def raw_sbir_awards() -> pd.DataFrame: ...

@asset
def validated_sbir_awards(raw_sbir_awards: pd.DataFrame) -> pd.DataFrame: ...

@asset
def enriched_sbir_awards(validated_sbir_awards: pd.DataFrame) -> pd.DataFrame: ...

# Asset check for quality gate
@asset_check(asset=validated_sbir_awards)
def completeness_check(validated_sbir_awards: pd.DataFrame) -> AssetCheckResult: ...
```

### 3. Configuration Management Architecture

**Decision**: Three-layer system: YAML files → Pydantic validation → Environment overrides

**Why**:
- Type safety via Pydantic prevents configuration errors
- Environment-specific overrides without code changes
- Secrets via environment variables (never in config files)
- Non-technical users can adjust thresholds in YAML
- Validated at startup (fail fast)

**Structure**:
```
config/
├── base.yaml              # Defaults (checked into git)
├── dev.yaml               # Development overrides
├── prod.yaml              # Production settings
└── README.md              # Documentation

src/config/
├── schemas.py             # Pydantic models
└── loader.py              # Load and merge logic
```

**Environment variable pattern**: `SBIR_ETL__SECTION__KEY=value`

**Alternatives considered**:
- Single config file: No environment separation
- .env files only: No validation, error-prone
- Code-based config: Changes require code deploys

### 4. Data Quality Framework

**Decision**: Implement quality checks at each stage with configurable thresholds

**Why**:
- Early detection of data issues
- Automated blocking of bad data
- Configurable thresholds allow tuning without code changes
- Audit trail via Dagster asset checks
- Aligns with production SBIR project patterns

**Quality dimensions** (config/base.yaml):
```yaml
data_quality:
  completeness:
    award_id: 1.00          # 100% required
    company_name: 0.95      # 95% required
  uniqueness:
    award_id: 1.00          # No duplicates
  validity:
    award_amount_min: 0.0
    award_amount_max: 5000000.0
```

**Implementation**: Pydantic models for validation, asset checks for gates

### 5. Structured Logging with loguru

**Decision**: Use loguru for structured, context-aware logging

**Why**:
- Simpler API than stdlib logging
- Native structured logging support
- Easy context injection (stage, run_id)
- JSON output for production (machine-readable)
- Pretty console output for development

**Key features**:
- Automatic exception tracing
- Daily log rotation
- Context variables for pipeline stage tracking
- Performance metrics logging

**Alternatives considered**:
- stdlib logging: More boilerplate, less intuitive
- structlog: More complex configuration

### 6. DuckDB for Data Processing

**Decision**: Use DuckDB to query both SBIR CSV files and USAspending Postgres dump data

**Why**:
- DuckDB can import data from Postgres dump files directly (or read decompressed SQL)
- No need to run a separate PostgreSQL server/container
- Fast analytical queries without loading entire datasets into memory
- SQL interface for complex joins and filtering
- Embeddable (no separate database server)
- Zero-copy data sharing with pandas
- Handles both CSV (SBIR) and Postgres dump (USAspending) formats

**Data sources**:
- **SBIR data**: Bulk CSV export from SBIR.gov → DuckDB or pandas
- **USAspending data**: Compressed PostgreSQL dump → DuckDB import/query

**Usage**:
- Import/decompress Postgres dump into DuckDB on first run (one-time setup)
- Query SBIR CSV files via DuckDB for efficient filtering
- Join USAspending and SBIR data using SQL queries
- Export relevant subsets to pandas DataFrames for processing

**Alternatives considered**:
- Running PostgreSQL container: Operational overhead, unnecessary for read-only queries
- Pandas only: Large files (multi-GB) may exceed memory
- Loading everything into Neo4j: Unnecessary duplication of source data

### 7. Directory Structure

**Decision**: Organize by pipeline stage, not by component type

```
src/
├── extractors/           # Stage 1: Data extraction
│   ├── sbir.py
│   ├── usaspending.py
│   └── patents.py
├── validators/           # Stage 2: Schema and quality validation
│   ├── schemas.py
│   └── quality_checks.py
├── enrichers/            # Stage 3: External API enrichment
│   ├── sam_gov.py
│   └── usaspending_api.py
├── transformers/         # Stage 4: Business logic
│   ├── companies.py
│   ├── awards.py
│   └── patents.py
├── loaders/              # Stage 5: Neo4j loading
│   ├── neo4j_client.py
│   ├── nodes.py
│   └── relationships.py
├── assets/               # Dagster asset definitions
│   ├── sbir_assets.py
│   └── checks.py
├── config/               # Configuration management
│   ├── schemas.py
│   └── loader.py
├── models/               # Pydantic data models
│   ├── award.py
│   └── company.py
└── utils/                # Shared utilities
    ├── logging_config.py
    └── metrics.py

config/                   # Configuration files
├── base.yaml
├── dev.yaml
└── prod.yaml

tests/                    # Testing pyramid
├── unit/                 # 70-80% of tests
├── integration/          # 15-20% of tests
└── e2e/                  # 5-10% of tests

data/                     # Local data storage (gitignored)
├── raw/
├── validated/
├── enriched/
└── transformed/
```

**Why**: Stage-based organization makes pipeline flow obvious, easy to navigate

### 8. Dependency Management

**Decision**: Use Poetry for dependency management

**Why**:
- Modern, deterministic dependency resolution
- Built-in virtual environment management
- Automatic lock file generation (poetry.lock)
- Better handling of transitive dependencies than pip-tools
- Native support for development dependencies

**Core dependencies**:
- dagster, dagster-webserver - Orchestration
- pandas - Data manipulation
- neo4j - Graph database driver
- duckdb - SQL queries on CSV and Postgres dump data
- pydantic - Data validation
- loguru - Structured logging
- pyyaml - Configuration
- typer, rich - CLI
- pytest, black, ruff, mypy - Development tools

### 9. Testing Strategy

**Decision**: Three-layer testing pyramid (Unit 70-80%, Integration 15-20%, E2E 5-10%)

**Why**:
- Fast feedback loop with unit tests
- Integration tests validate cross-stage workflows
- E2E tests ensure full pipeline correctness
- High coverage (≥85%) without excessive test runtime

**Test structure**:
- Unit: Test individual validators, transformers (mock external dependencies)
- Integration: Test extract → validate → enrich flows (use test database)
- E2E: Full Dagster materialization with sample datasets

## Risks / Trade-offs

**Risk**: Dagster learning curve for team unfamiliar with asset-based orchestration
- **Mitigation**: Provide examples, documentation, training session

**Risk**: DuckDB memory usage for very large queries
- **Mitigation**: Monitor memory, implement chunked processing if needed

**Trade-off**: Five stages add complexity vs. three-stage pipeline
- **Rationale**: Quality gates and clear boundaries worth the added structure

**Trade-off**: YAML configuration requires discipline (validation happens at runtime)
- **Rationale**: Pydantic validation catches errors early, benefits outweigh risk

## Migration Plan

N/A - This is initial architecture setup, no migration needed

## Resolved Questions

1. **Dependency management preference**: Poetry vs. pip-tools?
   - **Resolution**: Use Poetry for modern dependency management and deterministic builds

2. **Neo4j deployment**: Aura (managed) vs. self-hosted?
   - **Resolution**: Self-hosted Neo4j via Docker Compose for local development and flexibility

3. **Initial data sources**: Start with SBIR CSV only, or include USAspending?
   - **Resolution**: Start with SBIR CSV and USAspending compressed PostgreSQL dump
   - DuckDB will import/query the Postgres dump (no PostgreSQL server needed)

4. **Docker containerization**: Include in initial setup or defer?
   - **Resolution**: Include Docker and Docker Compose in initial setup
   - docker-compose.yml will define services: Neo4j and application container
