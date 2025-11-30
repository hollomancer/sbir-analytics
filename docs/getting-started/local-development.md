# Local Development Setup

Complete guide for setting up the SBIR ETL pipeline locally.

## Prerequisites

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) for dependency management
- Docker (optional, for local Neo4j)

## Installation

```bash
# Clone repository
git clone https://github.com/hollomancer/sbir-analytics
cd sbir-analytics

# Install dependencies
uv sync

# Copy environment template
cp .env.example .env
```

## Neo4j Setup

### Option 1: Neo4j Aura (Recommended)

1. Create free instance at [neo4j.com/aura](https://neo4j.com/product/auradb/)
2. Copy connection URI and credentials to `.env`

### Option 2: Local Docker

```bash
make neo4j-up
# Access at http://localhost:7474 (neo4j/password)
```

## Running the Pipeline

```bash
# Start Dagster UI
uv run dagster dev

# Open http://localhost:3000
# Materialize raw_sbir_awards asset
```

## Development Workflow

```bash
# Run tests
uv run pytest

# Code quality
uv run ruff check .
uv run mypy src/

# Format code
uv run ruff format .
```

## Common Issues

- **Neo4j connection failed**: Check `.env` credentials
- **Import errors**: Run `uv sync` to update dependencies
- **Memory issues**: Reduce `SBIR_ETL__PIPELINE__CHUNK_SIZE`

## Next Steps

- [Docker Setup](../development/docker.md)
- [Testing Guide](../testing/index.md)
- [Configuration](../configuration.md)
