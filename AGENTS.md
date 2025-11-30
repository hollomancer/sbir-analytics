# AI Agent Instructions

## Specification System

This project uses **Kiro specifications** (`.kiro/specs/`) for all active development, planning, and requirements documentation. Historical OpenSpec content is archived in `archive/openspec/` for reference.

## Project: SBIR Analytics

Graph-based ETL: SBIR awards → Neo4j. Dagster orchestration, DuckDB processing, Docker deployment.

### Stack

- **Runtime:** Python 3.11+, uv for dependency management, Neo4j Aura (cloud) or Docker (optional)
- **Data:** Dagster assets (consolidated), DuckDB, Pandas, Neo4j 5.x
- **Config:** Hierarchical PipelineConfig + YAML (`config/base.yaml`)
- **CI:** GitHub Actions (pytest, coverage, regression checks)
- **Performance:** Consolidated monitoring (`src/utils/monitoring/`)

### Architecture

The codebase uses a consolidated architecture with well-structured modules:
- **231 Python files** in `src/` organized by ETL stage
- **Configuration system:** 33/33 tests passing, 88% coverage
- **Workflows:** ci, deploy, nightly, weekly, lambda-deploy, data-refresh, build-r-base, run-ml-jobs

## Key Directories

```text
src/
  extractors/           # SBIR.gov CSV, USAspending dump, USPTO patents
  enrichers/            # Fuzzy matching, chunked processing, spill-to-disk (includes fiscal enrichers)
  transformers/         # Business logic, normalization (includes fiscal transformers)
  loaders/              # Neo4j (idempotent MERGE, relationships)
  assets/               # Consolidated Dagster asset definitions
    ├── uspto/          # Unified USPTO assets (transformation, loading, AI)
    ├── cet/            # Consolidated CET classification
    ├── transition/     # Unified transition detection
    ├── fiscal_assets.py # Fiscal returns analysis
    ├── ma_detection.py # M&A detection assets
    ├── company_categorization.py # Company categorization assets
    ├── paecter/        # PaECTER embeddings and similarity
    ├── jobs/           # Dagster job definitions (cet, fiscal, transition, uspto, paecter, usaspending)
    └── sensors/        # Dagster sensors (usaspending refresh)
  cli/                  # Command-line interface (commands, display, integration)
  config/schemas.py     # Hierarchical PipelineConfig (16+ consolidated schemas)
  utils/monitoring/      # Consolidated monitoring and alerts
  utils/quality_*.py     # Baselines, dashboards

config/base.yaml        # Thresholds, paths, performance settings
docs/
  data/                 # Data dictionaries, evaluation guides
  deployment/containerization.md
  schemas/              # Neo4j schemas
.kiro/specs/            # Kiro specifications (active system)
.kiro/steering/         # Agent steering documents (architectural patterns)
archive/openspec/       # Archived OpenSpec content (historical reference)

.github/workflows/
  ci.yml                # Main CI pipeline
  deploy.yml            # Dagster serverless deployment
  nightly.yml           # Nightly security scans and smoke tests
  weekly.yml            # Weekly comprehensive tests
  lambda-deploy.yml     # Lambda function deployment
  data-refresh.yml      # SBIR/USAspending/USPTO data refresh
  build-r-base.yml      # R base image build for fiscal analysis
  run-ml-jobs.yml       # ML job execution (PaECTER, CET)
```

## Workflows & Guidelines

- **Testing & Quality**: See [`docs/testing/index.md`](docs/testing/index.md) for all commands (local, Docker, CI).
- **Development Standards**: See [`CONTRIBUTING.md`](CONTRIBUTING.md) for code quality, formatting, and PR process.
- **Deployment**: See [`docs/deployment/README.md`](docs/deployment/README.md).

## Common Patterns

**Add monitoring:** Use `src.utils.monitoring` decorators and `AlertCollector` for metrics
**Modify CI:** Edit `.github/workflows/*.yml`, upload artifacts to `reports/`
**Add tests:** Place in `tests/unit|integration|e2e/`, run via `pytest -v --cov=src`
**Update Neo4j:** Modify `src/loaders/`, use MERGE operations, document in `docs/schemas/`
**Run fiscal analysis:** Use `fiscal_returns_mvp_job` (core) or `fiscal_returns_full_job` (with sensitivity)
**Run PaECTER analysis:** Use `paecter_job` for embedding generation and award-patent similarity computation
**Use CLI tools:** Run `uv run python -m src.cli.main <command>` for dashboard, metrics, status, and enrichment operations

## References

- Kiro specifications: `.kiro/specs/` (see this file for workflow guidance)
- Agent steering documents: `.kiro/steering/` (architectural patterns and guidance - see `.kiro/steering/README.md`)
- Container guide: `docs/deployment/containerization.md`
- Data sources overview: `docs/data/index.md`
- Data dictionaries: `docs/data/dictionaries/`
- Neo4j schemas: `docs/schemas/patent-neo4j-schema.md`
