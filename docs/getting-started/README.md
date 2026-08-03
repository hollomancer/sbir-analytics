# Getting Started

> **Operational data caveat.** No SBIR/STTR award data is committed to this repository. The setup commands below install dependencies and start local development services; they do not recreate the full research dataset by themselves. Full dataset reproduction requires downloading source/bulk data, adding your own API credentials to `.env`, and running supporting services such as Neo4j, so reproducing the analyses end-to-end is non-trivial.


Quick setup guide for the SBIR ETL pipeline.

## Prerequisites

- Python 3.11 or 3.12
- [`uv`](https://github.com/astral-sh/uv) for dependency management
- Docker (optional, for local Neo4j)

## Local Development

The project supports Python 3.11 or 3.12 and uses `uv` for dependency management. The recommended
local flow mirrors the repository README:

```bash
# Clone and install
git clone https://github.com/hollomancer/sbir-analytics
cd sbir-analytics
make install  # full stack: sbir_etl + Dagster + ML + graph packages

# Copy environment template
cp .env.example .env

# Start Dagster UI
make dev
# Open http://localhost:3000
```

If you prefer to run the underlying commands directly, `make install` is
equivalent to `uv sync --extra stack-dev`, and `make dev` runs:

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

The equivalent Make target is `make neo4j-up`. Container profiles and lifecycle commands belong in
the [Docker guide](../development/docker.md).

## First Steps

1. **Materialize assets** - In Dagster UI, materialize `raw_sbir_awards`
2. **View data** - Check Neo4j Browser at <http://localhost:7474>
3. **Run tests** - `uv run pytest tests/unit/ -v`

## Development Workflow

```bash
make test-unit
make check
```

## Common Issues

- **Neo4j connection failed**: Check `.env` credentials
- **Import errors**: Run `make install` (or `uv sync --extra stack-dev`) to update the full stack
- **Memory issues**: Reduce `SBIR_ETL__ENRICHMENT__PERFORMANCE__CHUNK_SIZE`; confirm the setting in
  the [configuration reference](../configuration.md) before adding another override

## Next Steps

- [Docker Setup](../development/docker.md) - Container-based development
- [Deployment Guide](../deployment/README.md) - Mac mini and local deployment
- [Testing Guide](../testing/index.md) - Running tests
- [Configuration](../configuration.md) - YAML configuration
