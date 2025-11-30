# Configuration Paths

Reference for configuration file locations and data paths.

## Configuration Files

| Path | Purpose |
|------|---------|
| `config/base.yaml` | Default settings (version controlled) |
| `config/dev.yaml` | Development overrides |
| `config/prod.yaml` | Production settings |
| `config/cet/taxonomy.yaml` | CET classification taxonomy |

## Data Directories

| Path | Purpose |
|------|---------|
| `data/raw/` | Source data files (not in git) |
| `data/processed/` | Intermediate processing results |
| `data/transformed/` | Business logic outputs |
| `data/validated/` | Quality-checked data |
| `data/enriched/` | Externally enriched data |

## S3 Paths (Production)

| S3 Key Prefix | Purpose |
|---------------|---------|
| `raw/awards/` | SBIR award CSV files |
| `raw/patents/` | USPTO patent data |
| `raw/usaspending/` | USAspending database dumps |
| `processed/` | Pipeline outputs |
| `artifacts/` | Reports and summaries |

## Environment Variable Overrides

Override any config using `SBIR_ETL__SECTION__KEY` pattern:

```bash
export SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
export SBIR_ETL__PIPELINE__CHUNK_SIZE=20000
```

## Related

- [Configuration Guide](../configuration.md) - Full configuration reference
- [Steering: Configuration Patterns](../../.kiro/steering/configuration-patterns.md)
