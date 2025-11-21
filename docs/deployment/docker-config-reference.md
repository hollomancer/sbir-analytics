# Docker Configuration Reference

This document provides reference information for Docker and containerized deployment configurations. This is **not a runtime environment** - it's a reference guide for Docker service defaults.

> **Note**: `config/docker.yaml` is a reference file only. It is NOT loaded as a runtime environment by the configuration loader. Use `development`, `test`, or `production` environments instead.

## Docker Compose Profiles

The consolidated `docker-compose.yml` uses profile-based configuration:

- **Development**: `docker compose --profile dev up --build` (bind-mounts, hot-reload)
- **CI Testing**: `docker compose --profile ci up --build` (ephemeral services, test execution)

## Service Defaults

### Neo4j Service

```yaml
neo4j:
  host: "neo4j"
  http_port: 7474
  bolt_port: 7687
  user: "neo4j"
  # Password: Set via NEO4J_PASSWORD environment variable or .env file

  memory:
    pagecache_size: "256M"
    heap_max_size: "512M"

  volumes:
    data: "neo4j_data"
    logs: "neo4j_logs"
    import: "neo4j_import"

  healthcheck:
    interval: "10s"
    timeout: "5s"
    retries: 12
    start_period: "10s"
```

### Dagster Service

```yaml
dagster:
  host: "0.0.0.0"
  port: 3000
  health_path: "/server_info"

  cmd_dev: "dagster dev -h 0.0.0.0 -p 3000"
  cmd_prod: "dagster api -h 0.0.0.0 -p 3000"
  enable_watchfiles: true  # dev-only

  volumes:
    reports: "reports"
    logs: "logs"
    data: "data"
    config: "config"
    metrics: "metrics"

  healthcheck:
    interval: "10s"
    timeout: "3s"
    retries: 5
    start_period: "5s"
```

## Service Dependencies

```yaml
services:
  dagster_web:
    depends_on:
      - neo4j
    condition: "service_healthy"

  dagster_daemon:
    depends_on:
      - neo4j
      - dagster_web
    condition: "service_healthy"

  etl_runner:
    depends_on:
      - neo4j
    condition: "service_healthy"
```

## Environment Variables

### Common Environment Variables

```bash
ENVIRONMENT=dev  # or: test, prod
PYTHONPATH=/app
PYTHONUNBUFFERED=1
SERVICE_STARTUP_TIMEOUT=120

# Neo4j connection
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password_here
```

### Security Best Practices

1. **Never commit secrets** to YAML files or the repository
2. **Use environment variables** for sensitive data (passwords, API keys)
3. **Use `.env` file** for local development (gitignored)
4. **Use secret mounts** in production (e.g., `/run/secrets/NEO4J_PASSWORD`)

## Volume Configuration

Default named volumes:

- `neo4j_data` - Neo4j database data
- `neo4j_logs` - Neo4j logs
- `neo4j_import` - Neo4j import directory
- `reports` - Application reports
- `logs` - Application logs
- `data` - Application data
- `config` - Configuration files
- `metrics` - Metrics data

## Makefile Helpers

Use the Makefile helpers rather than raw compose commands:

```bash
make docker-build      # Build the image locally
make docker-up-dev     # Start the dev stack (bind mounts, watch/reload)
make docker-test       # Run containerized tests using the CI test overlay
make docker-down       # Tear down running compose stacks
```

## CI Configuration

For CI/CD pipelines:

- Build image using Buildx/cache
- Run tests using `docker compose --profile ci`
- Push artifacts to registry only when tests pass
- See `scripts/ci/build_container.sh` and `.github/workflows/container-ci.yml` for examples

## Entrypoint Scripts

Entrypoint scripts (`scripts/docker/entrypoint.sh`) will:

- Load `.env` and `/run/secrets/*` files
- Wait for dependencies (Neo4j, Dagster web) before starting services
- Provide robust fallback even when `depends_on.condition` is not supported

## Additional Resources

- [Containerization Guide](containerization.md) - Full containerization documentation
- [Configuration Management](../../../config/README.md) - Configuration system overview
- [Docker Compose File](../../docker-compose.yml) - Main compose configuration
