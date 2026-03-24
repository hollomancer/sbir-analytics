---

Type: Decision
Owner: conrad.hollomon@pm.me
Last-Reviewed: 2026-03-24
Status: draft

---

# ADR: ETL Library Extraction Evaluation

## Context

We're evaluating whether to extract the ETL pipeline from `sbir-analytics` into a
standalone library that other applications can consume. The motivation is reuse: other
apps could benefit from our SBIR extraction, enrichment, and transformation capabilities
without depending on Dagster, Neo4j, or our CLI.

### Current Architecture

The ETL pipeline is organized into four clean stages within `src/`:

| Stage | Location | Lines | Purpose |
|-------|----------|-------|---------|
| Extract | `src/extractors/` | ~4.6K | SBIR CSV (DuckDB), USAspending DB, USPTO patents, SAM.gov, SBIR.gov API |
| Enrich | `src/enrichers/` | ~9.3K | Fuzzy matching, company categorization, geographic resolution, patent similarity |
| Transform | `src/transformers/` | ~3.8K | Normalization, categorization, fiscal pipeline, NAICS-BEA mapping |
| Load | `src/loaders/neo4j/` | ~2.8K | Neo4j graph loading with idempotent MERGE |

Supporting modules that ETL depends on:
- `src/models/` — Pydantic data models (~20 files)
- `src/config/` — YAML-based hierarchical config with env var overrides
- `src/utils/` — Cloud storage, DuckDB client, caching, date parsing, async tools
- `src/exceptions.py` — Shared exception hierarchy

Orchestration lives in `src/assets/` (Dagster asset definitions) and `src/assets/jobs/`
(Dagster job definitions). The CLI lives in `src/cli/`.

## Analysis

### What's Decoupled (Easy to Extract)

**Extractors** have the cleanest dependency profile. They import only from `models`,
`config`, and `utils` — never from enrichers, transformers, loaders, CLI, or Dagster.
An external app could use `SbirDuckDBExtractor` or `ContractExtractor` directly today
with minimal wrapping.

**Transformers** are mostly pure functions operating on DataFrames or model objects.
`company_categorization.py` depends only on `models.categorization`. The fiscal pipeline
(`sbir_fiscal_pipeline.py`) is self-contained within the transformers package.

**Data models** (`src/models/`) use lazy loading and have almost no internal dependencies
beyond `utils.common.date_utils`. They're already suitable for packaging standalone.

### What's Coupled (Hard to Extract)

**Enrichers** have the deepest dependency graph. `company_categorization.py` imports from
extractors, config, exceptions, utils (cache, async), and the USAspending enricher. The
`ChunkedEnricher` depends on `psutil` for memory monitoring and has spill-to-disk
behavior tied to local filesystem assumptions.

**Neo4j loaders** are inherently tied to our graph schema (Award, Company, Patent nodes
with specific relationship types). Another app would need the same Neo4j schema or
wouldn't use these at all.

**Configuration** uses a singleton `get_config()` pattern with `config/base.yaml`
hardcoded as the default path. Every enricher and most extractors call `get_config()`
directly rather than accepting config as a parameter — this is the single biggest
coupling obstacle.

**Dagster orchestration** (`src/assets/`, `src/definitions.py`) is tightly coupled to
the ETL modules but is a one-way dependency: assets import ETL, ETL never imports assets.
This means extraction doesn't require touching Dagster code.

### Dependency Weight

The current `pyproject.toml` has 24 runtime dependencies. A library consumer would
inherit all of them unless we made heavy deps optional. Key heavyweight dependencies:

- **Required by extractors**: `duckdb`, `pandas`, `pyarrow`, `boto3`, `cloudpathlib`
- **Required by enrichers**: `rapidfuzz`, `jellyfish`, `httpx`, `spacy`, `scikit-learn`
- **Required by transformers**: `pydantic` (already light)
- **Required by loaders**: `neo4j`
- **Not needed by library**: `dagster`, `typer`, `rich`

A minimal "extract-only" library would still pull in DuckDB, pandas, boto3, and pyarrow
— around 200MB of dependencies.

### Who Would Consume This?

This is the critical question. Potential consumers:

1. **Internal analytics notebooks** — already import from `src/` directly
2. **Separate web API** — would need models + extractors, maybe enrichers
3. **Other government analytics projects** — would need SBIR-specific extractors
4. **Data science pipelines** — would need models + transformers

Use case (1) doesn't need a library — it already works. Use cases (2-4) are hypothetical.

### Maintenance Cost

Extracting to a library means:
- **Versioning**: Two packages to version, release, and keep compatible
- **Testing**: Tests split across two repos, integration tests needed for compatibility
- **Config**: Library needs its own config mechanism (can't assume `base.yaml` exists)
- **CI/CD**: Separate publish pipeline for the library
- **API stability**: Library consumers expect stable interfaces; internal code can change freely

With a team of one (based on commit history), this overhead is significant relative to
the reuse benefit.

## Decision

**Do not extract a separate library at this time.** The costs outweigh the benefits given:

1. No concrete external consumers exist today
2. The configuration coupling (`get_config()` singleton) would require significant
   refactoring to make the ETL usable outside this project
3. Maintaining two packages with one contributor adds friction without clear payoff
4. Internal consumers (notebooks, CLI) already import `src/` directly

### Recommended Preparatory Steps Instead

If library extraction becomes warranted later, these low-cost changes would make it
much easier:

1. **Dependency injection for config** — Refactor extractors/enrichers to accept config
   as a parameter instead of calling `get_config()` globally. This is the single highest-
   leverage change. Example:

   ```python
   # Before (coupled)
   class SbirDuckDBExtractor:
       def __init__(self):
           self.config = get_config()

   # After (injectable)
   class SbirDuckDBExtractor:
       def __init__(self, config: SbirConfig | None = None):
           self.config = config or get_config()
   ```

2. **Separate `sbir-models` package** — The models are already nearly standalone. Publishing
   them as a lightweight package (~5 files, only depends on pydantic) would let other apps
   share data structures without pulling in the full ETL.

3. **Make Neo4j loaders optional** — Move `neo4j` from required to optional dependencies
   in `pyproject.toml` with a `[neo4j]` extra. This is good practice regardless of
   library extraction.

4. **Namespace the package** — The current `src/` package name would conflict if installed
   alongside other projects. Rename to `sbir_etl/` or use a namespace package
   (`sbir.etl`).

## Consequences

**Positive:**
- No additional maintenance burden
- Internal code can evolve freely without worrying about API stability
- Preparatory steps (config injection, optional deps) improve the codebase regardless

**Negative:**
- If a concrete consumer appears, extraction will take more effort than if done now
- Other projects can't pip-install our extractors

**Neutral:**
- The modular directory structure is already good — no architectural debt accumulating

## Alternatives Considered

### Full extraction now
Extracting all ETL into `sbir-etl` library immediately. Rejected because there are no
concrete consumers, and the config coupling means this is weeks of work (refactoring
`get_config()` calls across ~50 files, building a separate CI pipeline, splitting tests).

### Monorepo with workspace packages
Using a monorepo tool (e.g., `hatch` workspaces) to publish `sbir-etl` and
`sbir-analytics` from the same repo. This reduces some maintenance cost but still
requires solving the config coupling and adds build complexity. Worth revisiting if
a second app materializes.

### Git submodule / subtree
Sharing ETL code via git subtree. Rejected — creates merge pain and doesn't solve
the config coupling or dependency isolation problems.

## Links

- Related files: `src/extractors/`, `src/enrichers/`, `src/transformers/`, `src/loaders/`
- Related config: `pyproject.toml`, `config/base.yaml`
