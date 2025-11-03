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

## Containerized Environments

The project supports running inside Docker Compose for local development, CI, and production-like testing. When operating in containerized environments, follow these guidelines:

- Override precedence: environment variables (highest) > `.env` (local overrides) > YAML config files (`config/*.yaml`).
- Do not store secrets in YAML or in the repository. Use environment variables, `.env` (local and gitignored), or mounted secret files (e.g., `/run/secrets/NEO4J_PASSWORD`) for secret values.
- The consolidated `docker-compose.yml` uses profile-based configuration:
  - Base compose: `docker-compose.yml`
  - Development: `docker compose --profile dev up --build` (bind-mounts, hot-reload)
  - CI Testing: `docker compose --profile ci-test up --build` (ephemeral services)
  - Production: `docker compose --profile prod up --build`
  - Other profiles: `e2e`, `cet-staging`, `neo4j-standalone`, `tools`
- Use the Makefile helpers rather than raw compose commands:
  - `make docker-build` — build the image locally
  - `make docker-up-dev` — start the dev stack (bind mounts, watch/reload)
  - `make docker-test` — run containerized tests using the CI test overlay
  - `make docker-down` — tear down running compose stacks
- Use `config/docker.yaml` for non-sensitive defaults and CI hints; do not include credentials in this file.
- Entrypoint scripts (`sbir-etl/scripts/docker/entrypoint.sh`) will attempt to load `.env` and `/run/secrets/*` and will wait for dependencies (Neo4j, Dagster web) before starting services — the entrypoint provides a robust fallback even when `depends_on.condition` is not supported by the environment.

Recommended workflow (local)
1. Copy `.env.example` -> `.env` and set local test credentials (do not commit `.env`)
2. Build the image: `make docker-build`
3. Start dev stack: `make docker-up-dev` (or run compose with dev overlay)
4. Run ad-hoc commands inside the image via `docker compose run --rm etl-runner -- <cmd>` or use `make docker-exec`

CI guidance
- CI should build the image (using Buildx/cache), run `docker/docker-compose.test.yml` to execute tests inside the built image, and only push artifacts to a registry when tests pass. See `scripts/ci/build_container.sh` and `.github/workflows/container-ci.yml` for examples.

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
