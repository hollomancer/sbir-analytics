# Docker Development Guide

**Audience**: Developers
**Prerequisites**: Docker 20.10+, Docker Compose V2
**Related**: [Docker Reference](docker-reference.md), [Docker Troubleshooting](../development/docker-troubleshooting.md)
**Last Updated**: 2025-11-29

## Overview

Docker Compose is the **failover option** for local development. **Dagster Cloud Solo Plan** is the primary deployment method. Use Docker for:
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

See [Configuration Patterns](.kiro/steering/configuration-patterns.md) for complete reference.

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

For more troubleshooting, see [Docker Troubleshooting Guide](../development/docker-troubleshooting.md).

## Related Documentation

- [Docker Reference](docker-reference.md) - Configuration and optimization details
- [Docker Troubleshooting](../development/docker-troubleshooting.md) - Common issues and solutions
- [Dagster Cloud Deployment](dagster-cloud.md) - Primary deployment method
- [Testing Guide](../testing/index.md) - Running tests in Docker
- [Configuration Patterns](.kiro/steering/configuration-patterns.md) - Environment variable overrides
