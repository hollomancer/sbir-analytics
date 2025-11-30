# API Reference

Code documentation for the SBIR ETL pipeline.

## Module Structure

```
src/
├── assets/          # Dagster asset definitions
├── config/          # Configuration schemas and loader
├── extractors/      # Data extraction modules
├── enrichers/       # Data enrichment modules
├── transformers/    # Data transformation modules
├── loaders/         # Neo4j loading modules
├── models/          # Pydantic data models
├── utils/           # Shared utilities
├── ml/              # Machine learning modules
└── cli/             # Command-line interface
```

## Key Modules

### Configuration
- `src.config.loader` - Configuration loading and validation
- `src.config.schemas` - Pydantic configuration schemas

### Assets
- `src.assets.sbir` - SBIR award processing assets
- `src.assets.cet` - CET classification assets
- `src.assets.uspto` - USPTO patent assets

### Data Processing
- `src.extractors` - Data extraction from sources
- `src.enrichers` - External data enrichment
- `src.transformers` - Business logic transformations
- `src.loaders` - Neo4j graph loading

## Generating Docs

```bash
# Generate API documentation
uv run pdoc src/ -o docs/api/generated/
```

## Related

- [Architecture Overview](../architecture/detailed-overview.md)
- [Configuration Guide](../configuration.md)
