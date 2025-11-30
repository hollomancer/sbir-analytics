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
