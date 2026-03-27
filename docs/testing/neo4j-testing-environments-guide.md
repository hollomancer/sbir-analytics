# Neo4j Testing Environments Guide

This guide explains how to set up and use Neo4j with Docker for testing the SBIR ETL pipeline.

## Table of Contents

1. [Overview](#1-overview)
2. [Docker Test Setup](#2-docker-test-setup)
    * [Docker Compose Profiles](#docker-compose-profiles)
    * [GitHub Actions CI](#github-actions-ci)
3. [Recommended Testing Strategy](#3-recommended-testing-strategy)
4. [Troubleshooting](#4-troubleshooting)
5. [Additional Resources](#5-additional-resources)

---

## 1. Overview

All Neo4j testing uses **Docker** — locally with Docker Compose and in CI via the `.github/actions/start-neo4j` action. There is no cloud dependency.

## 2. Docker Test Setup

### Docker Compose Profiles

The project has **two Docker profiles**:

#### 1. `dev` Profile (Development)

```bash
docker compose --profile dev up
```

**Services:**
* `neo4j`: Local Neo4j instance (no limits)
* `dagster-webserver`: Dagster UI for development
* `dagster-daemon`: Background scheduler
* `etl-runner`: Interactive runner for pipeline

**Neo4j Config:**
* Ports: `7687` (Bolt), `7474` (HTTP)
* Auth: `NEO4J_USER=neo4j`, `NEO4J_PASSWORD` from `.env`
* Volumes: Persistent (`neo4j_data`, `neo4j_logs`)
* Memory: 1GB heap, 256MB pagecache
* Plugins: APOC

**Best For:**
* Local development with full dataset
* Running Dagster UI for debugging
* Long-running development sessions

#### 2. `ci` Profile (CI/CD Testing)

```bash
docker compose --profile ci up
```

**Services:**
* `neo4j`: Test database (ephemeral)
* `app`: Test runner container
* Runs `pytest -m fast` automatically

**Neo4j Config:**
* Same as dev, but ephemeral
* Destroyed after test run
* Fresh instance each time

**Best For:**
* CI/CD pipeline testing
* Automated test runs
* Clean-room testing

### GitHub Actions CI

**Current CI Flow (.github/workflows/ci.yml):**

```yaml
services:
  neo4j:
    image: neo4j:5
    env:
      NEO4J_AUTH: none  # No password for CI
      NEO4J_ACCEPT_LICENSE_AGREEMENT: "yes"
```

**Steps:**

1. Spin up Neo4j service container
2. Wait for Neo4j to be ready
3. Install Python dependencies via uv (`uv sync`)
4. Run `pytest -m fast` (unit + fast integration tests)
5. Generate coverage report

**Tests Run in CI:**
* Unit tests (mocked, no real Neo4j needed)
* Fast integration tests (real Neo4j, small datasets)
* E2E tests: run via `e2e-docker` job using `.github/actions/start-neo4j`

## 3. Recommended Testing Strategy

### Tier 1: Fast Tests (< 5 min, < 5K awards)

**Use:** Docker (dev profile or `start-neo4j` action in CI)

```bash
# Local
docker compose --profile dev up neo4j -d
pytest -m fast

# CI: handled automatically via start-neo4j action
```

### Tier 2: Integration Tests (5-30 min, 10-50K awards)

**Use:** Docker (dev profile)

```bash
docker compose --profile dev up neo4j -d
pytest -m integration
```

### Tier 3: Nightly/Weekly Tests (1+ hour, full dataset)

**Use:** Docker (dev profile or EC2)

```bash
docker compose --profile dev up -d
python scripts/run_pipeline.py  # Full dataset
```

## 4. Troubleshooting

### Docker Specific Issues

#### Neo4j container fails to start

```bash
# Check container status
docker compose --profile dev ps

# View logs
docker logs $(docker ps --filter "name=sbir-neo4j" --format "{{.Names}}" | head -1)

# Common fix: remove stale volumes
docker compose --profile dev down -v
docker compose --profile dev up neo4j -d
```

#### Connection refused on port 7687

```bash
# Wait for Neo4j to finish starting (can take 30-60s)
until nc -z localhost 7687; do sleep 2; done
echo "Neo4j ready"
```

#### Out of memory errors

```bash
# Increase heap in docker-compose.yml
NEO4J_server_memory_heap_max__size=2G
```

## 5. Additional Resources

* **Neo4j Cypher Manual:** <https://neo4j.com/docs/cypher-manual/current/introduction/>
* **SBIR ETL Issues:** <https://github.com/hollomancer/sbir-analytics/issues>
* **Configuration schema:** [sbir_etl/config/](../../sbir_etl/config/)
* **Environment examples:** [.env.example](../../.env.example)
