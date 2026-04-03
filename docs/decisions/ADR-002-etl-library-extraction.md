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

### 1. Package Renamed: `src/` → `sbir_etl/` and multi-package layout

The generic `src/` package has been restructured into `sbir_etl/` plus multiple packages under `packages/` to avoid namespace
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

`packages/sbir-models/` provides a **truly standalone** `sbir_models` package with its
own copies of the model source files. Dependencies: only `pydantic>=2.8`. Other projects
can use SBIR data models without pulling in the full ETL pipeline:

```python
from sbir_models import Award, Patent, Organization, FederalContract
```

The package vendors its own `parse_date` utility (`_date_utils.py`) and a logging shim
(`_logging.py`) that falls back to stdlib `logging` when `loguru` is not installed.
No `sbir_etl` installation required.

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

**Recommendation**: Use `sbir-models` for model sharing (now fully standalone).
For ETL function reuse, the dependency analysis below identifies which deps can be
made optional to reduce install footprint.

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

**Ship `sbir-etl` as the reusable Python library. Ship `sbir-analytics` as the full
pipeline metapackage.** Multiple consumer applications can `pip install sbir-etl` and
use the ETL functions (extractors, enrichers, transformers) without pulling in Dagster,
Neo4j, CLI tools, or ML dependencies. Each consumer chooses its own storage backend
(Neo4j, Postgres, S3, etc.) by loading the ETL output (Pydantic models / DataFrames)
into its own persistence layer.

### Package Hierarchy

```
sbir-models       Only Pydantic models (~5 MB, pydantic only)
    ↑
sbir-etl          ETL library (~135 MB, core deps)
    ↑
sbir-analytics    Full pipeline (~380 MB, metapackage = sbir-etl[all])
```

### Install Profiles

```bash
# ETL library (extractors, enrichers, transformers, models, config)
pip install sbir-etl

# Full pipeline (Dagster + CLI + S3 + ML + Neo4j)
pip install sbir-analytics
# equivalent to: pip install sbir-etl[pipeline,cli,cloud,ml,neo4j]

# À la carte extras on the ETL library
pip install sbir-etl[pipeline]     # + Dagster orchestration
pip install sbir-etl[cli]          # + sbir-cli command
pip install sbir-etl[cloud]        # + S3 support (boto3, cloudpathlib)
pip install sbir-etl[ml]           # + scikit-learn, spacy, huggingface
pip install sbir-etl[neo4j]        # + Neo4j graph loader

# Just the models (no ETL deps at all)
pip install sbir-models
```

### Library Usage Pattern (Storage-Agnostic)

```python
from sbir_etl.extractors.sbir import SbirDuckDBExtractor
from sbir_etl.enrichers.patentsview import PatentsViewClient
from sbir_etl.config.schemas import PipelineConfig

# Extract
extractor = SbirDuckDBExtractor(config=my_config)
awards_df = extractor.extract()

# Enrich
client = PatentsViewClient(config=my_config)
enriched_df = client.enrich(awards_df)

# Output is a DataFrame / Pydantic models — consumer decides where it goes
save_to_postgres(enriched_df)  # App A
upload_to_s3(enriched_df)      # App B
load_to_neo4j(enriched_df)     # App C (uses sbir-analytics[neo4j])
```

### What the Refactoring Achieved

1. **`sbir-etl`** — the reusable library, pip package name matches the Python import (`sbir_etl`)
2. **`sbir-analytics`** — metapackage for the full pipeline (`sbir-etl[all]`)
3. **`sbir-models`** — truly standalone model package (only needs pydantic)
4. **Optional neo4j** — consumers choose their storage backend
5. **Config injection** — no filesystem coupling for library-style use
6. **Tiered dependencies** — core deps support ETL; dagster/cli/ml/cloud are extras

## Runtime Dependency Analysis

Audit of which `sbir_etl/` modules actually import each dependency:

| Dependency | Install Size | Used By | Extra |
|-----------|-------------|---------|-------|
| **pydantic** | ~5 MB | models, config (pervasive) | core |
| **pandas** | ~45 MB | 13 modules (pervasive) | core |
| **loguru** | ~1 MB | 14 modules (pervasive) | core |
| **pyyaml** | ~1 MB | `config/`, `cli/`, `enrichers/` | core |
| **numpy** | ~15 MB | `enrichers/`, `transformers/`, `utils/` | core |
| **duckdb** | ~30 MB | `extractors/`, `utils/`, `config/` | core |
| **pyarrow, pyreadstat** | ~25 MB | `extractors/`, `utils/`, `quality/` | core |
| **httpx, tenacity** | ~5 MB | `enrichers/`, `extractors/` | core |
| **rapidfuzz, jellyfish** | ~5 MB | `enrichers/` only | core |
| **psutil** | ~2 MB | `transition/`, `utils/` | core |
| **dagster, dagster-webserver** | ~60 MB | `assets/`, `definitions/` | `[pipeline]` |
| **typer, rich** | ~10 MB | `cli/` only | `[cli]` |
| **boto3, cloudpathlib** | ~40 MB | `utils/`, `assets/`, `lambda/` | `[cloud]` |
| **scikit-learn, joblib** | ~35 MB | `ml/`, `transition/`, `tools/` | `[ml]` |
| **spacy** | ~100 MB | `ml/` only | `[ml]` |
| **huggingface-hub** | ~5 MB | `ml/` only | `[ml]` |

### Key Finding: Clean Separation Already Exists

The core ETL modules (`extractors/`, `enrichers/`, `transformers/`, `models/`) have
**zero Dagster imports**. Dagster is completely isolated to orchestration (`assets/`,
`definitions/`) and CLI. The core install (~135 MB) covers the full ETL pipeline;
the extras add ~245 MB for orchestration, ML, cloud, and CLI.

## Consequences

**Positive:**
- Multiple apps can `pip install sbir-etl` without the full analytics stack
- `pip install sbir-analytics` still works for the full pipeline (backwards compat)
- ETL output is storage-agnostic — consumers choose neo4j, postgres, S3, etc.
- Core install is ~135 MB vs ~380 MB for the full pipeline
- Config injection enables library-style use without filesystem coupling

**Negative:**
- Cloud storage functions require `[cloud]` extra — callers get a clear ImportError
- Two pip package names to maintain (`sbir-etl` and `sbir-analytics`)

**Neutral:**
- Monorepo approach avoids separate release cycles — both packages live in one repo

## Superseded: `sbir-models` standalone package (removed)

The original design extracted Pydantic models into a standalone `packages/sbir-models/`
package. This was removed because:

- `sbir-models` was never wired as a dependency — `sbir_etl` continued importing from
  its own `sbir_etl/models/`, not from `sbir_models`
- The 13 duplicated model files diverged within days as edits hit one copy but not the other
- No second consumer of `sbir-models` materialized

All data models now live in `sbir_etl/models/`. If a standalone models package is needed
in the future, it should be extracted with proper dependency wiring from the start.

## Links

- Related files: `sbir_etl/extractors/`, `sbir_etl/enrichers/`, `sbir_etl/transformers/`, `sbir_etl/loaders/`
- Related config: `pyproject.toml`, `config/base.yaml`
