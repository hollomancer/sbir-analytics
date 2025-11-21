---

Type: Guide
Owner: devops@project
Last-Reviewed: 2025-10-30
Status: active

---

# Containerization and Compose Profiles

**Note**: Docker Compose is now a **failover option** for local development and emergency scenarios. **Dagster Cloud Solo Plan** is the primary deployment method. See [`dagster-cloud-deployment-guide.md`](dagster-cloud-deployment-guide.md) for the production setup.

This guide explains how to build, run, and validate the SBIR ETL stack with Docker. It also documents the consolidated Compose architecture that replaced six fragmented files with a single profile-driven configuration.

## Quick Start

### Step 1: Check Prerequisites

```bash
make docker-check-prerequisites
```

This validates:
- ✅ Docker 20.10+ installed and running
- ✅ Docker Compose V2 available
- ✅ Ports 3000, 7474, 7687 available
- ✅ Sufficient disk space (5GB+)

### Step 2: Configure Environment

```bash
cp .env.example .env
# Edit .env: Set NEO4J_USER and NEO4J_PASSWORD
# For local development, defaults (neo4j/test) work fine
```

**Minimal setup** (local development):
- `NEO4J_USER=neo4j`
- `NEO4J_PASSWORD=test`

**Full setup** (see [Environment Setup Guide](../development/docker-env-setup.md)):
- All variables configured for production-like testing

### Step 3: Build Image

```bash
make docker-build
```

**Expected time:** 10-20 minutes (first build only)
- Builds base images used by development, CI, and production profiles
- Includes R packages for fiscal analysis (takes 5-10 minutes)

### Step 4: Start Services

```bash
make docker-up-dev
```

**Expected time:** 2-3 minutes
- Spins up the `dev` profile with bind mounts for fast iteration
- Services: Neo4j, Dagster webserver, Dagster daemon
- Dagster UI: http://localhost:3000
- Neo4j Browser: http://localhost:7474

### Step 5: Verify Setup

```bash
make docker-verify
```

This checks:
- ✅ Neo4j is accessible
- ✅ Dagster UI is accessible
- ✅ All services are running

### Run Tests in Containers

```bash
make docker-test
```

Executes the CI test profile inside Docker (mirrors `container-ci.yml`).

### Other Useful Targets

```bash
make docker-down        # stop containers
make docker-logs        # tail Dagster / Neo4j logs
make docker-rebuild     # rebuild and restart
make neo4j-check        # check Neo4j health
```

## Troubleshooting

If you encounter issues, see the [Docker Troubleshooting Guide](../development/docker-troubleshooting.md) or check:

- Service logs: `make docker-logs SERVICE=<name>`
- Service status: `docker compose --profile dev ps`
- Common issues: Port conflicts, Docker not running, insufficient disk space

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

For deeper operational runbooks, see `docs/deployment/neo4j-runbook.md` and `docs/performance/index.md`.
