# Configuration Files

Runtime configuration is assembled and validated by `sbir_etl/config/loader.py` and the Pydantic
models in `sbir_etl/config/schemas/`.

## Profiles

| File | Role |
| --- | --- |
| `base.yaml` | Shared defaults; always loaded |
| `dev.yaml` | Local development overrides |
| `test.yaml` | Automated-test overrides |
| `prod.yaml` | Live-server overrides that are safe to commit |

Select a profile with `SBIR_ETL__PIPELINE__ENVIRONMENT`:

```bash
export SBIR_ETL__PIPELINE__ENVIRONMENT=development
```

`development`/`dev`, `production`/`prod`, and `test` map to the corresponding YAML files. An
explicit `get_config(environment="...")` argument takes precedence.

## Runtime overrides

Use double underscores to mirror nested keys:

```bash
export SBIR_ETL__PATHS__DATA_ROOT=/path/to/data
export SBIR_ETL__LOGGING__LEVEL=DEBUG
export SBIR_ETL__ENRICHMENT__PERFORMANCE__CHUNK_SIZE=10000
```

Neo4j connection values can be supplied directly with `NEO4J_URI`, `NEO4J_USER`,
`NEO4J_PASSWORD`, and `NEO4J_DATABASE`. Do not commit credentials to YAML.

## Domain configuration

Subdirectories such as `cet/`, `fiscal/`, `ml/`, and `transition/` contain configuration owned by
specific pipeline components. They are not automatically merged into the root configuration;
follow the loader in the owning component when changing them.

## Usage

```python
from sbir_etl.config.loader import get_config

config = get_config()
print(config.pipeline.environment)
print(config.paths.resolve_path("raw_data"))
```

See the [configuration reference](../docs/configuration.md) for precedence, supported sections,
path behavior, Docker usage, and the procedure for adding settings.
