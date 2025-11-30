# Docker Quick Start

Get the SBIR ETL pipeline running in Docker in 5 minutes.

## Prerequisites

- Docker Desktop installed
- Git

## Steps

### 1. Clone and Enter Directory

```bash
git clone https://github.com/hollomancer/sbir-analytics.git
cd sbir-analytics
```

### 2. Create Environment File

```bash
cp .env.example .env
```

### 3. Start Services

```bash
docker-compose --profile dev up -d
```

### 4. Verify

```bash
# Check services are running
docker-compose ps

# Run tests
docker-compose exec app uv run pytest tests/unit/ -v
```

### 5. Access Services

- **Dagster UI**: http://localhost:3000
- **Neo4j Browser**: http://localhost:7474 (neo4j/password)

## Common Tasks

```bash
# View logs
docker-compose logs -f app

# Run specific test
docker-compose exec app uv run pytest tests/unit/test_config.py -v

# Stop everything
docker-compose down
```

## Next Steps

- [Docker Troubleshooting](docker-troubleshooting.md) - If you hit issues
- [Containerization Guide](../deployment/containerization.md) - Full reference
