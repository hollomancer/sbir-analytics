# AI Agent Instructions

## Specification System

This project uses **Kiro specifications** (`.kiro/specs/`) for all active development, planning, and requirements documentation. Historical OpenSpec content is archived in `archive/openspec/` for reference.

## Project: SBIR Analytics

Graph-based ETL: SBIR awards → Neo4j. Dagster orchestration, DuckDB processing, Docker deployment.

### Stack

- **Runtime:** Python 3.11+, uv for dependency management, Neo4j (Docker)
- **Data:** Dagster assets (consolidated), DuckDB, Pandas, Neo4j 5.x
- **Config:** Hierarchical PipelineConfig + YAML (`config/base.yaml`)
- **CI:** GitHub Actions (pytest, coverage, regression checks)
- **Performance:** Consolidated monitoring (`sbir_etl/utils/`)

### Architecture

The codebase uses a consolidated architecture with well-structured modules:

- **~317 Python files** across `sbir_etl/` and `packages/` organized by ETL stage
- **Configuration system:** 33/33 tests passing, 88% coverage
- **Workflows:** ci, deploy, nightly, weekly, lambda-deploy, data-refresh, build-r-base, run-ml-jobs

## Key Directories

```text
sbir_etl/                 # Core ETL library
  extractors/           # SBIR.gov CSV, USAspending dump, USPTO patents
  enrichers/            # Fuzzy matching, chunked processing, spill-to-disk (includes fiscal enrichers)
  transformers/         # Business logic, normalization (includes fiscal transformers)
  validators/           # Schema validation and data quality checks
  models/               # Pydantic data models and type definitions
  config/               # Configuration management (schemas.py: 16+ consolidated schemas)
  quality/              # Data quality validation modules
  utils/                # Shared utilities (logging, metrics, monitoring, alerts)

packages/
  sbir-analytics/sbir_analytics/
    assets/             # Consolidated Dagster asset definitions
      ├── uspto/        # Unified USPTO assets (transformation, loading, AI)
      ├── cet/          # Consolidated CET classification
      ├── transition/   # Unified transition detection
      ├── fiscal_assets.py # Fiscal returns analysis
      ├── ma_detection.py # M&A detection assets
      ├── company_categorization.py # Company categorization assets
      ├── paecter/      # PaECTER embeddings and similarity
      ├── jobs/         # Dagster job definitions (cet, fiscal, transition, uspto, paecter, usaspending)
      └── sensors/      # Dagster sensors (usaspending refresh)
    clients/            # Service clients (Dagster, Neo4j, metrics)
    definitions.py      # Dagster repository definitions
  sbir-graph/sbir_graph/
    loaders/            # Neo4j (idempotent MERGE, relationships)
  sbir-ml/sbir_ml/      # ML models (CET classification, transition detection)

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

**Add monitoring:** Use `sbir_etl.utils` decorators and `AlertCollector` for metrics
**Modify CI:** Edit `.github/workflows/*.yml`, upload artifacts to `reports/`
**Add tests:** Place in `tests/unit|integration|e2e/`, run via `pytest -v --cov=sbir_etl`
**Update Neo4j:** Modify `packages/sbir-graph/sbir_graph/loaders/`, use MERGE operations, document in `docs/schemas/`
**Run fiscal analysis:** Use `fiscal_returns_mvp_job` (core) or `fiscal_returns_full_job` (with sensitivity)
**Run PaECTER analysis:** Use `paecter_job` for embedding generation and award-patent similarity computation
**Use scripts:** Run `python scripts/pipeline_status.py`, `python scripts/pipeline_metrics.py`, `python scripts/run_benchmark.py`, or `python scripts/run_transition.py` for pipeline operations

## References

- Kiro specifications: `.kiro/specs/` (see this file for workflow guidance)
- Agent steering documents: `.kiro/steering/` (architectural patterns and guidance - see `.kiro/steering/quick-reference.md`)
- Container guide: `docs/deployment/containerization.md`
- Data sources overview: `docs/data/index.md`
- Data dictionaries: `docs/data/dictionaries/`
- Neo4j schemas: `docs/schemas/patent-neo4j-schema.md`

## Workflow Orchestration

### 1. Plan Node Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
- If something goes sideways, STOP and re-plan immediately - don't keep pushing
- Use plan mode for verification steps, not just building
- Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
- Use subagents liberally to keep main context window clean
- Offload research, exploration, and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents
- One task per subagent for focused execution

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern
- Write rules for yourself that prevent the same mistake
- Ruthlessly iterate on these lessons until mistake rate drops
- Review lessons at session start for relevant project

### 4. Verification Before Done
- Never mark a task complete without proving it works
- Diff behavior between main and your changes when relevant
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
- Skip this for simple, obvious fixes - don't over-engineer
- Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding
- Point at logs, errors, failing tests - then resolve them
- Zero context switching required from the user
- Go fix failing CI tests without being told how

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

## Core Principles

- **Simplicity First**: Make every change as simple as possible. Impact minimal code.
- **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.
