---
Type: Overview
Owner: docs@project
Last-Reviewed: 2026-08-04
Status: active
---

# Deployment

This page routes readers to the one current deployment runbook. The repository is a personal
research project, not production software; these notes preserve repeatable operations without
implying a production-grade service.

> **Operational data caveat.** No SBIR/STTR award data is committed to this repository. Local-development commands in these docs are intended to bring up services, run tests, or exercise pipeline components against small/local inputs after you provide `.env` values. Full dataset reproduction requires downloading the source/bulk datasets yourself, supplying the relevant API credentials, and running supporting services such as Neo4j; reproducing the analyses end-to-end is non-trivial setup, not a one-command deployment.

## Choose a path

| Goal | Use |
|------|-----|
| Run the pipeline locally, iterate on code | [Docker guide](../development/docker.md) — `make docker-up-dev` |
| Run a one-off job without Docker | [Getting started](../getting-started/README.md) — `make dev` + Dagster UI |
| Private always-on server (tailnet-only) | [Self-hosted server](self-hosted-server.md) — `make server-up` |
| Scheduled runs or live-state operations | [Self-hosted server runbook](self-hosted-server.md) |
| Heavy ML or fiscal jobs | [Heavy assets](self-hosted-server.md#heavy-assets); run manually and measure first |

## Current boundary

Everything runs on one always-on self-hosted server; GitHub Actions is CI only.

1. **Self-hosted server (Dagster)** — source downloads, ETL pipelines, and Neo4j
2. **GitHub Actions** — lint, typecheck, tests. No data plane, no scheduled work, no image publishing.
3. **Docker (development)** — local development and testing

The AWS data plane (S3, Batch, Lambda, and Step Functions) is retired. Scheduled workloads have
moved off GitHub Actions. The remaining account-level teardown checklist is tracked in the
[AWS decommission plan](aws-decommission-plan.md); the completed Actions migration plan is
[archived](../archive/deployment/actions-migration-plan.md).

## Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions (CI only)                  │
│          lint · typecheck · tests (Neo4j containers)         │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│          Self-hosted server — tailnet-only, always on        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │  downloads   │─▶│  pipelines   │─▶│    Neo4j     │       │
│  │ (schedules)  │  │  (sensors)   │  │              │       │
│  └──────────────┘  └──────────────┘  └──────┬───────┘       │
│         │                                                   │
│         ▼                                                   │
│       persistent application data                            │
└─────────────────────────────────────────────────────────────┘
```

## Canonical references

| Guide | Description |
|-------|-------------|
| [Self-hosted server runbook](self-hosted-server.md) | Live checkout, services, schedules, backups, and recovery |
| [Docker development](../development/docker.md) | Local Compose profiles and troubleshooting |
| [Neo4j migrations](../migrations.md) | Versioned graph schema and data migrations |
| [AWS decommission plan](aws-decommission-plan.md) | Remaining external teardown only |

## Live credentials

Server credentials live in `.env.server` on the server host (see the
[self-hosted server runbook](self-hosted-server.md)), not in GitHub secrets:

| Variable | Description |
|----------|-------------|
| `NEO4J_PASSWORD` | Neo4j password for the server profile |
| `SAM_GOV_API_KEY` | SAM.gov API key (expires roughly every 60 days) |
| `USPTO_ODP_API_KEY` | USPTO ODP key, required for PatentsView downloads |

Do not copy live credentials into the development checkout or GitHub Actions. For local setup and
commands, use the [getting-started guide](../getting-started/README.md).
