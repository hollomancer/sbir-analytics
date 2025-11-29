---
Type: Guide
Owner: devops@project
Last-Reviewed: 2025-01-XX
Status: active
---

# Docker Environment Setup Guide

This guide explains how to configure environment variables for Docker development. It covers minimal setup (quick start) and full configuration (production-like testing).

## Quick Start: Minimal Setup

For **local development**, you only need these variables in `.env`:

```bash
# Neo4j credentials (for local Docker Neo4j)
NEO4J_USER=neo4j
NEO4J_PASSWORD=test
```

**That's it!** Everything else has sensible defaults.

## Environment File Structure

The `.env` file uses this structure:

```bash
# =============================================================================
# Neo4j Configuration
# =============================================================================
NEO4J_USER=neo4j
NEO4J_PASSWORD=test
NEO4J_URI=bolt://neo4j:7687

# =============================================================================
# Dagster Configuration
# =============================================================================
DAGSTER_PORT=3000
ENVIRONMENT=dev

# =============================================================================
# Data Storage
# =============================================================================
SBIR_ETL_USE_S3=false
SBIR_ETL_S3_BUCKET=

# =============================================================================
# Optional: Advanced Configuration
# =============================================================================
# ... (see sections below)
```

## Required Variables

### For Local Docker Development

**Minimum required:**
```bash
NEO4J_USER=neo4j
NEO4J_PASSWORD=test
```

**Why:** These authenticate to the local Neo4j container. The defaults work fine for development.

### For Neo4j Aura (Cloud)

If using Neo4j Aura instead of local Docker:

```bash
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-aura-password
```

**Note:** When using Aura, you don't need to start the local Neo4j container. Set `NEO4J_URI` and the application will connect to Aura.

## Optional Variables

### Data Storage

**Local filesystem (default):**
```bash
SBIR_ETL_USE_S3=false
# Data stored in ./data directory
```

**AWS S3:**
```bash
SBIR_ETL_USE_S3=true
SBIR_ETL_S3_BUCKET=your-bucket-name
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION=us-east-1
```

**When to use S3:**
- Testing S3 integration
- Working with large datasets
- Production-like testing

### Dagster Configuration

```bash
# Port for Dagster UI
DAGSTER_PORT=3000

# Environment (affects logging, behavior)
ENVIRONMENT=dev  # or: test, prod

# Startup timeout (seconds)
SERVICE_STARTUP_TIMEOUT=120
```

### Neo4j Advanced

```bash
# Neo4j host (default: neo4j - Docker service name)
SBIR_ETL__NEO4J__HOST=neo4j

# Neo4j port (default: 7687)
SBIR_ETL__NEO4J__PORT=7687

# Connection timeout
SBIR_ETL__NEO4J__CONNECTION_TIMEOUT=30
```

### Performance Tuning

```bash
# Batch sizes for processing
SBIR_ETL__NEO4J__BATCH_SIZE=1000

# Memory limits (if needed)
SBIR_ETL__NEO4J__MEMORY__HEAP_MAX_SIZE=1G
SBIR_ETL__NEO4J__MEMORY__PAGECACHE_SIZE=256M
```

## Configuration Hierarchy

Environment variables are loaded in this order (later overrides earlier):

1. **System environment variables** (highest priority)
2. **`.env` file** in project root
3. **`config/.env`** (if exists)
4. **YAML config files** (`config/base.yaml`, `config/dev.yaml`)
5. **Docker Compose environment** (from `docker-compose.yml`)

**Best practice:** Use `.env` for local overrides, system env vars for secrets.

## Variable Naming

### SBIR ETL Variables

Variables prefixed with `SBIR_ETL__` use double underscores to represent nested config:

```bash
# Maps to config.neo4j.host
SBIR_ETL__NEO4J__HOST=neo4j

# Maps to config.data_quality.completeness.company_name
SBIR_ETL__DATA_QUALITY__COMPLETENESS__COMPANY_NAME=0.95
```

### Docker Compose Variables

Variables used by Docker Compose directly:

```bash
# Image configuration
IMAGE_NAME=sbir-analytics
IMAGE_TAG=latest

# Service names
NEO4J_CONTAINER_NAME=sbir-neo4j
DAGSTER_WEBSERVER_CONTAINER_NAME=sbir-dagster-web

# Ports
NEO4J_HTTP_PORT=7474
NEO4J_BOLT_PORT=7687
DAGSTER_PORT=3000
```

