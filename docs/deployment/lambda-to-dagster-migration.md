# Lambda to Dagster Cloud Migration

## Overview

The container-based Lambda functions (`ingestion-checks` and `load-neo4j`) have been migrated to Dagster Cloud to simplify the architecture and better leverage Dagster's orchestration capabilities.

## What Changed

### Removed
- **Container-based Lambda functions**:
  - `ingestion-checks` - Ran SBIR ingestion validation using Dagster assets
  - `load-neo4j` - Loaded validated awards into Neo4j using Dagster assets
- **ECR repository** for Lambda container images
- **Container build steps** in GitHub Actions workflow

### Added
- **Dagster job**: `sbir_weekly_refresh_job` in `src/assets/jobs/sbir_weekly_refresh_job.py`
  - Combines ingestion validation and Neo4j loading into a single job
  - Runs in Dagster Cloud with full observability
- **Simple Lambda function**: `trigger-dagster-refresh`
  - Lightweight function (no containers needed)
  - Triggers Dagster Cloud jobs via API
  - Replaces the container-based functions in Step Functions workflows

## Architecture Changes

### Before
```
Step Functions
  ├── download-csv (Lambda)
  ├── validate-dataset (Lambda)
  ├── profile-inputs (Lambda)
  ├── ingestion-checks (Lambda Container) ❌
  ├── enrichment-checks (Lambda)
  ├── reset-neo4j (Lambda)
  ├── load-neo4j (Lambda Container) ❌
  └── smoke-checks (Lambda)
```

### After
```
Step Functions
  ├── download-csv (Lambda)
  ├── validate-dataset (Lambda)
  ├── profile-inputs (Lambda)
  ├── trigger-dagster-refresh (Lambda) → Dagster Cloud
  │   └── sbir_weekly_refresh_job
  │       ├── raw_sbir_awards
  │       ├── validated_sbir_awards
  │       ├── sbir_validation_report
  │       └── neo4j_sbir_awards
  ├── enrichment-checks (Lambda)
  ├── reset-neo4j (Lambda)
  └── smoke-checks (Lambda)
```

## Benefits

1. **Simplified Infrastructure**
   - No more container builds for Lambda
   - No ECR repository needed
   - Simpler deployment workflow

2. **Better Observability**
   - Full Dagster UI for job execution
   - Better error tracking and retry logic
   - Asset-level monitoring

3. **More Flexible**
   - Can run jobs independently or as part of larger pipelines
   - Easier to test and debug locally
   - Better integration with other Dagster assets

4. **Cost Optimization**
   - No container image storage costs
   - Simpler Lambda functions (layer-based only)
   - Better resource utilization in Dagster Cloud

## Migration Steps

### 1. Update Step Functions State Machine

The state machine has been updated to use `trigger-dagster-refresh` instead of `ingestion-checks` and `load-neo4j`:

```json
{
  "TriggerDagsterRefresh": {
    "Type": "Task",
    "Resource": "${lambda.trigger-dagster-refresh.arn}",
    "Comment": "Triggers sbir_weekly_refresh_job in Dagster Cloud",
    "Next": "EnrichmentChecks"
  }
}
```

### 2. Configure Dagster Cloud API Token

Store the Dagster Cloud API token in AWS Secrets Manager:

```bash
aws secretsmanager create-secret \
  --name sbir-analytics/dagster-cloud-api-token \
  --secret-string '{"dagster_cloud_api_token": "your-token-here"}'
```

### 3. Deploy Updated Lambda Function

The `trigger-dagster-refresh` function will be deployed automatically via CDK. Ensure it has:
- Access to Secrets Manager (for API token)
- Environment variables:
  - `DAGSTER_CLOUD_ORG` (or pass in event)
  - `DAGSTER_CLOUD_DEPLOYMENT` (defaults to "prod")
  - `DAGSTER_CLOUD_SECRET_NAME` (defaults to "sbir-analytics/dagster-cloud-api-token")

### 4. Update Step Functions Input

The `trigger-dagster-refresh` Lambda expects:

```json
{
  "dagster_cloud_org": "your-org",
  "dagster_cloud_deployment": "prod",
  "job_name": "sbir_weekly_refresh_job",
  "run_config": {
    "ops": {
      "raw_sbir_awards": {
        "config": {
          "csv_path": "s3://bucket/raw/awards/2025-01-15/award_data.csv"
        }
      }
    }
  }
}
```

## Rollback

If you need to rollback to the container-based approach:

1. Restore the container build steps in `.github/workflows/lambda-deploy.yml`
2. Restore the container function definitions in `infrastructure/cdk/stacks/lambda_stack.py`
3. Restore the ECR repository creation
4. Update Step Functions state machine to use the original Lambda functions

## References

- Dagster job: `src/assets/jobs/sbir_weekly_refresh_job.py`
- Lambda function: `scripts/lambda/trigger_dagster_refresh/lambda_handler.py`
- Dagster Cloud API: https://docs.dagster.io/deployment/dagster-plus/api

