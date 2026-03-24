---

Type: Decision
Owner: conrad.hollomon@pm.me
Last-Reviewed: 2026-03-24
Status: accepted

---

# ADR: ETL Library Extraction Evaluation

## Context

We're evaluating whether to extract the ETL pipeline from `sbir-analytics` into a
standalone library that other applications can consume. The motivation is reuse: other
government analytics projects and data science pipelines could benefit from our SBIR
extraction, enrichment, and transformation capabilities without depending on Dagster,
Neo4j, or our CLI.

### Current Architecture

The ETL pipeline is organized into four clean stages within `sbir_etl/`:

| Stage | Location | Lines | Purpose |
|-------|----------|-------|---------|
| Extract | `sbir_etl/extractors/` | ~4.6K | SBIR CSV (DuckDB), USAspending DB, USPTO patents, SAM.gov, SBIR.gov API |
| Enrich | `sbir_etl/enrichers/` | ~9.3K | Fuzzy matching, company categorization, geographic resolution, patent similarity |
| Transform | `sbir_etl/transformers/` | ~3.8K | Normalization, categorization, fiscal pipeline, NAICS-BEA mapping |
| Load | `sbir_etl/loaders/neo4j/` | ~2.8K | Neo4j graph loading with idempotent MERGE |

Supporting modules that ETL depends on:
- `sbir_etl/models/` — Pydantic data models (~20 files)
- `sbir_etl/config/` — YAML-based hierarchical config with env var overrides
- `sbir_etl/utils/` — Cloud storage, DuckDB client, caching, date parsing, async tools
- `sbir_etl/exceptions.py` — Shared exception hierarchy

Orchestration lives in `sbir_etl/assets/` (Dagster asset definitions) and
`sbir_etl/assets/jobs/` (Dagster job definitions). The CLI lives in `sbir_etl/cli/`.

## Refactoring Completed

All four preparatory steps from the initial evaluation have been implemented:

### 1. Package Renamed: `src/` → `sbir_etl/`

The generic `src/` package name has been renamed to `sbir_etl/` to avoid namespace
conflicts when installed alongside other Python projects. All imports, pyproject.toml
references, Dockerfiles, CI workflows, and tooling configs updated.

### 2. Neo4j Made Optional

`neo4j` moved from core `dependencies` to `[project.optional-dependencies.neo4j]`.
Install with `pip install sbir-analytics[neo4j]`. The `sbir_etl.loaders.neo4j` package
uses lazy imports — importing `sbir_etl` or `sbir_etl.models` no longer requires neo4j
to be installed. Asset and CLI files that use neo4j guard their imports with try/except.

### 3. Config Dependency Injection

Key ETL modules now accept `config=None` parameter with `get_config()` as fallback:

- **Extractors**: `SAMGovExtractor(config=...)`, `extract_usaspending_from_config(config=...)`
- **Enrichers**: `ChunkedEnricher(config=...)`, `PatentsViewClient(config=...)`,
  `retrieve_company_contracts_api(config=...)`
- **Transformers**: Already used the `config or get_config()` pattern
- **Utilities**: `get_duckdb_client(config=...)`, `configure_logging_from_config(config=...)`,
  `EnrichmentMetricsCollector(config=...)`

External consumers can now use ETL components without `config/base.yaml`:

```python
from sbir_etl.extractors.sam_gov import SAMGovExtractor
from sbir_etl.config.schemas import PipelineConfig

my_config = PipelineConfig(extraction={"sam_gov": {"parquet_path": "..."}})
extractor = SAMGovExtractor(config=my_config)
```

### 4. Standalone Models Package

`packages/sbir-models/` provides a lightweight `sbir_models` package that re-exports
Pydantic models from `sbir_etl.models`. Dependencies: only `pydantic>=2.8`. Other
projects can use SBIR data models without pulling in the full ETL pipeline:

```python
from sbir_models import Award, Patent, Organization, FederalContract
```

Currently implemented as a re-export layer (requires `sbir_etl` to also be installed).
For true standalone use, model files would need to be copied into the package and the
`parse_date` utility vendored.

## Re-Evaluation for Use Cases

With the refactoring complete, let's re-evaluate for the target use cases:

### Other Government Analytics Projects

**Verdict: Feasible now, but monorepo approach recommended over separate library.**

What works today:
- `pip install sbir-analytics` gives a properly namespaced `sbir_etl` package
- Extractors accept injected config — no need for our `config/base.yaml`
- Neo4j is optional — projects not using graph databases avoid the dependency
- Models are lightweight and well-defined via Pydantic

What still couples:
- 24 runtime deps come along (dagster, duckdb, spacy, scikit-learn, etc.)
- Extractors are SBIR-domain-specific (CSV column mappings, field names)
- No `extras` groups for "extract-only" or "transform-only" install profiles

**Recommendation**: For sharing with other government analytics projects, create
additional optional dependency groups (e.g., `[extract]`, `[enrich]`, `[transform]`)
to let consumers install only what they need. Consider publishing `sbir-models` to an
internal PyPI if model sharing is the primary need.

### Data Science Pipelines

**Verdict: Ready for use.**

Data science pipelines can now:
1. Install `sbir-analytics` (gets models + transformers + extractors)
2. Import models: `from sbir_etl.models import Award, Patent`
3. Use extractors with custom config: `SAMGovExtractor(config=my_config)`
4. Skip Neo4j entirely (optional dep)
5. Use transformers for fiscal analysis, categorization, etc.

The config DI pattern means notebook/pipeline code doesn't need filesystem config.

## Updated Decision

**Accept the monorepo approach with the completed refactoring.** The four preparatory
steps have been implemented, making the codebase ready for reuse without the overhead
of maintaining a separate library:

1. **`sbir_etl/`** — properly namespaced, pip-installable
2. **Optional neo4j** — consumers choose what they need
3. **Config injection** — no filesystem coupling for library-style use
4. **`sbir-models`** — lightweight model package available

### When to Revisit Full Extraction

Extract to a separate library if:
- A concrete external consumer appears that cannot install `sbir-analytics` at all
- The dependency footprint (200MB+) is prohibitive for the consumer
- Multiple teams need independent release cycles for ETL vs. pipeline

### Remaining Work (If Extraction Needed Later)

1. Create `[extract]`, `[enrich]`, `[transform]` optional dependency groups
2. Vendor `parse_date` into `sbir-models` for truly standalone model usage
3. Make dagster an optional dependency (move to `[pipeline]` extra)
4. Split tests to validate each extra independently

## Consequences

**Positive:**
- ETL is now usable as a library without separate packaging
- Config injection enables external consumers and improves testability
- Neo4j optional reduces install footprint for non-graph use cases
- No additional maintenance burden from separate packages

**Negative:**
- Full dependency set still installed even if only models are needed
- `sbir-models` re-export approach requires `sbir_etl` to be co-installed

**Neutral:**
- Monorepo structure scales well until multiple independent consumers appear

## Links

- Related files: `sbir_etl/extractors/`, `sbir_etl/enrichers/`, `sbir_etl/transformers/`, `sbir_etl/loaders/`
- Related config: `pyproject.toml`, `config/base.yaml`
- Models package: `packages/sbir-models/`
