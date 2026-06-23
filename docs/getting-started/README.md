# Getting Started

Quick setup guides for the SBIR ETL pipeline.

## Local Development

The project uses Python 3.11 and [`uv`](https://github.com/astral-sh/uv) for dependency management. The recommended local flow mirrors the repository README:

```bash
# Clone and install
git clone https://github.com/hollomancer/sbir-analytics
cd sbir-analytics
make install

# Start Dagster UI
make dev
# Open http://localhost:3000
```

If you prefer to run the underlying commands directly, `make install` is equivalent to `uv sync`, and `make dev` runs:

```bash
uv run dagster dev -m sbir_analytics.definitions
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

- [Local Development Setup](local-development.md) - Detailed local workflow
- [Docker Setup](../development/docker.md) - Container-based development
- [Deployment Guide](../deployment/README.md) - Production deployment
- [Testing Guide](../testing/index.md) - Running tests
- [Configuration](../configuration.md) - YAML configuration
