---
Type: Reference
Owner: devops@project
Last-Reviewed: 2025-01-15
Status: active

---

# Dagster Cloud Deployment Overview

Dagster Cloud Solo Plan is the **primary** orchestration surface for SBIR ETL. This overview centralizes the prerequisites, environment variables, and verification steps referenced by the README, Quick Start, and deployment index to keep guidance consistent.

## Prerequisites

- Dagster Cloud Solo Plan account (30-day trial available)
- GitHub repository access for the SBIR ETL code location
- Python 3.11 runtime with `uv` or `pip` for local validation
- Docker (only required for CLI/serverless deployments that build Python executables)
- Neo4j Aura credentials (URI, username, password, optional database name)

## Required Environment Variables

Set these in Dagster Cloud → **Deployments → Code Locations → Environment Variables** (or via variable sets if available):

```text
NEO4J_URI=neo4j+s://<your-instance>.databases.neo4j.io
NEO4J_USER=neo4j
NEO4J_PASSWORD=<your-password>
NEO4J_DATABASE=neo4j
```

Optional overrides (only if you deviate from defaults):

- `SBIR_ETL__PIPELINE__ENVIRONMENT` – `production`, `staging`, etc.
- `SBIR_ETL__PATHS__DATA_ROOT` – custom data directory when using S3 mounts
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` – required if Dagster Cloud needs to access private S3 buckets

## Code Location Defaults

- **Module**: `src.definitions`
- **Python version**: 3.11
- **Entrypoint**: `pyproject.toml` already includes the required `[tool.dagster]` metadata for Dagster Cloud discovery.

## Deployment Checklist

1. Create the Dagster Cloud deployment and link the repository.
2. Configure the code location with the module and branch (`main`).
3. Add the environment variables above.
4. Trigger the initial deploy (Dagster Cloud does this automatically after linking the repo).
5. Validate in the Dagster Cloud UI:
   - **Assets** load without errors.
   - **Jobs** appear under the code location.
   - **Schedules / Sensors** are present (if enabled in `src.definitions`).

## Smoke Test

1. Open Dagster Cloud → **Assets** → select a lightweight asset group (e.g., CET validation).
2. Materialize the assets and confirm the run completes.
3. Download the run logs to verify that Neo4j credentials were injected correctly.

## Related Guides

- [Dagster Cloud Deployment Guide](dagster-cloud-deployment-guide.md) – step-by-step UI + CLI instructions.
- [Containerization Guide](containerization.md) – Docker Compose failover / local testing.
- [README Production Deployment](../../README.md#production-deployment-dagster-cloud) – high-level positioning now linked back to this overview.
