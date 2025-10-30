---
Type: Guide
Owner: devops@project
Last-Reviewed: 2025-10-30
Status: active
---

# Containerization and Environments

This guide consolidates the deployment docs. It explains how to build, run, and test the SBIR ETL pipeline with Docker.

## Prerequisites
- Docker and Docker Compose installed
- `.env` configured (copy from `.env.example`) with `NEO4J_USER` and `NEO4J_PASSWORD`

## Build
```bash
make docker-build
```

## Run (development)
```bash
make docker-up-dev
```
- Binds the local repo into containers for fast iteration.
- Dagster UI: http://localhost:3000
- Neo4j Browser: http://localhost:7474

## Run tests in containers
```bash
make docker-test
```

## Stacks
- `docker/docker-compose.dev.yml`: developer stack
- `docker/docker-compose.test.yml`: test runner
- `docker/docker-compose.e2e.yml`: end-to-end CI stack

## Configuration
Configuration is layered via Pydantic + YAML:
- Base: `config/base.yaml`
- Environment overrides: `config/dev.yaml`, `config/prod.yaml`, `config/envs/*.yaml`

## Neo4j notes
- Neo4j config in `config/neo4j/neo4j.conf`
- Data and logs mounted under `neo4j/`
- Ensure credentials are set in `.env`

## CI references
- Workflows in `.github/workflows/`:
  - `container-ci.yml` for container-based test runs
  - `neo4j-smoke.yml` for integration checks

For architectural details, see `docs/architecture/overview.md`.