## Common Configurations

### Configuration 1: Local Development (Minimal)

**Use case:** Quick local development, no external services

```bash
# .env
NEO4J_USER=neo4j
NEO4J_PASSWORD=test
SBIR_ETL_USE_S3=false
ENVIRONMENT=dev
```

### Configuration 2: Local with S3

**Use case:** Testing S3 integration locally

```bash
# .env
NEO4J_USER=neo4j
NEO4J_PASSWORD=test
SBIR_ETL_USE_S3=true
SBIR_ETL_S3_BUCKET=my-test-bucket
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION=us-east-1
```

### Configuration 3: Neo4j Aura

**Use case:** Using cloud Neo4j instead of local

```bash
# .env
NEO4J_URI=neo4j+s://your-instance.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=your-aura-password
SBIR_ETL_USE_S3=false
ENVIRONMENT=dev
```

**Note:** Don't start local Neo4j container when using Aura.

### Configuration 4: Production-Like Testing

**Use case:** Testing with production-like settings

```bash
# .env
NEO4J_USER=neo4j
NEO4J_PASSWORD=secure-password
NEO4J_URI=bolt://neo4j:7687
SBIR_ETL_USE_S3=true
SBIR_ETL_S3_BUCKET=test-bucket
ENVIRONMENT=test
SBIR_ETL__NEO4J__BATCH_SIZE=500
```

## Validating Configuration

### Check Required Variables

The Makefile validates `.env` exists:

```bash
make env-check
```

### Validate Neo4j Connection

```bash
make neo4j-check
```

### Full Setup Verification

```bash
make docker-verify
```

## Troubleshooting Configuration

### Variable Not Taking Effect

1. **Check variable name:** Use double underscores for nested config (`SBIR_ETL__NEO4J__HOST`)
2. **Check `.env` location:** Must be in project root
3. **Restart services:** `make docker-down && make docker-up-dev`
4. **Check precedence:** System env vars override `.env`

### Neo4j Connection Issues

**Problem:** Can't connect to Neo4j

**Check:**
```bash
# Verify credentials
echo $NEO4J_USER
echo $NEO4J_PASSWORD

# Test connection
make neo4j-check
```

**Common fixes:**
- Ensure `.env` has correct credentials
- If using Aura, verify `NEO4J_URI` is correct
- Check Neo4j container is running: `docker compose --profile dev ps neo4j`

### S3 Configuration Issues

**Problem:** S3 operations failing

**Check:**
```bash
# Verify S3 is enabled
echo $SBIR_ETL_USE_S3

# Verify credentials
echo $AWS_ACCESS_KEY_ID
echo $AWS_SECRET_ACCESS_KEY
```

**Common fixes:**
- Ensure `SBIR_ETL_USE_S3=true` (not `True` or `1`)
- Verify AWS credentials are correct
- Check bucket exists and is accessible

## Security Best Practices

### ✅ Do

- **Use `.env` for local development** (gitignored)
- **Use system env vars for secrets** in production
- **Use Docker secrets** for sensitive data in containers
- **Rotate credentials regularly**

### ❌ Don't

- **Commit `.env` to git** (it's in `.gitignore`)
- **Hardcode secrets in code**
- **Share `.env` files** (each developer should have their own)
- **Use production credentials in `.env`**

## Environment Variable Reference

### Complete List

See `.env.example` for the complete list of available variables with descriptions.

**Categories:**
- Neo4j configuration
- Dagster configuration
- Data storage (S3/local)
- Performance tuning
- Feature flags
- Logging configuration

## Next Steps

- **[Docker Quick Start](docker-quickstart.md)** - Get started with Docker
- **[Troubleshooting Guide](docker-troubleshooting.md)** - Common issues
- **[Containerization Guide](../deployment/containerization.md)** - Advanced Docker usage
- **[Configuration Guide](../../config/README.md)** - Full configuration documentation

---

**Need help?** Check the [Troubleshooting Guide](docker-troubleshooting.md) or see [Configuration Guide](../../config/README.md) for detailed variable documentation.
