# Configuration Management

This directory contains the configuration files for the SBIR ETL pipeline. The system uses a three-layer configuration approach for flexibility and type safety.

## Configuration Layers

### 1. Base Configuration (`base.yaml`)
Contains default settings that are version controlled and shared across all environments. These provide sensible defaults for production use.

### 2. Environment Overrides (`dev.yaml`, `prod.yaml`)
Environment-specific settings that override base configuration. These files contain settings that differ between development, staging, and production environments.

### 3. Environment Variables
Runtime overrides using environment variables with the pattern `SBIR_ETL__SECTION__KEY=value`. These take highest precedence and are useful for secrets and deployment-specific settings.

## Configuration Structure

```yaml
pipeline:
  name: "sbir-etl"
  version: "0.1.0"
  environment: "development"

data_quality:
  completeness:
    award_id: 1.00          # 100% required
    company_name: 0.95      # 95% required
  uniqueness:
    award_id: 1.00          # No duplicates
  validity:
    award_amount_min: 0.0
    award_amount_max: 5000000.0

extraction:
  sbir:
    chunk_size: 10000
    date_format: "%m/%d/%Y"
  usaspending:
    database_name: "usaspending"
    import_chunk_size: 50000

# ... additional sections
```

## Environment Variable Overrides

Environment variables override YAML configuration using double underscores to separate nested keys:

```bash
# Override Neo4j URI
export SBIR_ETL__NEO4J__URI_ENV_VAR="neo4j://localhost:7687"

# Override data quality threshold
export SBIR_ETL__DATA_QUALITY__COMPLETENESS__COMPANY_NAME=0.90

# Override logging level
export SBIR_ETL__LOGGING__LEVEL="DEBUG"
```

## Type Safety

Configuration is validated using Pydantic models in `src/config/schemas.py`. This ensures:

- Type safety at runtime
- Automatic validation of configuration values
- Clear error messages for invalid configuration
- IDE support and autocompletion

## Usage in Code

```python
from src.config.loader import get_config

# Get validated configuration
config = get_config()

# Access configuration values
neo4j_uri = os.getenv(config.neo4j.uri_env_var)
batch_size = config.neo4j.batch_size
quality_threshold = config.data_quality.completeness["company_name"]
```

## Environment Selection

The environment is determined by:

1. Explicit parameter to `get_config(environment="prod")`
2. `SBIR_ETL__PIPELINE__ENVIRONMENT` environment variable
3. Defaults to `"development"`

## Validation

Configuration is automatically validated when loaded. Invalid configuration will raise a `ConfigurationError` with details about what's wrong.

## Best Practices

1. **Keep secrets out of YAML files** - Use environment variables for sensitive data
2. **Version control base.yaml** - Environment-specific files can be gitignored if they contain secrets
3. **Use descriptive keys** - Configuration keys should be self-documenting
4. **Validate early** - Configuration is validated at startup to catch issues immediately
5. **Document overrides** - Keep track of environment variable overrides in deployment documentation

## Adding New Configuration

1. Add the new fields to the appropriate Pydantic model in `src/config/schemas.py`
2. Add default values to `base.yaml`
3. Add environment-specific overrides to `dev.yaml`/`prod.yaml` as needed
4. Update this documentation