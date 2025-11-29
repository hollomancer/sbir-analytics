# Docker Configuration Reference

**Audience**: DevOps, Advanced Users
**Prerequisites**: [Docker Guide](docker-guide.md)
**Related**: [Docker Optimization](docker-optimization.md), [Dockerfile](../../Dockerfile)
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

See [Configuration Patterns](.kiro/steering/configuration-patterns.md) for complete reference.

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

- [Docker Guide](docker-guide.md) - Getting started and common tasks
- [Docker Optimization](docker-optimization.md) - Advanced optimization techniques
- [Docker Troubleshooting](../development/docker-troubleshooting.md) - Common issues
- [Configuration Patterns](.kiro/steering/configuration-patterns.md) - Configuration reference
- [Dockerfile](../../Dockerfile) - Source Dockerfile
- [docker-compose.yml](../../docker-compose.yml) - Source Compose file
