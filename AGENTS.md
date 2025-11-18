# AI Agent Instructions

## Specification System

This project uses **Kiro specifications** (`.kiro/specs/`) for all active development, planning, and requirements documentation. Historical OpenSpec content is archived in `archive/openspec/` for reference.

## Project: SBIR Analytics

Graph-based ETL: SBIR awards → Neo4j. Dagster orchestration, DuckDB processing, Docker deployment.

## 🎉 Consolidated Architecture (2025-01-01)

**Major consolidation completed** - 30-60% code duplication reduction achieved:
- ✅ **Unified Assets**: USPTO, CET, transition assets consolidated into single files
- ✅ **Hierarchical Config**: PipelineConfig with 16+ consolidated schemas
- ✅ **Single Docker Compose**: Profile-based configuration (dev, prod, ci-test, e2e)
- ✅ **Unified Models**: Award model replaces separate implementations
- ✅ **Consolidated Utils**: Performance monitoring and utilities streamlined

### Stack

- **Runtime:** Python 3.11+, uv for dependency management, Neo4j Aura (cloud) or Docker (optional)
- **Data:** Dagster assets (consolidated), DuckDB, Pandas, Neo4j 5.x
- **Config:** Hierarchical PipelineConfig + YAML (`config/base.yaml`)
- **CI:** GitHub Actions (pytest, coverage, regression checks)
- **Performance:** Consolidated monitoring (`src/utils/performance_monitor.py`)

### Current State

- Consolidated architecture with 231 Python files in `src/` (well-structured)
- Configuration system: 33/33 tests passing, 88% coverage
- Workflows: ci, deploy, nightly, static-analysis, lambda-deploy, uspto-data-refresh, weekly-award-data-refresh, branch_deployments
- Archived spec: `.kiro/specs/archive/codebase-consolidation-refactor/`

## Key Directories

```text
src/
  extractors/           # SBIR.gov CSV, USAspending dump, USPTO patents
  enrichers/            # Fuzzy matching, chunked processing, spill-to-disk (includes fiscal enrichers)
  transformers/         # Business logic, normalization (includes fiscal transformers)
  loaders/              # Neo4j (idempotent MERGE, relationships)
  assets/               # Consolidated Dagster asset definitions
    ├── uspto_assets.py # Unified USPTO assets (transformation, loading, AI)
    ├── cet_assets.py   # Consolidated CET classification
    ├── transition_assets.py # Unified transition detection
    ├── fiscal_assets.py # Fiscal returns analysis
    ├── ma_detection.py # M&A detection assets
    ├── company_categorization.py # Company categorization assets
    ├── paecter/        # PaECTER embeddings and similarity
    ├── jobs/           # Dagster job definitions (cet, fiscal, transition, uspto, paecter, usaspending)
    └── sensors/        # Dagster sensors (usaspending refresh)
  cli/                  # Command-line interface (commands, display, integration)
  config/schemas.py     # Hierarchical PipelineConfig (16+ consolidated schemas)
  utils/performance_monitor.py # Consolidated monitoring and alerts
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
  deploy.yml            # Deployment workflows
  nightly.yml           # Nightly builds and tests
  static-analysis.yml   # Code quality checks
  lambda-deploy.yml     # Lambda function deployment
  uspto-data-refresh.yml # USPTO data refresh automation
  weekly-award-data-refresh.yml # Weekly award data refresh
  branch_deployments.yml # Branch-based deployments
```

## Workflows

### Local (uv)

```bash
uv sync
uv run dagster dev  # http://localhost:3000
pytest -v --cov=src
```

### Container (Docker)

```bash
make docker-build
make docker-up-dev      # Dev stack with bind mounts
make docker-test        # Run tests in container
```

## Guidelines

### Code Quality:
- Format: `black src tests` (line-length: 100)
- Lint: `ruff check src tests`
- Type: `mypy src`
- Security: `bandit -r src`

### Performance:
- Baselines: `reports/benchmarks/baseline.json` (CI-cached)
- Alerts: `reports/alerts/*.json`
- Thresholds: `config/base.yaml`

### Testing:
- Coverage: ≥80% (CI enforced)
- Isolation: Use `tmp_path`, avoid global state
- Neo4j: Assumes healthy container

### Documentation:
- User changes → README.md
- New data sources → `docs/data/`
- Neo4j changes → `docs/schemas/`

## Common Patterns

**Add monitoring:** Use `performance_monitor.py` decorators, `AlertCollector` for metrics
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
- Data sources: `docs/data/index.md`, `data/raw/uspto/README.md`
- Neo4j schemas: `docs/schemas/patent-neo4j-schema.md`
