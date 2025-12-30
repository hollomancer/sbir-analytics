# Containerization Guide

Docker-based development and deployment for the SBIR ETL pipeline.

## Quick Start

```bash
# Start development environment
make docker-up-dev

# Run tests in container
make docker-test

# View logs
make docker-logs
```

## Docker Compose Profiles

The project uses a single `docker-compose.yml` with profiles:

| Profile | Purpose | Services |
|---------|---------|----------|
| `dev` | Local development | app, neo4j |
| `test` | CI testing | app, neo4j (ephemeral) |
| `prod` | Production-like | app (optimized) |

## Common Commands

```bash
# Build images
make docker-build

# Start with specific profile
docker-compose --profile dev up -d

# Execute command in container
docker-compose exec app uv run pytest

# Stop all services
make docker-down
```

## Neo4j Service

Local Neo4j runs on:

- Bolt: `bolt://localhost:7687`
- HTTP: `http://localhost:7474`

Default credentials: `neo4j/password`

## Environment Variables

Set in `.env` or pass to docker-compose:

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

## Troubleshooting

See [Docker Troubleshooting](../development/docker.md) for common issues.

## Related

- [Docker Reference](docker.md) - Detailed configuration
- [Docker Guide](docker.md) - Extended usage
- [AWS Deployment](aws-deployment.md) - Production deployment
