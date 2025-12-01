# Docker Development Guide

**Audience**: Developers
**Prerequisites**: Docker 20.10+, Docker Compose V2
**Related**: [Docker Reference](docker.md), [Docker Troubleshooting](../development/docker.md)
**Last Updated**: 2025-11-29

## Overview

Docker Compose is the **failover option** for local development. **GitHub Actions Solo Plan** is the primary deployment method. Use Docker for:
- Local development without cloud dependencies
- CI/CD testing (mirrors production environment)
- Emergency failover scenarios

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

**Production-like configuration**:
```bash
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<secure-password>  # pragma: allowlist secret
AWS_PROFILE=default  # Optional: for S3 access
DAGSTER_HOME=/opt/dagster/dagster_home
```

See [Environment Variables](#environment-variables) for complete reference.

### 3. Build and Start

```bash
# Build image (10-20 minutes first time)
make docker-build

# Start development services
make docker-up-dev

# Verify setup
make docker-verify
```

**Services available:**
- Dagster UI: http://localhost:3000
- Neo4j Browser: http://localhost:7474
- Neo4j Bolt: bolt://localhost:7687

### 4. Development Workflow

```bash
# View logs
make docker-logs

# Run tests
make docker-test

# Rebuild after code changes
make docker-rebuild

# Stop services
make docker-down
```

## Compose Profiles

The project uses a single `docker-compose.yml` with profiles for different scenarios:

| Profile | Use Case | Services | Command |
|---------|----------|----------|---------|
| `dev` | Local development | Neo4j, Dagster (bind mounts) | `make docker-up-dev` |
| `ci` | CI/CD testing | Neo4j, App (pytest) | `make docker-test` |
| `prod` | Production-like | Neo4j, Dagster (optimized) | `docker compose --profile prod up` |

### Development Profile

**Features:**
- Bind mounts for live code editing
- Hot reload enabled
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
- Mirrors GitHub Actions environment
- Runs pytest automatically
- Ephemeral containers
- No bind mounts

**Start:**
```bash
make docker-test
# or
docker compose --profile ci up --abort-on-container-exit
```

### Production Profile

**Features:**
- Optimized image (no dev dependencies)
- Health checks enabled
- Resource limits configured
- Persistent volumes

**Start:**
```bash
docker compose --profile prod up -d
```

## Common Tasks

### Materialize Assets

```bash
# Via Dagster UI
# 1. Open http://localhost:3000
# 2. Navigate to Assets
# 3. Select assets to materialize
# 4. Click "Materialize"

# Via CLI
docker compose exec app dagster asset materialize -m src.definitions
```

### Run Specific Job

```bash
docker compose exec app dagster job execute \
  -f src/definitions.py \
  -j sbir_ingestion_job
```

### Access Neo4j

```bash
# Via Browser
open http://localhost:7474

# Via Cypher Shell
docker compose exec neo4j cypher-shell -u neo4j -p test
```

### View Logs

```bash
# All services
make docker-logs

# Specific service
make docker-logs SERVICE=app

# Follow logs
docker compose logs -f app
```

### Execute Commands in Container

```bash
# Interactive shell
docker compose exec app bash

# Run Python script
docker compose exec app python scripts/data/download_sbir_data.py

# Run pytest
docker compose exec app pytest tests/unit/
```

## Environment Variables

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `NEO4J_USER` | Neo4j username | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j password | `test` |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NEO4J_URI` | Neo4j connection URI | `bolt://neo4j:7687` |
| `DAGSTER_HOME` | Dagster home directory | `/opt/dagster/dagster_home` |
| `AWS_PROFILE` | AWS profile for S3 access | `default` |
| `SBIR_ETL_ENV` | Environment name | `dev` |

### Override Configuration

Use `SBIR_ETL__` prefix to override any config value:

```bash
export SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
export SBIR_ETL__PIPELINE__CHUNK_SIZE=20000
```

See [Configuration Patterns](../../.kiro/steering/configuration-patterns.md) for complete reference.

## Build Options

### Standard Build (with R)

```bash
make docker-build
# or
docker build -t sbir-analytics:latest .
```

**Build time:** 10-20 minutes (includes R packages)

### Fast Build (without R)

```bash
docker build --build-arg BUILD_WITH_R=false -t sbir-analytics:ci .
```

**Build time:** 2-3 minutes (CI builds)

### Using Pre-built R Base

```bash
docker build \
  --build-arg USE_R_BASE_IMAGE=true \
  -t sbir-analytics:latest .
```

**Build time:** 5-7 minutes (uses cached R packages)

## Data Volumes

### Volume Structure

```
sbir-analytics_neo4j-data/     # Neo4j database
sbir-analytics_dagster-home/   # Dagster metadata
sbir-analytics_app-data/       # Application data
```

### Backup Volumes

```bash
# Backup Neo4j data
docker run --rm \
  -v sbir-analytics_neo4j-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/neo4j-$(date +%Y%m%d).tar.gz /data
```

### Reset Volumes

```bash
# Stop services
make docker-down

# Remove volumes
docker volume rm sbir-analytics_neo4j-data
docker volume rm sbir-analytics_dagster-home

# Restart
make docker-up-dev
```

## Performance Optimization

### Resource Limits

Edit `docker-compose.yml` to adjust resource limits:

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

### Build Cache

Use BuildKit for faster builds:

```bash
export DOCKER_BUILDKIT=1
make docker-build
```

### Multi-stage Caching

The Dockerfile uses multi-stage builds with aggressive caching:
- Builder stage: Cached until dependencies change
- Runtime stage: Cached until code changes

## Troubleshooting

### Services Won't Start

```bash
# Check port conflicts
make docker-check-prerequisites

# Check logs
make docker-logs

# Restart services
make docker-rebuild
```

### Neo4j Connection Issues

```bash
# Check Neo4j health
make neo4j-check

# Verify credentials
docker compose exec neo4j cypher-shell -u neo4j -p test

# Check URI
echo $NEO4J_URI
```

### Build Failures

```bash
# Clean build cache
docker builder prune -a

# Rebuild from scratch
docker build --no-cache -t sbir-analytics:latest .
```

### Out of Disk Space

```bash
# Clean up unused images
docker system prune -a

# Remove old volumes
docker volume prune
```

For more troubleshooting, see [Docker Troubleshooting Guide](../development/docker.md).

## Related Documentation

- [Docker Reference](docker.md) - Configuration and optimization details
- [Docker Troubleshooting](../development/docker.md) - Common issues and solutions
- [GitHub Actions Deployment](README.md) - Primary deployment method
- [Testing Guide](../testing/index.md) - Running tests in Docker
- [Configuration Patterns](../../.kiro/steering/configuration-patterns.md) - Environment variable overrides
# Docker Image Optimization Guide

## Current Optimizations

### Multi-Stage Build
- **Builder stage**: Compiles wheels, installs build dependencies
- **Runtime stage**: Only includes runtime dependencies and wheels
- **Impact**: ~60% smaller final image

### Layer Caching
- Dependencies copied before code for better cache hits
- UV cache mounted for faster builds
- Pip cache mounted for wheel building
- **Impact**: 2-3x faster rebuilds

### .dockerignore Optimization
- Excludes 100+ MB of unnecessary files:
  - Test data and fixtures
  - CI/CD configurations
  - Documentation and notebooks
  - Build artifacts and caches
  - Development tools
- **Impact**: Faster context transfer, smaller image

### Conditional R Installation
- R packages only installed when needed
- Pre-built R base image option for faster builds
- **Impact**: 40% faster builds without R

## Image Size Comparison

| Build Type | Size | Build Time |
|------------|------|------------|
| Full (with R) | ~1.2 GB | ~5 min |
| With R cache | ~1.2 GB | ~2 min |
| Without R (CI) | ~800 MB | ~2 min |

## Build Optimization Tips

### 1. Use BuildKit
```bash
DOCKER_BUILDKIT=1 docker build -t sbir-analytics .
```

### 2. Use Cache Mounts
Already implemented in Dockerfile:
```dockerfile
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=cache,target=/root/.cache/pip
```

### 3. Layer Ordering
Dependencies before code for better caching:
```dockerfile
COPY pyproject.toml uv.lock* /workspace/  # Changes rarely
# ... build dependencies ...
COPY . /workspace/  # Changes frequently
```

### 4. Multi-Platform Builds
```bash
docker buildx build --platform linux/amd64,linux/arm64 -t sbir-analytics .
```

## Runtime Optimizations

### 1. Non-Root User
- Runs as `sbir` user (UID 1000)
- Better security posture
- Compatible with Kubernetes security policies

### 2. Minimal Runtime Dependencies
- Only essential packages in runtime stage
- Build tools excluded
- Test dependencies excluded

### 3. Tini for PID 1
- Proper signal handling
- Zombie process reaping
- Clean shutdown

## Further Optimization Opportunities

### 1. Distroless Base (Advanced)
Switch to distroless for even smaller images:
```dockerfile
FROM gcr.io/distroless/python3-debian12
```
**Trade-off**: No shell, harder debugging

### 2. Alpine Base (Not Recommended)
Alpine is smaller but has compatibility issues:
- musl vs glibc differences
- Slower Python performance
- Wheel compatibility problems

### 3. Slim Down Python
Remove unnecessary Python stdlib modules:
```dockerfile
RUN find /usr/local/lib/python3.11 -name "test" -type d -exec rm -rf {} +
RUN find /usr/local/lib/python3.11 -name "*.pyc" -delete
```
**Impact**: ~50 MB saved

## Monitoring Image Size

### Check Layer Sizes
```bash
docker history sbir-analytics:latest --human --no-trunc
```

### Analyze Image
```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  wagoodman/dive sbir-analytics:latest
```

### Compare Builds
```bash
docker images sbir-analytics --format "table {{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
```

## CI/CD Integration

### GitHub Actions Cache
Already implemented in ci.yml:
```yaml
cache-from: |
  type=registry,ref=ghcr.io/${{ github.repository }}:latest
  type=gha,scope=ci-no-r
cache-to: type=gha,mode=max,scope=ci-no-r
```

### Registry Cache
Push to GHCR for cross-runner caching:
```yaml
push: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}
```

## Best Practices

1. ✅ **Multi-stage builds** - Separate build and runtime
2. ✅ **Layer caching** - Order layers by change frequency
3. ✅ **Cache mounts** - Use BuildKit cache mounts
4. ✅ **.dockerignore** - Exclude unnecessary files
5. ✅ **Minimal base** - Use slim images
6. ✅ **Non-root user** - Security best practice
7. ✅ **Conditional features** - R installation optional
8. ✅ **Registry caching** - Push cache layers to registry

## Troubleshooting

### Large Image Size
```bash
# Find large layers
docker history sbir-analytics:latest --human | head -20

# Check what's in the image
docker run --rm sbir-analytics:latest du -sh /app/* | sort -h
```

### Slow Builds
```bash
# Check cache hits
DOCKER_BUILDKIT=1 docker build --progress=plain -t sbir-analytics . 2>&1 | grep CACHED

# Use build cache from registry
docker build --cache-from ghcr.io/your-repo/sbir-analytics:latest .
```

### Build Failures
```bash
# Debug specific stage
docker build --target builder -t debug .
docker run --rm -it debug /bin/bash
```

## References

- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [BuildKit Documentation](https://docs.docker.com/build/buildkit/)
- [Multi-stage Builds](https://docs.docker.com/build/building/multi-stage/)


---

# Reference

# Docker Configuration Reference

**Audience**: DevOps, Advanced Users
**Prerequisites**: [Docker Guide](docker.md)
**Related**: [Dockerfile](../../Dockerfile)
**Last Updated**: 2025-11-29

## Dockerfile Architecture

### Multi-Stage Build

```dockerfile
FROM python:3.11-slim AS builder
# Install build dependencies
# Build wheels
# Install R packages (optional)

FROM python:3.11-slim AS runtime
# Copy wheels from builder
# Install runtime dependencies
# Copy application code
```

**Benefits:**
- Small runtime image (~800MB with R, ~400MB without)
- Fast rebuilds (cached layers)
- Secure (no build tools in runtime)

### Build Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `BUILD_WITH_R` | `true` | Include R and fiscal analysis packages |
| `USE_R_BASE_IMAGE` | `false` | Use pre-built R base image |
| `R_BASE_IMAGE` | `ghcr.io/...` | R base image URL |
| `PYTHON_VERSION` | `3.11.9` | Python version |

**Examples:**

```bash
# Standard build with R
docker build -t sbir-analytics:latest .

# Fast CI build without R
docker build --build-arg BUILD_WITH_R=false -t sbir-analytics:ci .

# Use cached R packages
docker build --build-arg USE_R_BASE_IMAGE=true -t sbir-analytics:latest .
```

## Docker Compose Configuration

### Service Definitions

#### App Service

```yaml
services:
  app:
    image: sbir-analytics:${TAG:-latest}
    environment:
      - NEO4J_URI=bolt://neo4j:7687
      - NEO4J_USER=${NEO4J_USER}
      - NEO4J_PASSWORD=${NEO4J_PASSWORD}
      - DAGSTER_HOME=/opt/dagster/dagster_home
    volumes:
      - ./src:/app/src  # Dev profile only
      - ./config:/app/config
      - dagster-home:/opt/dagster/dagster_home
    depends_on:
      neo4j:
        condition: service_healthy
```

#### Neo4j Service

```yaml
services:
  neo4j:
    image: neo4j:5
    environment:
      - NEO4J_AUTH=${NEO4J_USER}/${NEO4J_PASSWORD}
      - NEO4J_PLUGINS=["apoc"]
      - NEO4J_dbms_memory_heap_max__size=2G
      - NEO4J_dbms_memory_pagecache_size=1G
    volumes:
      - neo4j-data:/data
    healthcheck:
      test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "${NEO4J_PASSWORD}", "RETURN 1"]
      interval: 10s
      timeout: 5s
      retries: 5
```

### Profile Configuration

#### Development Profile

```yaml
profiles:
  - dev

services:
  app:
    command: dagster-webserver -h 0.0.0.0 -p 3000
    volumes:
      - ./src:/app/src:ro  # Read-only bind mount
      - ./config:/app/config:ro
    environment:
      - DAGSTER_RELOAD=true
```

**Features:**
- Live code reload
- Bind mounts for fast iteration
- Debug logging enabled
- No resource limits

#### CI Profile

```yaml
profiles:
  - ci

services:
  app:
    command: pytest -v --cov=src
    environment:
      - CI=true
      - PYTEST_TIMEOUT=300
```

**Features:**
- Runs tests automatically
- Exits after completion
- No bind mounts
- Ephemeral containers

#### Production Profile

```yaml
profiles:
  - prod

services:
  app:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import src"]
      interval: 30s
      timeout: 5s
      retries: 3
```

**Features:**
- Resource limits enforced
- Auto-restart on failure
- Health checks enabled
- Optimized image

## Environment Variables

### Neo4j Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEO4J_URI` | Yes | `bolt://neo4j:7687` | Neo4j connection URI |
| `NEO4J_USER` | Yes | - | Neo4j username |
| `NEO4J_PASSWORD` | Yes | - | Neo4j password |

### Dagster Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DAGSTER_HOME` | No | `/opt/dagster/dagster_home` | Dagster metadata directory |
| `DAGSTER_RELOAD` | No | `false` | Enable hot reload (dev only) |

### AWS Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AWS_PROFILE` | No | `default` | AWS profile for S3 access |
| `AWS_REGION` | No | `us-east-2` | AWS region |
| `AWS_ACCESS_KEY_ID` | No | - | AWS access key (alternative to profile) |
| `AWS_SECRET_ACCESS_KEY` | No | - | AWS secret key (alternative to profile) |

### Application Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SBIR_ETL_ENV` | No | `dev` | Environment name (dev/prod) |
| `PYTHONUNBUFFERED` | No | `1` | Disable Python output buffering |
| `LOG_LEVEL` | No | `INFO` | Logging level |

### Configuration Overrides

Use `SBIR_ETL__` prefix to override any config value:

```bash
# Override Neo4j settings
export SBIR_ETL__NEO4J__URI="bolt://localhost:7687"
export SBIR_ETL__NEO4J__BATCH_SIZE=2000

# Override pipeline settings
export SBIR_ETL__PIPELINE__CHUNK_SIZE=20000
export SBIR_ETL__ENRICHMENT__BATCH_SIZE=200

# Override quality thresholds
export SBIR_ETL__DATA_QUALITY__MIN_ENRICHMENT_SUCCESS=0.85
```

See [Configuration Patterns](../../.kiro/steering/configuration-patterns.md) for complete reference.

## Volume Management

### Volume Types

| Volume | Type | Purpose | Backup |
|--------|------|---------|--------|
| `neo4j-data` | Named | Neo4j database | Required |
| `dagster-home` | Named | Dagster metadata | Recommended |
| `app-data` | Named | Application data | Optional |
| `./src` | Bind | Source code (dev) | N/A |
| `./config` | Bind | Configuration | N/A |

### Backup Strategy

```bash
# Backup Neo4j data
docker run --rm \
  -v sbir-analytics_neo4j-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/neo4j-$(date +%Y%m%d).tar.gz /data

# Backup Dagster metadata
docker run --rm \
  -v sbir-analytics_dagster-home:/data \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/dagster-$(date +%Y%m%d).tar.gz /data
```

### Restore Strategy

```bash
# Stop services
docker compose down

# Restore Neo4j data
docker run --rm \
  -v sbir-analytics_neo4j-data:/data \
  -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/neo4j-20251129.tar.gz -C /

# Restart services
docker compose --profile prod up -d
```

## Performance Optimization

### Build Optimization

#### Layer Caching

```dockerfile
# Copy dependencies first (changes infrequently)
COPY pyproject.toml uv.lock* /workspace/

# Install dependencies (cached layer)
RUN uv export --no-hashes -o requirements.txt

# Copy code last (changes frequently)
COPY . /workspace/
```

#### BuildKit Features

```bash
# Enable BuildKit
export DOCKER_BUILDKIT=1

# Use cache mounts
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
```

### Runtime Optimization

#### Resource Limits

```yaml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '4'
          memory: 8G
        reservations:
          cpus: '2'
          memory: 4G
```

#### Neo4j Memory Tuning

```yaml
services:
  neo4j:
    environment:
      # Heap size (JVM)
      - NEO4J_dbms_memory_heap_max__size=4G
      - NEO4J_dbms_memory_heap_initial__size=2G

      # Page cache (graph data)
      - NEO4J_dbms_memory_pagecache_size=2G

      # Transaction state
      - NEO4J_dbms_memory_transaction_max__size=1G
```

**Guidelines:**
- Heap: 25-50% of available RAM
- Page cache: 50-75% of available RAM
- Total: Should not exceed 90% of available RAM

### Network Optimization

```yaml
networks:
  sbir-net:
    driver: bridge
    ipam:
      config:
        - subnet: 172.28.0.0/16
```

## Security Configuration

### User Permissions

```dockerfile
# Create non-root user
RUN groupadd -g 1000 sbir && \
    useradd -m -u 1000 -g 1000 sbir

# Switch to non-root user
USER sbir
```

### Secret Management

**Never commit secrets to `.env` file:**

```bash
# Use environment variables
export NEO4J_PASSWORD=$(cat /run/secrets/neo4j_password)

# Or use Docker secrets
docker secret create neo4j_password /path/to/secret
```

### Network Isolation

```yaml
services:
  app:
    networks:
      - sbir-net
  neo4j:
    networks:
      - sbir-net
    # Don't expose ports externally in production
```

## Health Checks

### Application Health Check

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD python -c "import importlib; importlib.import_module('src')" || exit 1
```

### Neo4j Health Check

```yaml
healthcheck:
  test: ["CMD", "cypher-shell", "-u", "neo4j", "-p", "${NEO4J_PASSWORD}", "RETURN 1"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 30s
```

### Dagster Health Check

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:3000/server_info"]
  interval: 30s
  timeout: 5s
  retries: 3
```

## Logging Configuration

### Application Logging

```yaml
services:
  app:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

### Centralized Logging

```yaml
services:
  app:
    logging:
      driver: "syslog"
      options:
        syslog-address: "tcp://logstash:5000"
        tag: "sbir-analytics"
```

## Monitoring Integration

### Prometheus Metrics

```yaml
services:
  app:
    environment:
      - PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
    ports:
      - "9090:9090"
```

### Grafana Dashboards

```yaml
services:
  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    volumes:
      - ./monitoring/dashboards:/etc/grafana/provisioning/dashboards
```

## Related Documentation

- [Docker Guide](docker.md) - Getting started and common tasks

- [Docker Troubleshooting](../development/docker.md) - Common issues
- [Configuration Patterns](../../.kiro/steering/configuration-patterns.md) - Configuration reference
- [Dockerfile](../../Dockerfile) - Source Dockerfile
- [docker-compose.yml](../../docker-compose.yml) - Source Compose file
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
- [Configuration Management](../../config/README.md) - Configuration system overview
- [Docker Compose File](../../docker-compose.yml) - Main compose configuration
