---

Type: Guide
Owner: devops@project
Last-Reviewed: 2025-10-30
Status: active

---

# Containerization and Compose Profiles

**Note**: Docker Compose is now a **failover option** for local development and emergency scenarios. **Dagster Cloud Solo Plan** is the primary deployment method. See `docs/deployment/dagster-cloud-migration.md` for production deployment setup.

This guide explains how to build, run, and validate the SBIR ETL stack with Docker. It also documents the consolidated Compose architecture that replaced six fragmented files with a single profile-driven configuration.

## Quick Start

### Prerequisites

- Docker Desktop or Docker Engine + Compose V2
- `.env` created from `.env.example` with `NEO4J_USER` / `NEO4J_PASSWORD`
- Optional: `COMPOSE_PROFILES` set for your preferred default profile

### Build

```bash
make docker-build
```

Creates the base images used by development, CI, and production profiles.

### Run (development)

```bash
make docker-up-dev
```

- Spins up the `dev` profile with bind mounts for fast iteration
- Dagster UI: http://localhost:3000
- Neo4j Browser: http://localhost:7474

### Run tests in containers

```bash
make docker-test
```

Executes the CI test profile inside Docker (mirrors `container-ci.yml`).

### Other useful targets

```bash
make docker-down        # stop containers
make docker-logs        # tail Dagster / Neo4j logs
make docker-clean       # remove containers and volumes
```

## Profiles at a Glance

| Profile | Use Case | Key Features |
|---------|----------|--------------|
| `dev` | Local development | Bind mounts, live reload, debug logging, persistent Neo4j data |
| `ci` | CI/testing environment | Ephemeral volumes, test execution, E2E test support |

Select profiles via `COMPOSE_PROFILES` or the `--profile` flag:

```bash
docker compose --profile dev up --build    # Development
docker compose --profile ci up --build     # CI Testing
```

## Configuration Layering

- Base settings: `config/base.yaml`
- Environment overlays: `config/dev.yaml`, `config/prod.yaml`, `config/envs/*.yaml`
- Runtime overrides: `SBIR_ETL__...` environment variables (preferred for secrets)
- Neo4j runtime: `config/neo4j/neo4j.conf`

## Consolidated Compose Architecture

The project previously kept six Compose files (`docker-compose.yml`, `docker-compose.cet-staging.yml`, `docker/docker-compose.dev.yml`, etc.). These were merged into a single `docker-compose.yml` with profile blocks and YAML anchors.

### Benefits

- **60% fewer lines** of Compose configuration
- **One source of truth** for services, volumes, and networks
- **Consistent environment variables** via the `SBIR_ETL__` prefix
- **Shared health checks and resource limits** across profiles

### Profile Example

```yaml
services:
  neo4j:
    profiles: [ci, dev]
    environment: *common-environment
    volumes:
      - neo4j_data:/data
      - neo4j_logs:/logs
      - neo4j_import:/var/lib/neo4j/import
```

### Shared Anchors

```yaml
x-common-environment: &common-environment
  ENVIRONMENT: ${ENVIRONMENT:-dev}
  PYTHONPATH: /app
  SBIR_ETL__NEO4J__HOST: ${SBIR_ETL__NEO4J__HOST:-neo4j}

x-common-volumes: &common-volumes

  - reports:/app/reports
  - logs:/app/logs
  - data:/app/data
```

## Migration & Tooling

Use `scripts/docker/migrate_compose_configs.py` to validate or regenerate the consolidated file:

```bash
python scripts/docker/migrate_compose_configs.py --validate
python scripts/docker/migrate_compose_configs.py --test-profiles
python scripts/docker/migrate_compose_configs.py --backup --migrate
```

A companion shell helper (`scripts/docker/validate_consolidated_compose.sh`) lint-checks profile combinations.

## CI Integration

- `container-ci.yml` – Executes the `ci-test` profile inside GitHub Actions
- `neo4j-smoke.yml` – Spins up Neo4j via Compose and runs smoke checks
- `performance-regression-check.yml` – Uses Compose images for benchmark comparisons

For deeper operational runbooks, see `docs/neo4j/server.md` and `docs/performance/index.md`.
