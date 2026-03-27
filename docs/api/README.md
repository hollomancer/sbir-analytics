# API Reference

Code documentation for the SBIR ETL pipeline.

## Module Structure

```text
sbir_etl/
├── config/          # Configuration schemas and loader
├── extractors/      # Data extraction modules
├── enrichers/       # Data enrichment modules
├── transformers/    # Data transformation modules
├── models/          # Pydantic data models
├── utils/           # Shared utilities
└── quality/         # Data quality checks

packages/sbir-analytics/sbir_analytics/
├── assets/          # Dagster asset definitions
├── cli/             # Command-line interface
└── tools/           # Utility tools

packages/sbir-graph/sbir_graph/
└── loaders/         # Neo4j loading modules

packages/sbir-ml/sbir_ml/
├── ml/              # Machine learning modules
└── transition/      # Transition detection
```

## Key Modules

### Configuration

- `sbir_etl.config.loader` - Configuration loading and validation
- `sbir_etl.config.schemas` - Pydantic configuration schemas

### Assets

- `sbir_analytics.assets.sbir` - SBIR award processing assets
- `sbir_analytics.assets.cet` - CET classification assets
- `sbir_analytics.assets.uspto` - USPTO patent assets

### Data Processing

- `sbir_etl.extractors` - Data extraction from sources
- `sbir_etl.enrichers` - External data enrichment
- `sbir_etl.transformers` - Business logic transformations
- `sbir_graph.loaders` - Neo4j graph loading

## Generating Docs

```bash
# Generate API documentation
uv run pdoc sbir_etl/ -o docs/api/generated/
```

## Related

- [Architecture Overview](../architecture/detailed-overview.md)
- [Configuration Guide](../configuration.md)
