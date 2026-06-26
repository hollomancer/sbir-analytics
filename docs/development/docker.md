# Docker Development Guide

**Audience**: Developers, DevOps
**Prerequisites**: Docker 20.10+, Docker Compose V2
**Related**: [Dockerfile](../../Dockerfile), [docker-compose.yml](../../docker-compose.yml)
**Last Updated**: 2026-06-26

## Overview

Docker Compose is the **failover option** for local development. **GitHub Actions** is
the primary deployment method. Use Docker for:

- Local development without cloud dependencies
- CI/CD testing (mirrors the GitHub Actions environment)
- Emergency failover scenarios

This guide is the single canonical reference for Docker in this repo: quick start,
configuration, the image architecture, optimization, and troubleshooting.

## Quick Start

### 1. Prerequisites Check

```bash
make docker-check-prerequisites
```

Validates:

- Docker 20.10+ installed and running
- Docker Compose V2 available
- Ports 3000, 7474, 7687 available
- Sufficient disk space (5GB+)

### 2. Environment Setup

```bash
cp .env.example .env
```

**Minimal configuration** (local development):

```bash
NEO4J_USER=neo4j
NEO4J_PASSWORD=test  # pragma: allowlist secret
```

See [Environment Variables](#environment-variables) for the complete reference.

### 3. Build and Start

```bash
# Build the ETL image
make docker-build

# Start the development stack (profile: dev)
make docker-up-dev

# Verify setup
make docker-verify
```

**Services available:**

- Dagster UI: <http://localhost:3000>
- Neo4j Browser: <http://localhost:7474>
- Neo4j Bolt: bolt://localhost:7687

### 4. Development Workflow

```bash
# View logs (default service: dagster-webserver)
make docker-logs

# Run containerised CI tests (profile: ci)
make docker-test

# Rebuild image and restart the dev stack
make docker-rebuild

# Stop services and remove volumes
make docker-down
```

## Makefile Targets

Prefer the Makefile helpers over raw `docker compose` commands. The real Docker targets are:

| Target | Purpose |
|--------|---------|
| `make docker-check-prerequisites` | Check all prerequisites for Docker setup |
| `make docker-verify` | Verify the Docker setup is working correctly |
| `make docker-build` | Build the application Docker image (BuildKit) |
| `make docker-buildx` | Build the image with `docker buildx` (multi-platform) |
| `make docker-push` | Push the tagged image to `DOCKER_REGISTRY` |
| `make docker-up-dev` | Start the development stack (profile: dev) |
| `make docker-up-tools` | Start the tools container (profile: dev) |
| `make docker-down` | Stop all services and remove volumes |
| `make docker-rebuild` | Rebuild the image and restart the dev stack |
| `make docker-logs` | Tail logs for `SERVICE` (default `dagster-webserver`) |
| `make docker-exec` | Execute `CMD` (default `sh`) in `SERVICE` |
| `make docker-test` | Run containerised CI tests (profile: ci) |

## Compose Profiles

The project uses a single `docker-compose.yml` with **two profiles**:

| Profile | Use Case | Services | Command |
|---------|----------|----------|---------|
| `dev` | Local development | Neo4j, Dagster (bind mounts, hot reload), tools | `make docker-up-dev` |
| `ci` | CI/testing | Neo4j, app test runner (`pytest`), ephemeral volumes | `make docker-test` |

> There is no `prod` or `test` profile. Production runs on GitHub Actions, not Compose.

### Development Profile

**Features:**

- Bind mounts for live code editing and hot reload
- Debug logging
- Local data volumes

**Start:**

```bash
make docker-up-dev
# or
docker compose --profile dev up -d
```

### CI Profile

**Features:**

- Mirrors the GitHub Actions environment
- Runs `pytest -m fast` automatically, then exits
- Named (ephemeral) volumes for isolation

**Start:**

```bash
make docker-test
# or
docker compose --profile ci up --abort-on-container-exit
```

## Services

| Service | Profiles | Role |
|---------|----------|------|
| `neo4j` | dev, ci | Neo4j 5 graph database (APOC enabled) |
| `dagster-webserver` | dev, ci | Dagster UI on port 3000 |
| `dagster-daemon` | dev, ci | Dagster schedules/sensors daemon |
| `etl-runner` | dev, ci | One-off ETL command runner |
| `app` | ci | Containerised test runner (`pytest -m fast`) |
| `tools` | dev, ci | Idle utility container for ad-hoc commands |

## Common Tasks

### Materialize Assets

```bash
# Via Dagster UI: http://localhost:3000 → Assets → Materialize

# Via CLI
docker compose --profile dev exec dagster-webserver \
  dagster asset materialize -m sbir_analytics.definitions
```

### Run a Specific Job

```bash
docker compose --profile dev exec dagster-webserver \
  dagster job execute -m sbir_analytics.definitions -j sbir_weekly_refresh_job
```

### List Jobs

```bash
docker compose --profile dev exec dagster-webserver \
  dagster job list -m sbir_analytics.definitions
```

### Access Neo4j

```bash
# Via Browser
open http://localhost:7474

# Via Cypher Shell
docker compose --profile dev exec neo4j cypher-shell -u neo4j -p test
```

### View Logs

```bash
# Default service (dagster-webserver)
make docker-logs

# Specific service
make docker-logs SERVICE=neo4j

# Follow logs directly
docker compose --profile dev logs -f dagster-webserver
```

### Execute Commands in a Container

```bash
# Interactive shell
make docker-exec SERVICE=dagster-webserver CMD=bash

# Run a Python script
docker compose --profile dev exec dagster-webserver \
  python scripts/data/download_sbir_data.py

# Run pytest
docker compose --profile dev exec dagster-webserver pytest tests/unit/
```

## Environment Variables

### Required

| Variable | Description | Example |
|----------|-------------|---------|
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | `test` |

### Optional

| Variable | Description | Default |
|----------|-------------|---------|
| `NEO4J_URI` | Neo4j connection URI | `bolt://neo4j:7687` |
| `DAGSTER_HOME` | Dagster home directory | `/opt/dagster/dagster_home` |
| `AWS_PROFILE` | AWS profile for S3 access | `default` |
| `AWS_REGION` | AWS region | `us-east-2` |
| `ENVIRONMENT` | Environment name | `dev` |
| `PYTHONUNBUFFERED` | Disable Python output buffering | `1` |
| `SERVICE_STARTUP_TIMEOUT` | Wait time for dependencies (seconds) | `120` |

### Configuration Overrides

Use the `SBIR_ETL__` prefix to override any config value:

```bash
# Override Neo4j settings
export SBIR_ETL__NEO4J__BOLT_URL="bolt://localhost:7687"
export SBIR_ETL__NEO4J__BATCH_SIZE=2000

# Override pipeline settings
export SBIR_ETL__PIPELINE__CHUNK_SIZE=20000
export SBIR_ETL__ENRICHMENT__BATCH_SIZE=200

# Override quality thresholds
export SBIR_ETL__DATA_QUALITY__MIN_ENRICHMENT_SUCCESS=0.85
```

See [Configuration Patterns](../configuration.md) for the complete reference.

### Security Best Practices

1. **Never commit secrets** to YAML files or the repository.
2. **Use environment variables** for sensitive data (passwords, API keys).
3. **Use a `.env` file** for local development (it is gitignored).
4. **Use secret mounts** in production (e.g. `/run/secrets/NEO4J_PASSWORD`).

## Image Architecture

The image is built as a layered set of three Dockerfiles. All images are published under
the `hollomancer` GHCR org.

| Dockerfile | Image | Contents | Used by |
|------------|-------|----------|---------|
| `Dockerfile.python-base` | `ghcr.io/hollomancer/sbir-analytics-python-base` | Python 3.11 + core deps (dagster, pandas, duckdb, neo4j, pydantic) | Base for the two images below; rebuilt weekly and on dependency changes |
| `Dockerfile` | `sbir-analytics` (ETL) | ETL deps only, no R/ML | GitHub Actions ETL, local development |
| `Dockerfile.full` | `sbir-analytics-full` | ETL + ML for fiscal analysis | AWS Batch, local ML/fiscal development |

### Build Arguments

| Dockerfile | Argument | Default | Description |
|------------|----------|---------|-------------|
| `Dockerfile.python-base` | `PYTHON_VERSION` | `3.11.9` | Python version for the base image |
| `Dockerfile.python-base` | `UV_VERSION` | `0.5.11` | `uv` version installed in the base image |
| `Dockerfile` | `BASE_IMAGE` | `ghcr.io/hollomancer/sbir-analytics-python-base:latest` | Python base image to build the ETL image from |
| `Dockerfile.full` | `PYTHON_BASE` | `ghcr.io/hollomancer/sbir-analytics-python-base:latest` | Python base image to build the full image from |

**Examples:**

```bash
# Build the ETL image (default)
make docker-build
# or
docker build -t sbir-analytics:latest .

# Build the full (ETL + ML) image
docker build -f Dockerfile.full -t sbir-analytics-full:latest .

# Rebuild the python base locally
docker build -f Dockerfile.python-base \
  -t ghcr.io/hollomancer/sbir-analytics-python-base:latest .
```

The application runs with `PYTHONPATH=/app` and the default ETL command
`dagster job list -m sbir_analytics.definitions`.

### Entrypoint Scripts

Entrypoint scripts (`scripts/docker/entrypoint.sh`) will:

- Load `.env` and `/run/secrets/*` files
- Wait for dependencies (Neo4j, Dagster web) before starting services
- Provide a robust fallback even when `depends_on.condition` is not supported

## Build Optimization

### Use BuildKit

```bash
export DOCKER_BUILDKIT=1
make docker-build
```

### Layer Ordering and Cache Mounts

Dependencies are installed in the cached python-base image, and application code is copied
last so that code changes do not invalidate the dependency layers. The base image uses
cache mounts:

```dockerfile
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
```

### Multi-Platform Builds

```bash
make docker-buildx
# or
docker buildx build --platform linux/amd64,linux/arm64 -t sbir-analytics .
```

### CI / Registry Cache

CI builds pull and push layer caches from GHCR for cross-runner reuse:

```yaml
cache-from: |
  type=registry,ref=ghcr.io/hollomancer/sbir-analytics:latest
  type=gha,scope=ci
cache-to: type=gha,mode=max,scope=ci
```

See `scripts/ci/build_container.sh` and `.github/workflows/build-images.yml` for the real
build pipeline.

### Monitoring Image Size

```bash
# Layer sizes
docker history sbir-analytics:latest --human --no-trunc

# Interactive analysis
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  wagoodman/dive sbir-analytics:latest

# Compare builds
docker images sbir-analytics --format "table {{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
```

## Data Volumes

Compose uses named volumes (local driver):

| Volume | Purpose | Backup |
|--------|---------|--------|
| `neo4j_data` | Neo4j database | Required |
| `neo4j_logs` | Neo4j logs | Optional |
| `neo4j_import` | Neo4j import directory | Optional |
| `reports` | Application reports | Recommended |
| `logs` | Application logs | Optional |
| `data` | Application data | Recommended |
| `config` | Configuration | Optional |
| `metrics` | Metrics data | Optional |

### Backup

```bash
docker run --rm \
  -v neo4j_data:/data \
  -v "$(pwd)/backups:/backup" \
  alpine tar czf "/backup/neo4j-$(date +%Y%m%d).tar.gz" /data
```

### Restore

```bash
make docker-down

docker run --rm \
  -v neo4j_data:/data \
  -v "$(pwd)/backups:/backup" \
  alpine tar xzf /backup/neo4j-20260626.tar.gz -C /

make docker-up-dev
```

### Reset

```bash
make docker-down
docker volume rm neo4j_data neo4j_logs neo4j_import
make docker-up-dev
```

## Performance Tuning

### Neo4j Memory

```yaml
services:
  neo4j:
    environment:
      - NEO4J_server_memory_heap_max__size=1G
      - NEO4J_server_memory_pagecache_size=512M
```

**Guidelines:**

- Heap: 25-50% of available RAM
- Page cache: 50-75% of available RAM
- Total: should not exceed 90% of available RAM

### Reduce Data Size for Development

```bash
# In .env
SBIR_ETL__EXTRACTION__SAMPLE_LIMIT=1000
```

## Troubleshooting

Start with the quick diagnostics, then jump to the matching section below.

### Quick Diagnostics

```bash
# 1. Check prerequisites
make docker-check-prerequisites

# 2. Check service status
docker compose --profile dev ps

# 3. Verify setup
make docker-verify

# 4. Check logs
make docker-logs SERVICE=<service-name>
```

### Prerequisites Issues

**Docker not found** — install Docker Desktop (macOS/Windows:
<https://www.docker.com/products/docker-desktop/>; Linux:
<https://docs.docker.com/engine/install/>) and verify with `docker --version`
(20.10+). On Linux you may need to add your user to the `docker` group.

**Docker daemon not running** — start Docker Desktop, or on Linux
`sudo systemctl start docker`, then verify with `docker info`.

**Docker Compose V2 not found** — update Docker Desktop (it bundles Compose V2) and
verify with `docker compose version`.

**Ports already in use** — find the offender and free the port:

```bash
lsof -i :3000   # or 7474 / 7687
docker ps && docker stop <container-id>   # if a container holds it
```

You can also remap ports in `.env` (`DAGSTER_PORT`, `NEO4J_HTTP_PORT`,
`NEO4J_BOLT_PORT`) and restart with `make docker-down && make docker-up-dev`.

### Build Issues

**Out of space** (`no space left on device`):

```bash
docker system df          # inspect usage
docker system prune -a    # remove unused images/containers/networks
docker volume prune       # remove unused volumes (deletes data)
docker builder prune      # clear build cache
```

In Docker Desktop, increase the disk image size under Settings → Resources → Advanced.

**Build is slow / fails on ML packages** — increase Docker RAM (Settings → Resources;
4GB+ RAM, 2+ CPUs recommended), avoid `--no-cache`, and watch progress with:

```bash
DOCKER_BUILDKIT=1 docker build --progress=plain -t sbir-analytics:latest .
```

```bash
# Capture full build output for debugging
docker build -t sbir-analytics:latest . 2>&1 | tee build.log
```

### Service Startup Issues

**Services won't start** — check status, logs, and prerequisites, then restart:

```bash
docker compose --profile dev ps
make docker-logs SERVICE=neo4j
make docker-logs SERVICE=dagster-webserver
make docker-check-prerequisites
make docker-down && make docker-up-dev
```

**Neo4j won't start:**

```bash
make docker-logs SERVICE=neo4j   # inspect logs
grep NEO4J .env                  # verify credentials
lsof -i :7474; lsof -i :7687     # check port conflicts
make neo4j-reset                 # WARNING: deletes all Neo4j data
```

Neo4j needs enough memory to start — increase Docker RAM and review memory settings in
`config/neo4j/neo4j.conf`.

**Dagster webserver won't start:**

```bash
make docker-logs SERVICE=dagster-webserver
make neo4j-check                 # Dagster waits for Neo4j
lsof -i :3000
# In .env, raise the dependency wait if needed:
#   SERVICE_STARTUP_TIMEOUT=180
docker compose --profile dev exec dagster-webserver env | grep PYTHON
```

### Connection Issues

**Can't connect to Neo4j:**

```bash
docker compose --profile dev ps neo4j     # should show "Up"
grep NEO4J .env                            # verify credentials
docker compose --profile dev exec neo4j cypher-shell -u neo4j -p test 'RETURN 1'
nc -zv localhost 7687                      # verify port mapping
```

**Can't access the Dagster UI:**

```bash
docker compose --profile dev ps dagster-webserver
lsof -i :3000
make docker-logs SERVICE=dagster-webserver
curl http://localhost:3000/server_info     # should return JSON
```

Dagster takes 30-60 seconds to start; wait for the "Server started" log line.

### Performance Issues

Slow responses or timeouts usually mean Docker needs more resources. Allocate more CPU/RAM
(Settings → Resources), inspect per-container usage with `docker stats`, tune Neo4j memory
(see [Performance Tuning](#performance-tuning)), and reduce the working data set with
`SBIR_ETL__EXTRACTION__SAMPLE_LIMIT`.

### Data Persistence Issues

```bash
docker compose --profile dev config   # confirm volume configuration
docker volume ls | grep neo4j         # neo4j_data / neo4j_logs / neo4j_import
ls -la data/                          # bind-mounted dev data
```

### Environment Variable Issues

```bash
ls -la .env                                  # must be in the project root
# Syntax: no spaces around '=' (NEO4J_USER=neo4j, not NEO4J_USER = neo4j)
make docker-down && make docker-up-dev       # vars load at startup
env | grep NEO4J                             # system env overrides .env
docker compose --profile dev exec dagster-webserver env | grep NEO4J
```

### Getting Help

If you are still stuck, collect logs (`make docker-logs SERVICE=<service>`), run
diagnostics (`make docker-check-prerequisites`, `make docker-verify`), and search/open a
GitHub issue with error messages, log output, and reproduction steps.

## Related Documentation

- [Configuration Patterns](../configuration.md) - Environment variable overrides
- [Configuration Management](../../config/README.md) - Configuration system overview
- [Testing Guide](../testing/index.md) - Running tests in Docker
- [Dockerfile](../../Dockerfile) - ETL image source
- [docker-compose.yml](../../docker-compose.yml) - Compose configuration
