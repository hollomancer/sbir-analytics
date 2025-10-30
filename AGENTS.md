<!-- SPECIFICATION SYSTEM:START -->
# AI Agent Instructions

## Specification System Migration

**Current State**: This project is migrating from OpenSpec to Kiro for specification-driven development.

### When to Use Kiro Specs (Preferred)

Use `.kiro/specs/` for new development:
- Planning new features or capabilities
- Architecture changes and design decisions
- Requirements documentation with EARS patterns
- Task-driven implementation planning

### When to Use OpenSpec (Legacy - Migration Period Only)

Check `openspec/AGENTS.md` during migration period for:
- Existing OpenSpec changes being migrated
- Legacy change proposal workflow
- Historical context and completed work

**Migration Status**: See [OpenSpec to Kiro Migration](.kiro/specs/openspec-to-kiro-migration/requirements.md) for complete migration plan.

<!-- SPECIFICATION SYSTEM:END -->

## Project: SBIR ETL Pipeline

Graph-based ETL: SBIR awards → Neo4j. Dagster orchestration, DuckDB processing, Docker deployment.

### Stack
- **Runtime:** Python 3.11+, Docker/Compose
- **Data:** Dagster assets, DuckDB, Pandas, Neo4j 5.x
- **Config:** Pydantic + YAML (`config/base.yaml`)
- **CI:** GitHub Actions (pytest, coverage, regression checks)
- **Performance:** Alerts, baselines, dashboards (mature infrastructure)

### Current State
- 29 tests (pytest 8.x, serial, ~8-12 min in CI)
- Performance infrastructure: `src/utils/performance_*.py`, `src/utils/quality_*.py`
- Workflows: ci, container-ci, neo4j-smoke, performance-regression-check, secret-scan

## Key Directories

```
src/
  extractors/           # SBIR.gov CSV, USAspending dump, USPTO patents
  enrichers/            # Fuzzy matching, chunked processing, spill-to-disk
  transformers/         # Business logic, normalization
  loaders/              # Neo4j (idempotent MERGE, relationships)
  assets/               # Dagster asset definitions
  utils/performance_*.py # Alerts, baselines, monitoring
  utils/quality_*.py     # Baselines, dashboards

config/base.yaml        # Thresholds, paths, performance settings
docs/
  data/                 # Data dictionaries, evaluation guides
  deployment/containerization.md
  schemas/              # Neo4j schemas
.kiro/specs/            # Kiro specifications (new system)
openspec/               # Legacy specs (being migrated to Kiro)

.github/workflows/
  performance-regression-check.yml  # Benchmark + regression detection
  container-ci.yml                   # Test runner (Docker)
  neo4j-smoke.yml                    # Integration tests
```

## Workflows

### Local (Poetry)
```bash
poetry install
poetry run dagster dev  # http://localhost:3000
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

**Code Quality:**
- Format: `black src tests` (line-length: 100)
- Lint: `ruff check src tests`
- Type: `mypy src`
- Security: `bandit -r src`

**Performance:**
- Baselines: `reports/benchmarks/baseline.json` (CI-cached)
- Alerts: `reports/alerts/*.json`
- Thresholds: `config/base.yaml`

**Testing:**
- Coverage: ≥80% (CI enforced)
- Isolation: Use `tmp_path`, avoid global state
- Neo4j: Assumes healthy container

**Documentation:**
- User changes → README.md
- New data sources → `docs/data/`
- Neo4j changes → `docs/schemas/`

## Common Patterns

**Add monitoring:** Use `performance_monitor.py` decorators, `AlertCollector` for metrics
**Modify CI:** Edit `.github/workflows/*.yml`, upload artifacts to `reports/`
**Add tests:** Place in `tests/unit|integration|e2e/`, run via `pytest -v --cov=src`
**Update Neo4j:** Modify `src/loaders/`, use MERGE operations, document in `docs/schemas/`

## References

- Kiro specifications: `.kiro/specs/` (preferred) or OpenSpec workflow: `openspec/AGENTS.md` (legacy)
- Container guide: `docs/deployment/containerization.md`
- Data sources: `docs/data/usaspending-evaluation.md`, `data/raw/uspto/README.md`
- Neo4j schemas: `docs/schemas/patent-neo4j-schema.md`
