# AWS Infrastructure Rebuild Design

**Date:** 2026-04-18
**Status:** Approved
**Account:** `161066624831` (us-east-2)

## Context

The original CDK codebase (`infrastructure/cdk/`) described infrastructure for the wrong AWS account (`658445659195`) and was never deployed. It accumulated prototype cruft: Lambda and Step Functions roles that were never used, dual create/import code paths, and ECR policies for images that actually live on GHCR.

This design starts clean: full rewrite of the CDK stacks, two stacks instead of three, no dead code.

## What the App Actually Needs

- **S3** — central data store for raw, validated, enriched, and artifact data across all pipeline stages
- **GitHub Actions OIDC role** — all six workflows authenticate via OIDC (`${{ secrets.AWS_ROLE_ARN }}`) for S3 access and Batch job submission
- **AWS Batch (Fargate)** — USAspending extract requires 30GB RAM and 200GB ephemeral storage, exceeding any hosted runner. ML jobs (CET, fiscal, PAECTER) also defined here for Spot pricing and retry logic.
- **Secrets Manager** — one secret (`sbir-analytics/neo4j`) for Neo4j credentials inside Batch job containers
- **No ECR** — images are published to GHCR (`ghcr.io/hollomancer/sbir-analytics-full:latest`)
- **No Lambda, no Step Functions** — ETL is fully orchestrated by Dagster + GitHub Actions

## Repository Structure

```
infrastructure/cdk/
  app.py                 # CDK app entry: FoundationStack, then BatchStack
  stacks/
    __init__.py
    config.py            # All constants (bucket name, role names, job names)
    foundation.py        # S3 bucket + GitHub Actions OIDC role + Secrets Manager ref
    batch.py             # Fargate compute, job queue, 4 job definitions, SNS
```

Old files deleted: `storage.py`, `security.py`, `batch_stack.py`

## Stack 1: FoundationStack

### S3 Bucket

- Name: `sbir-etl-prod-data`
- Versioning: enabled
- Encryption: S3-managed
- Public access: blocked
- Removal policy: `RETAIN` (data survives stack deletion)

Lifecycle rules:

| Prefix | Action | After |
|--------|--------|-------|
| `raw/` | Expire | 30 days |
| `artifacts/` | Expire | 90 days |
| `raw/usaspending/database/` | Transition to Glacier Instant Retrieval | 30 days |
| `raw/usaspending/database/` | Expire | 365 days |
| `validated/` | Expire | 180 days |
| `enriched/` | Expire | 365 days |

### GitHub Actions OIDC Role

- Name: `sbir-analytics-github-actions`
- Trust: `token.actions.githubusercontent.com`, audience `sts.amazonaws.com`, subject `repo:hollomancer/sbir-analytics:*`
- Policies (least-privilege):
  - S3: `GetObject`, `PutObject`, `DeleteObject`, `ListBucket` on `sbir-etl-prod-data`
  - Batch: `SubmitJob`, `DescribeJobs`, `ListJobs`, `TerminateJob` on `sbir-analytics-*` job definitions and queues
  - Batch: `RegisterJobDefinition` on `sbir-analytics-*` (needed for CDK deploys)
  - IAM: `PassRole` to `batch.amazonaws.com` for the two Batch IAM roles
  - CloudWatch Logs: `DescribeLogGroups`, `DescribeLogStreams`, `GetLogEvents` (read-only)
  - CloudFormation: full access (for CDK deployments from CI)

### Secrets Manager

Reference only (not created): `Secret.from_secret_name_v2("sbir-analytics/neo4j")`. Exposed as `foundation.neo4j_secret` so `BatchStack` can call `grant_read()`.

## Stack 2: BatchStack

Depends on `FoundationStack` for bucket ARN and Neo4j secret reference.

### IAM Roles

- `sbir-analytics-batch-execution-role` — assumes `ecs-tasks.amazonaws.com`, has `AmazonECSTaskExecutionRolePolicy` (pull images, write logs)
- `sbir-analytics-batch-task-role` — assumes `ecs-tasks.amazonaws.com`, S3 read/write on `sbir-etl-prod-data`, read on `sbir-analytics/neo4j` secret

### Compute Environments

Both use Fargate, default VPC, public subnets, max 8 vCPUs:

- `sbir-analytics-batch-spot` — Fargate Spot (order 1 in queue, preferred)
- `sbir-analytics-batch-on-demand` — Fargate on-demand (order 2, fallback)

### Job Queue

Name: `sbir-analytics-job-queue` — prefers Spot, falls back to on-demand automatically.

### CloudWatch Log Group

Name: `/aws/batch/sbir-analytics`, retention: 90 days. Created by the stack (not imported).

### Job Definitions

All use `ghcr.io/hollomancer/sbir-analytics-full:latest`, retry attempts: 2.

| Job name | vCPU | RAM | Timeout | Ephemeral |
|----------|------|-----|---------|-----------|
| `sbir-analytics-cet-pipeline` | 2 | 4GB | 6h | — |
| `sbir-analytics-fiscal-returns` | 4 | 8GB | 4h | — |
| `sbir-analytics-paecter-embeddings` | 2 | 4GB | 6h | — |
| `sbir-analytics-usaspending-extract` | 4 | 30GB | 8h | 200GB |

CET, fiscal, and PAECTER jobs include environment variables: `DAGSTER_LOAD_HEAVY_ASSETS=true`, `DAGSTER_HOME=/tmp/dagster_home`.

### SNS Notifications

One topic (`sbir-analytics-batch-notifications`) subscribed to `SUCCEEDED`/`FAILED` state changes on the job queue. Optional email subscription via `notification_email` CDK context variable.

## Workflow Impact

**Must do after deployment:**
- Update `AWS_ROLE_ARN` secret in GitHub repository settings to the new role ARN

**No code changes needed** — workflows already reference the correct bucket name (`sbir-etl-prod-data`), region (`us-east-2`), and use `${{ secrets.AWS_ROLE_ARN }}` for authentication.

**Follow-on task (separate):**
- Rewrite `etl-pipeline.yml` USAspending job to submit to Batch via `aws batch submit-job` instead of attempting to run in a GitHub Actions container.

## Deployment Order

```
cdk bootstrap   # if not already done for account 161066624831 / us-east-2
cdk deploy FoundationStack
cdk deploy BatchStack
```

Or in one command: `cdk deploy --all`

After deploy: copy `GitHubActionsRoleArn` output → GitHub secret `AWS_ROLE_ARN`.
