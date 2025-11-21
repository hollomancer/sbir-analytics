# Lambda Functions

This directory contains Lambda functions for the SBIR ETL pipeline.

## Function Structure

Each function is in its own directory:
- `scripts/lambda/{function-name}/lambda_handler.py`

## Functions

### Layer-based Functions (Lightweight)

- **download-csv**: Downloads CSV from SBIR.gov and uploads to S3
- **validate-dataset**: Validates CSV schema and computes hash
- **profile-inputs**: Profiles awards and company CSVs
- **enrichment-checks**: Runs enrichment coverage analysis
- **reset-neo4j**: Resets Neo4j database
- **smoke-checks**: Runs Neo4j smoke checks

### Container-based Functions (Migrated to Dagster Cloud)

**DEPRECATED**: The following functions have been migrated to Dagster Cloud:
- ~~**ingestion-checks**~~ → Now part of `sbir_weekly_refresh_job` in Dagster Cloud
- ~~**load-neo4j**~~ → Now part of `sbir_weekly_refresh_job` in Dagster Cloud

**Replacement**: Use the `trigger-dagster-refresh` Lambda function to trigger the `sbir_weekly_refresh_job` in Dagster Cloud.

### New Functions

- **trigger-dagster-refresh**: Triggers Dagster Cloud jobs via API (replaces container-based functions)

## Building

### Lambda Layer

```bash
./build_layer.sh
```

### Container Images

**DEPRECATED**: Container-based Lambda functions have been migrated to Dagster Cloud. The `build_containers.sh` script is deprecated and will exit with an error if run.

See [Lambda to Dagster Migration](../../docs/deployment/lambda-to-dagster-migration.md) for details.

## Testing

See [`docs/deployment/aws-serverless-deployment-guide.md`](../../docs/deployment/aws-serverless-deployment-guide.md) for deployment and testing guidelines.

## Deployment

### Automatic Deployment (Recommended)

Functions are automatically deployed when changes are pushed to `main` or `master` branch. The GitHub Actions workflow (`.github/workflows/lambda-deploy.yml`) will:

1. **Detect changes** in Lambda code or CDK infrastructure
2. **Build and publish Lambda layer** (if layer functions or dependencies changed)
3. **Deploy via CDK** to update all Lambda functions

**Note**: Container-based functions have been migrated to Dagster Cloud. No container builds are needed.

The workflow triggers on:
- Push to `main`/`master` with changes to:
  - `lambda/**`
  - `scripts/lambda/**`
  - `infrastructure/cdk/**`
- Manual trigger via GitHub Actions UI (with optional flags)

### Manual Deployment

If you need to deploy manually:

```bash
# 1. Build and publish Lambda layer (if dependencies changed)
./scripts/lambda/build_layer.sh
aws lambda publish-layer-version \
  --layer-name sbir-analytics-python-dependencies \
  --zip-file fileb:///tmp/python-dependencies-layer.zip \
  --compatible-runtimes python3.11

# 2. Deploy via CDK
cd infrastructure/cdk
uv sync
cdk deploy sbir-analytics-lambda
```

**Note**: Container-based functions have been migrated to Dagster Cloud. No container builds are needed.

### Updating Individual Function Code (Quick Update)

For quick code-only updates without rebuilding layers:

```bash
# Package function
cd scripts/lambda/download_csv
zip -r function.zip lambda_handler.py

# Update function code
aws lambda update-function-code \
  --function-name sbir-analytics-download-csv \
  --zip-file fileb://function.zip \
  --region us-east-2
```

**Note:** This only updates the function code, not dependencies. For dependency changes, use CDK deployment.

