# Getting Started

Quick setup guides for the SBIR ETL pipeline.

## Local Development

```bash
# Clone and install
git clone https://github.com/hollomancer/sbir-analytics
cd sbir-analytics
uv sync

# Start Dagster UI
uv run dagster dev
# Open http://localhost:3000
```

## First Steps

1. **Materialize assets** - In Dagster UI, materialize `raw_sbir_awards`
2. **View data** - Check Neo4j Browser at <http://localhost:7474>
3. **Run tests** - `uv run pytest tests/unit/ -v`

## Environment Setup

Create `.env` from template:

```bash
cp .env.example .env
```

Required variables:

```bash
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
```

## Next Steps

- [Docker Setup](../development/docker.md) - Container-based development
- [Deployment Guide](../deployment/README.md) - Production deployment
- [Testing Guide](../testing/index.md) - Running tests
- [Configuration](../configuration.md) - YAML configuration
