# AWS Infrastructure Guide

This guide covers the AWS infrastructure setup for the SBIR ETL pipeline using Step Functions and Lambda.

## Architecture Overview

The weekly SBIR awards refresh workflow has been migrated from GitHub Actions to AWS Step Functions orchestration with Lambda functions:

- **GitHub Actions**: Thin wrapper that invokes Step Functions
- **Step Functions**: Orchestrates the workflow
- **Lambda Functions**: Execute individual processing steps
- **S3**: Stores data and artifacts
- **Secrets Manager**: Stores Neo4j and GitHub credentials

## Prerequisites

1. AWS Account with appropriate permissions
2. AWS CLI configured
3. AWS CDK installed (`npm install -g aws-cdk`)
4. Docker (for building container images)
5. Python 3.11+

## Infrastructure Components

### S3 Bucket

- **Name**: `sbir-etl-production-data`
- **Region**: `us-east-2`
- **Structure**:
  - `raw/awards/` - Downloaded CSV files (30-day retention)
  - `processed/` - Processed data and validation artifacts
  - `artifacts/` - Metadata and reports (90-day retention)

### Secrets Manager

- **Secret Name**: `sbir-etl/neo4j-aura`
- **Structure**:
  ```json
  {
    "uri": "neo4j+s://...",
    "username": "...",
    "password": "...",
    "database": "neo4j"
  }
  ```

- **GitHub Token Secret**: `sbir-etl/github-token`
  ```json
  {
    "token": "ghp_..."
  }
  ```

### IAM Roles

1. **Lambda Execution Role** (`sbir-etl-lambda-role`)
   - S3 read/write permissions
   - Secrets Manager read permissions
   - CloudWatch Logs write permissions

2. **Step Functions Execution Role** (`sbir-etl-sf-role`)
   - Lambda invoke permissions
   - CloudWatch Logs write permissions

3. **GitHub Actions OIDC Role** (`sbir-etl-github-actions`)
   - Step Functions start execution permission
   - CloudWatch Logs read permission

## Deployment Steps

### 1. Deploy Infrastructure with CDK

```bash
cd infrastructure/cdk

# Install CDK dependencies using uv
uv sync

# Bootstrap CDK (first time only)
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
cdk bootstrap aws://$AWS_ACCOUNT_ID/us-east-2

# Deploy all stacks
cdk deploy --all
```

### 2. Create Secrets

```bash
# Neo4j Aura credentials
aws secretsmanager create-secret \
  --name sbir-etl/neo4j-aura \
  --secret-string '{
    "uri": "neo4j+s://...",
    "username": "neo4j",
    "password": "...",
    "database": "neo4j"
  }' \
  --region us-east-2

# GitHub token
aws secretsmanager create-secret \
  --name sbir-etl/github-token \
  --secret-string '{
    "token": "ghp_..."
  }' \
  --region us-east-2
```

### 3. Build and Deploy Lambda Layer

```bash
# Build layer
./scripts/lambda/build_layer.sh

# Upload layer
aws lambda publish-layer-version \
  --layer-name sbir-etl-python-dependencies \
  --zip-file fileb:///tmp/python-dependencies-layer.zip \
  --compatible-runtimes python3.11 \
  --region us-east-2
```

### 4. Build and Push Container Images

```bash
# Set AWS account ID
export AWS_ACCOUNT_ID=123456789012

# Build and push containers
./scripts/lambda/build_containers.sh
```

### 5. Deploy Lambda Functions

The Lambda functions are deployed automatically via CDK. If you need to update them manually:

```bash
# Package and deploy each function
cd scripts/lambda/download_csv
zip -r function.zip lambda_handler.py
aws lambda update-function-code \
  --function-name sbir-etl-download-csv \
  --zip-file fileb://function.zip \
  --region us-east-2
```

### 6. Configure GitHub Actions

Add the following secrets to your GitHub repository:

- `AWS_ROLE_ARN`: ARN of the GitHub Actions OIDC role
- `STEP_FUNCTIONS_STATE_MACHINE_ARN`: ARN of the Step Functions state machine

## Lambda Functions

### Layer-based Functions (Lightweight)

- `download-csv`: Downloads CSV from SBIR.gov
- `validate-dataset`: Validates CSV schema and computes hash
- `profile-inputs`: Profiles awards and company CSVs
- `enrichment-checks`: Runs enrichment coverage analysis
- `reset-neo4j`: Resets Neo4j database
- `smoke-checks`: Runs Neo4j smoke checks
- `create-pr`: Creates GitHub PR with results

### Container-based Functions (Dagster-dependent)

- `ingestion-checks`: Runs SBIR ingestion validation using Dagster assets
- `load-neo4j`: Loads validated awards into Neo4j using Dagster assets

## Step Functions State Machine

The state machine orchestrates the workflow:

1. **DownloadCSV** → Downloads CSV and uploads to S3
2. **CheckChanges** → Checks if data changed (or force refresh)
3. **ProcessPipeline** → Parallel execution:
   - ValidateDataset
   - ProfileInputs
4. **IngestionChecks** → Runs Dagster ingestion validation
5. **EnrichmentChecks** → Runs enrichment coverage
6. **ResetNeo4j** → Resets database (optional)
7. **LoadNeo4j** → Loads data into Neo4j
8. **SmokeChecks** → Validates Neo4j data
9. **CreatePR** → Creates GitHub PR

## Monitoring

### CloudWatch Logs

- Lambda functions: `/aws/lambda/sbir-etl-*`
- Step Functions: `/aws/vendedlogs/states/sbir-etl-weekly-refresh`

### CloudWatch Metrics

- Step Functions execution metrics
- Lambda invocation metrics
- Error rates and durations

## Troubleshooting

### Common Issues

1. **Lambda timeout**: Increase timeout in CDK stack
2. **S3 permissions**: Verify IAM role has S3 read/write permissions
3. **Secrets Manager**: Ensure secret names match exactly
4. **Container images**: Verify ECR repository exists and images are pushed

### Debugging

```bash
# View Step Functions execution
aws stepfunctions describe-execution \
  --execution-arn <execution-arn> \
  --region us-east-2

# View Lambda logs
aws logs tail /aws/lambda/sbir-etl-download-csv --follow --region us-east-2
```

## Cost Estimation

- **Step Functions**: ~$0.025 per 1,000 state transitions
- **Lambda**: ~$0.20 per 1M requests + compute time
- **S3**: Storage + requests
- **Secrets Manager**: $0.40 per secret per month

Estimated monthly cost for weekly executions: **$5-10**

## Rollback

To rollback to GitHub Actions workflow:

1. Keep existing GitHub Actions workflow as backup
2. Use feature flag to switch between workflows
3. Both workflows can run in parallel for validation

