# Getting Started

> **Operational data caveat.** No SBIR/STTR award data is committed to this repository. The setup commands below install dependencies and start local development services; they do not recreate the full research dataset by themselves. Full dataset reproduction requires downloading source/bulk data, adding your own API credentials to `.env`, and running supporting services such as Neo4j, so reproducing the analyses end-to-end is non-trivial.


Quick setup guide for the SBIR ETL pipeline.

## Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) for dependency management
- Docker (optional, for local Neo4j)

## Local Development

The project uses Python 3.11 and `uv` for dependency management. The recommended local flow mirrors the repository README:

```bash
# Clone and install
git clone https://github.com/hollomancer/sbir-analytics
cd sbir-analytics
make install

# Copy environment template
cp .env.example .env

# Start Dagster UI
make dev
# Open http://localhost:3000
```

If you prefer to run the underlying commands directly, `make install` is equivalent to `uv sync`, and `make dev` runs:

```bash
uv run dagster dev -m sbir_analytics.definitions
```

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

## Neo4j Setup

Start Neo4j locally with Docker:

```bash
docker compose --profile dev up neo4j -d
# Access at http://localhost:7474 (neo4j/password)
```

## First Steps

1. **Materialize assets** - In Dagster UI, materialize `raw_sbir_awards`
2. **View data** - Check Neo4j Browser at <http://localhost:7474>
3. **Run tests** - `uv run pytest tests/unit/ -v`

## Development Workflow

```bash
# Run tests
uv run pytest

# Code quality
uv run ruff check .
uv run mypy sbir_etl/

# Format code
uv run ruff format .
```

## Common Issues

- **Neo4j connection failed**: Check `.env` credentials
- **Import errors**: Run `make install` (or `uv sync`) to update dependencies
- **Memory issues**: Reduce `SBIR_ETL__PIPELINE__CHUNK_SIZE`

## Next Steps

- [Docker Setup](../development/docker.md) - Container-based development
- [Deployment Guide](../deployment/README.md) - Production deployment
- [Testing Guide](../testing/index.md) - Running tests
- [Configuration](../configuration.md) - YAML configuration
