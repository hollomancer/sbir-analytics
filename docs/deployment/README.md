---
Type: Overview
Owner: docs@project
Last-Reviewed: 2025-12-01
Status: active
---

# Deployment Documentation

This directory contains deployment documentation for the SBIR ETL project.

## Deployment Overview

The SBIR ETL project uses GitHub Actions for orchestration with AWS infrastructure:

1. **GitHub Actions (Primary)** - Orchestrates all ETL pipelines via `dagster job execute`
2. **AWS Batch** - Heavy compute jobs (ML, fiscal analysis)
3. **AWS Lambda + Step Functions** - Data download workflows
4. **Docker (Development)** - Local development and testing

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ ETL Pipeline│  │Data Refresh │  │  ML Jobs    │         │
│  │   (weekly)  │  │  (scheduled)│  │ (on-demand) │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
└─────────┼────────────────┼────────────────┼─────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────┐
│                         AWS                                  │
│  ┌─────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   S3    │  │Step Functions│  │  AWS Batch  │             │
│  │ (data)  │  │ (downloads)  │  │ (heavy ML)  │             │
│  └─────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────┐
│                     Neo4j Aura                               │
│                   (Graph Database)                           │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Run ETL Pipeline Manually

1. Go to **Actions** → **ETL Pipeline** → **Run workflow**
2. Select job: `sbir_weekly_refresh`, `usaspending_ingestion`, `uspto_pipeline`, etc.
3. Click **Run workflow**

### Scheduled Runs

| Workflow | Schedule | Description |
|----------|----------|-------------|
| ETL Pipeline | Monday 10 AM UTC | Full weekly pipeline |
| Data Refresh (SBIR) | Monday 9 AM UTC | Download fresh SBIR data |
| Data Refresh (USAspending) | 6th of month | Download USAspending dump |
| Data Refresh (USPTO) | 1st of month | Download USPTO patents |

## Deployment Guides

| Guide | Description |
|-------|-------------|
| [AWS Deployment](aws-deployment.md) | Lambda, Step Functions, S3 setup |
| [AWS Batch Jobs](aws-batch-analysis-jobs.md) | Heavy ML/fiscal analysis jobs |
| [Docker](docker.md) | Local development setup |
| [Neo4j Runbook](neo4j-runbook.md) | Neo4j Aura operations |
| [GitHub Actions ML](github-actions-ml.md) | ML job configuration |

## Required Secrets

Set these in GitHub → Settings → Secrets:

| Secret | Description |
|--------|-------------|
| `AWS_ROLE_ARN` | IAM role for AWS access |
| `NEO4J_URI` | Neo4j Aura connection URI |
| `NEO4J_USER` | Neo4j username |
| `NEO4J_PASSWORD` | Neo4j password |

## Local Development

```bash
# Start local Neo4j
make neo4j-up

# Run Dagster UI
uv run dagster dev

# Run specific job
uv run dagster job execute -m src.definitions -j sbir_weekly_refresh_job
```

See [Docker Guide](docker.md) for full local setup.
