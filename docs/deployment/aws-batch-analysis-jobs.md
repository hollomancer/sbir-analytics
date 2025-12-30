# AWS Batch Analysis Jobs

Heavy analysis jobs (fiscal returns) run on AWS Batch due to memory requirements (8GB+).

## Architecture

```text
GitHub Actions (trigger)
    │
    ▼
AWS Batch Job Queue
    │
    ▼
Fargate Compute (8GB RAM)
    │
    ├── Image: ghcr.io/hollomancer/sbir-analytics-full:latest
    ├── Job: fiscal_returns_mvp_job
    └── Output: S3 + Neo4j
```

## Jobs

| Job | Memory | Description |
|-----|--------|-------------|
| `fiscal_returns_mvp` | 8GB | R/StateIO economic impact analysis |

Note: CET and PaECTER now run on GitHub Actions (free tier).

## Running Jobs

### Via GitHub Actions (recommended)

1. Go to Actions → "Analysis Jobs"
2. Select `fiscal_returns_mvp`
3. Click "Run workflow"

### Via AWS CLI

```bash
aws batch submit-job \
  --job-name "fiscal-returns-$(date +%Y%m%d)" \
  --job-queue "sbir-analytics-analysis-queue" \
  --job-definition "sbir-analytics-analysis-fiscal-returns"
```

## Infrastructure

Managed via CDK in `infrastructure/cdk/stacks/batch_stack.py`:

- Fargate compute environment
- Job queue: `sbir-analytics-analysis-queue`
- Job definition: `sbir-analytics-analysis-fiscal-returns`

## Image

The `sbir-analytics-full` image includes:

- Python 3.11 + all ETL dependencies
- R + StateIO for fiscal analysis
- Built automatically via `build-images.yml`

## Costs

- Fargate: ~$0.10-0.20 per job run
- S3: Minimal (results storage)
- No ECR costs (using GHCR)
