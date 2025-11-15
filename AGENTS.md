<!-- SPECIFICATION SYSTEM:START -->

# AI Agent Instructions

##Using Kiro Specs

Use `.kiro/specs/` for all development work:

- Planning new features or capabilities
- Architecture changes and design decisions
- Requirements documentation with EARS patterns
- Task-driven implementation planning
- Design documentation and implementation tasks

<!-- SPECIFICATION SYSTEM:END -->

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

- Consolidated architecture with 153 Python files in `src/` (well-structured)
- Configuration system: 33/33 tests passing, 88% coverage
- Workflows: ci, container-ci, neo4j-smoke, performance-regression-check, secret-scan
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
    └── transition_assets.py # Unified transition detection
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
  performance-regression-check.yml  # Benchmark + regression detection
  container-ci.yml                   # Test runner (Docker)
  neo4j-smoke.yml                    # Integration tests
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
cp .env.example .env    # Set NEO4J_USER/PASSWORD
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

## References

- Kiro specifications: `.kiro/specs/` (see this file for workflow guidance)
- Agent steering documents: `.kiro/steering/` (architectural patterns and guidance - see `.kiro/steering/README.md`)
- Container guide: `docs/deployment/containerization.md`
- Data sources: `docs/data/index.md`, `data/raw/uspto/README.md`
- Neo4j schemas: `docs/schemas/patent-neo4j-schema.md`
