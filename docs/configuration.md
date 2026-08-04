# Configuration Reference

**Type**: Reference

**Owner**: Engineering Team

**Last-Reviewed**: 2026-08-03

**Status**: Active

The pipeline loads YAML from `config/`, applies environment-variable overrides, and validates
the result with Pydantic models in `sbir_etl/config/schemas/`. The schemas and YAML files are the
source of truth for fields, defaults, and validation constraints.

## Load order

`sbir_etl.config.loader.get_config()` builds the effective configuration in this order:

1. Load `config/base.yaml`.
2. Deep-merge the selected profile, when present: `dev.yaml`, `test.yaml`, or `prod.yaml`.
3. Map the legacy `loading.neo4j` block to the runtime `neo4j` section.
4. Add runtime defaults for Neo4j, logging, and monitoring.
5. Apply `SBIR_ETL__...` environment overrides.
6. Validate and return a `PipelineConfig`.

Later layers take precedence.

## Selecting a profile

Profile selection uses this precedence:

1. `get_config(environment="...")`
2. `SBIR_ETL__PIPELINE__ENVIRONMENT`
3. Legacy `SBIR_ETL_ENV`
4. `development`

The aliases `development`/`dev` and `production`/`prod` select `dev.yaml` and `prod.yaml`,
respectively. `test` selects `test.yaml`. A custom name selects `config/<name>.yaml` if that file
exists; otherwise only `base.yaml` is loaded.

```bash
export SBIR_ETL__PIPELINE__ENVIRONMENT=test
uv run python -c 'from sbir_etl.config import get_config; print(get_config().pipeline.environment)'
```

## Environment overrides

Use double underscores to mirror a YAML path:

```bash
export SBIR_ETL__PATHS__DATA_ROOT=/path/to/persistent-storage/sbir-analytics
export SBIR_ETL__LOGGING__LEVEL=DEBUG
export SBIR_ETL__ENRICHMENT__PERFORMANCE__CHUNK_SIZE=10000
```

Override names are case-insensitive after the `SBIR_ETL__` prefix. Values are converted to
booleans, integers, or floats when possible; all other values remain strings. Complex list or map
overrides should be expressed in a profile YAML file instead.

`SBIR_ETL__PIPELINE__ENVIRONMENT` selects the profile and is not reapplied as a generic override.

### Neo4j secrets and connection settings

The loader also supports these direct variables:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD='local-password'
export NEO4J_DATABASE=neo4j
```

Keep secrets out of committed YAML. The live server uses `.env.server`; preserve that file and
follow the [self-hosted server runbook](deployment/self-hosted-server.md) before any live operation.

## Using configuration in Python

```python
from sbir_etl.config.loader import get_config

config = get_config()
print(config.pipeline.environment)
print(config.enrichment.performance.chunk_size)
print(config.neo4j.uri)
```

`get_config()` is cached. Tests or long-running processes that change environment variables must
clear the cache before reloading:

```python
from sbir_etl.config.loader import get_config

get_config.cache_clear()
config = get_config()
```

## Paths

Paths are configured under `paths` and resolve relative to the current project root by default:

```python
from sbir_etl.config.loader import get_config

config = get_config()
raw_data = config.paths.resolve_path("raw_data")
output = config.paths.resolve_path("scripts_output", create_parent=True)
```

`resolve_path()` expands shell environment variables and `~`, accepts absolute paths, and can
create the resolved path's parent directory. Pipeline storage is local filesystem storage; the
live deployment mounts the host paths configured by `SERVER_*_DIR` into the containers.

## Main sections

The root `PipelineConfig` currently exposes:

| Section | Purpose |
| --- | --- |
| `pipeline` | Name, version, and selected environment |
| `paths` | Raw data, USAspending dumps, transition artifacts, and script outputs |
| `data_quality` | Completeness, validity, uniqueness, and enrichment quality gates |
| `enrichment` | API clients, matching, retries, caching, and performance controls |
| `enrichment_refresh` | Incremental refresh cadence, state, and freshness metrics |
| `extraction` | SBIR and USAspending extraction settings |
| `validation` / `transformation` | Record validation and transformation behavior |
| `neo4j` | Graph connection, database, batching, and concurrency |
| `logging` / `metrics` | Structured logs and runtime metrics |
| `duckdb` | Local analytical database settings |
| `company_categorization` | Contract-based company categorization |
| `statistical_reporting` | Statistical report generation |
| `fiscal_analysis` | Fiscal returns and BEA mappings |
| `ml` | ModernBERT, embeddings, and related model settings |
| `ot_consortium` | OT consortium verification and tiering |
| `cli` | Command-line defaults |

Some specialized configuration lives in domain directories such as `config/cet/`,
`config/fiscal/`, `config/transition/`, and `config/ml/`. Those files are loaded by their owning
components rather than automatically merged into `PipelineConfig`.

## Docker Compose

`.env`, `.env.server`, and Compose `environment:` blocks configure containers. They do not form an
additional loader layer by themselves: a value must be passed into the container process before
`get_config()` can see it.

Use the Make targets for local containers:

```bash
make docker-up-dev
make docker-test
make docker-down
```

See [Docker development](development/docker.md) for local workflows and the
[self-hosted server runbook](deployment/self-hosted-server.md) for the live instance.

## Adding a setting

1. Add the field to the appropriate Pydantic model in `sbir_etl/config/schemas/`.
2. Add its default to `config/base.yaml` when a shared default is appropriate.
3. Add only real environment differences to `dev.yaml`, `test.yaml`, or `prod.yaml`.
4. Add or update configuration tests.
5. Update this reference when the setting changes an operator-facing workflow.

Run focused configuration tests before committing:

```bash
uv run pytest tests/unit/config/ -v
```

For a compact directory-level overview, see [`config/README.md`](../config/README.md).
