---
Type: Overview
Owner: docs@project
Last-Reviewed: 2025-12-01
Status: active
---

# Deployment Documentation

This directory documents the deployment path for the SBIR ETL project. The repository is a personal research project, not production software; these notes preserve useful operational details for repeatable runs without implying a production-grade service.

> **Operational data caveat.** No SBIR/STTR award data is committed to this repository. Local-development commands in these docs are intended to bring up services, run tests, or exercise pipeline components against small/local inputs after you provide `.env` values. Full dataset reproduction requires downloading the source/bulk datasets yourself, supplying the relevant API credentials, and running supporting services such as Neo4j; reproducing the analyses end-to-end is non-trivial setup, not a one-command deployment.

## Choose your path

| Goal | Use |
|------|-----|
| Run the pipeline locally, iterate on code | [Docker guide](../development/docker.md) — `make docker-up-dev` |
| Run a one-off job without Docker | [Getting started](../getting-started/README.md) — `make dev` + Dagster UI |
| Private always-on server on a Mac mini (tailnet-only) | [Mac mini server](mac-mini-server.md) — `make server-up` |
| Scheduled/automated runs | Dagster schedules on the Mac mini — see [Mac mini server](mac-mini-server.md) |
| Heavy ML or fiscal jobs that need more RAM | Run on the Mac mini with `DAGSTER_LOAD_HEAVY_ASSETS=true` |

## Deployment Overview

Everything runs on one always-on Mac mini; GitHub Actions is CI only.

1. **Mac mini (Dagster)** — source downloads, ETL pipelines, Neo4j, the read-only API
2. **GitHub Actions** — lint, typecheck, tests, container image builds. No data plane.
3. **Docker (development)** — local development and testing

The AWS data plane (S3, Batch, Lambda, Step Functions) was retired; see the
[AWS decommission plan](aws-decommission-plan.md).

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions (CI only)                  │
│     lint · typecheck · tests (Neo4j containers) · images     │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│              Mac mini — tailnet-only, always on              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  downloads   │─▶│  pipelines   │─▶│    Neo4j     │       │
│  │ (schedules)  │  │  (sensors)   │  │              │       │
│  └──────────────┘  └──────────────┘  └──────┬───────┘       │
│         │                                    ▼              │
│         ▼                            ┌──────────────┐       │
│  /Volumes/SSDmini/sbir-analytics     │ analytics API│       │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Run a job manually

```bash
# From the deployment checkout on the mini
uv run dagster job execute -m sbir_analytics.definitions -j sbir_awards_download_job
```

Or use the Dagster UI over Tailscale — see [Mac mini server](mac-mini-server.md).

### Scheduled runs

All schedules default to **STOPPED**; enable each only after a manual run
succeeds on the host. See
[Source-data downloads](mac-mini-server.md#source-data-downloads).

| Schedule | Cron (UTC) | Description |
|----------|-----------|-------------|
| `weekly_sbir_awards_download` | Mon 09:00 | Download fresh SBIR data |
| `monthly_sam_gov_download` | 15th 03:00 | Download SAM.gov entities |
| `monthly_usaspending_download` | 6th 02:00 | Download USAspending dump |
| `monthly_uspto_download` | 1st 09:00 | Download USPTO patents |

Pipelines are chained onto downloads by run-status sensors rather than their
own crons, so they run only when there is fresh input.

## Deployment Guides

| Guide | Description |
|-------|-------------|
| [Mac mini server](mac-mini-server.md) | Tailnet-only always-on deployment |
| [AWS decommission plan](aws-decommission-plan.md) | Retiring the AWS data plane |
| [Docker](../development/docker.md) | Local development setup |
| [Neo4j Runbook](neo4j-runbook.md) | Neo4j operations |

## Credentials

Server credentials live in `.env.server` on the mini (see
[Mac mini server](mac-mini-server.md)), not in GitHub secrets:

| Variable | Description |
|----------|-------------|
| `NEO4J_PASSWORD` | Neo4j password for the server profile |
| `SBIR_ANALYTICS_API_TOKEN` | Bearer token for the read-only API |
| `SAM_GOV_API_KEY` | SAM.gov API key (expires roughly every 60 days) |
| `USPTO_ODP_API_KEY` | USPTO ODP key, required for PatentsView downloads |

## Local Development

```bash
# Start local Neo4j
make neo4j-up

# Run Dagster UI
uv run dagster dev

# Run specific job
uv run dagster job execute -m sbir_analytics.definitions -j sbir_weekly_refresh_job
```

See [Docker Guide](../development/docker.md) for full local setup.
