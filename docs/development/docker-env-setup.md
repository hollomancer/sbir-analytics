# Docker Environment Setup

Configuration guide for Docker-based development.

## Environment Variables

Create `.env` from template:

```bash
cp .env.example .env
```

### Required Variables

```bash
# Neo4j connection (local Docker)
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

### Optional Variables

```bash
# S3 bucket for data (AWS deployment)
S3_BUCKET=sbir-etl-production-data

# Dagster home directory
DAGSTER_HOME=/app/.dagster

# Python environment
PYTHONPATH=/app/src
```

## Docker Compose Configuration

The `docker-compose.yml` uses profiles to separate environments:

```yaml
# Development profile
docker-compose --profile dev up -d

# Test profile (CI)
docker-compose --profile test up -d
```

## Volume Mounts

Development profile mounts local directories for live editing:

| Local | Container | Purpose |
|-------|-----------|---------|
| `./src` | `/app/src` | Source code |
| `./tests` | `/app/tests` | Test files |
| `./config` | `/app/config` | Configuration |

## Neo4j Configuration

Local Neo4j uses these settings:

```yaml
environment:
  NEO4J_AUTH: neo4j/password
  NEO4J_PLUGINS: '["apoc"]'
ports:
  - "7474:7474"  # HTTP
  - "7687:7687"  # Bolt
```

## Related

- [Docker Quick Start](docker-quickstart.md)
- [Docker Troubleshooting](docker-troubleshooting.md)
