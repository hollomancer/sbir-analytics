# AWS Serverless Deployment Guide

This guide covers the AWS infrastructure setup for the SBIR ETL pipeline using Step Functions and Lambda, including the migration of the weekly award data refresh workflow to AWS Lambda.

## Table of Contents

1.  [Overview](#1-overview)
2.  [Architecture](#2-architecture)
3.  [Prerequisites](#3-prerequisites)
4.  [Infrastructure Components](#4-infrastructure-components)
    *   [S3 Bucket](#s3-bucket)
    *   [Secrets Manager](#secrets-manager)
    *   [IAM Roles](#iam-roles)
5.  [Deployment Steps](#5-deployment-steps)
    *   [Step 1: Deploy Infrastructure with CDK](#step-1-deploy-infrastructure-with-cdk)
    *   [Step 2: Create Secrets](#step-2-create-secrets)
    *   [Step 3: Build and Deploy Lambda Layer](#step-3-build-and-deploy-lambda-layer)
    *   [Step 4: Deploy Lambda Functions](#step-4-deploy-lambda-functions)
    *   [Step 5: Configure GitHub Actions](#step-5-configure-github-actions)
6.  [Lambda Functions](#6-lambda-functions)
    *   [Lambda Function Structure](#lambda-function-structure)
    *   [Packaging Options](#packaging-options)
    *   [Local Testing](#local-testing)
    *   [Environment Variables](#environment-variables)
    *   [Error Handling](#error-handling)
    *   [S3 Integration](#s3-integration)
    *   [Secrets Manager Integration](#secrets-manager-integration)
    *   [Dagster Integration](#dagster-integration) (Deprecated - see [Lambda to Dagster Migration](lambda-to-dagster-migration.md))
    *   [Performance Optimization](#performance-optimization)
    *   [Deployment Checklist](#deployment-checklist)
7.  [Step Functions State Machine](#7-step-functions-state-machine)
    *   [State Machine Definition](#state-machine-definition)
    *   [Input Format](#input-format)
    *   [Output Format](#output-format)
    *   [Error Handling](#error-handling-1)
    *   [Conditional Logic](#conditional-logic)
    *   [Parallel Execution](#parallel-execution)
    *   [Invoking Step Functions](#invoking-step-functions)
    *   [Testing Locally](#testing-locally)
    *   [Updating the State Machine](#updating-the-state-machine)
8.  [S3 Data Migration and Access](#8-s3-data-migration-and-access)
    *   [Overview](#overview)
    *   [Configuration](#configuration)
    *   [Data Migration Steps](#data-migration-steps)
    *   [How It Works](#how-it-works)
    *   [Testing S3 Access](#testing-s3-access)
    *   [AWS Credentials](#aws-credentials)
9.  [Monitoring](#9-monitoring)
    *   [CloudWatch Logs](#cloudwatch-logs)
    *   [CloudWatch Metrics](#cloudwatch-metrics)
    *   [X-Ray Tracing](#x-ray-tracing)
    *   [AWS Console](#aws-console)
    *   [GitHub Actions](#github-actions)
10. [Troubleshooting](#10-troubleshooting)
    *   [Common Issues](#common-issues)
    *   [Debugging](#debugging)
    *   [Lambda Timeout](#lambda-timeout)
    *   [Script Not Found](#script-not-found)
    *   [S3 Access Denied](#s3-access-denied)
    *   [Neo4j Connection Failed](#neo4j-connection-failed)
    *   [File Not Found](#file-not-found)
    *   [Slow Performance](#slow-performance)
11. [Cost Optimization](#11-cost-optimization)
12. [Rollback](#12-rollback)
13. [Future Enhancements](#13-future-enhancements)
14. [References](#14-references)

---

## 1. Overview

This guide covers the AWS infrastructure setup for the SBIR ETL pipeline using Step Functions and Lambda, including the migration of the weekly award data refresh workflow to AWS Lambda. The weekly award data refresh workflow has been migrated to AWS Lambda to:
- Reduce GitHub Actions compute costs
- Improve scalability and reliability
- Store data in S3 instead of Git
- Remove Git operations from the workflow

## 2. Architecture

### Components

1.  **GitHub Actions Workflow** (`.github/workflows/weekly-award-data-refresh.yml`)
    *   Triggers Lambda function via AWS SDK
    *   Passes workflow_dispatch inputs to Lambda
    *   No longer performs Git operations

2.  **AWS Lambda Function** (`src/lambda/weekly_refresh_handler.py`)
    *   Executes all validation and processing scripts
    *   Downloads CSV from sbir.gov
    *   Compares hash with previous S3 version
    *   Uploads CSV and metadata to S3
    *   Optionally loads data to Neo4j

3.  **Lambda Functions** (Layer-based only)
    *   All Lambda functions use Python layers (no containers)
    *   Container-based functions migrated to Dagster Cloud

4.  **Infrastructure** (`infrastructure/cdk/stacks/lambda_stack.py`)
    *   CDK (Python) configuration for Lambda functions
    *   **Note**: Infrastructure is managed via AWS CDK, not Terraform
    *   IAM roles and policies
    *   **Note**: Container-based Lambda functions have been migrated to Dagster Cloud

## 3. Prerequisites

1.  AWS Account with appropriate permissions
2.  AWS CLI configured
3.  AWS CDK installed (`npm install -g aws-cdk`)
4.  Docker (optional, for local testing only)
5.  Python 3.11+
6.  AWS CDK CLI installed (for infrastructure deployment)

## 4. Infrastructure Components

### S3 Bucket

-   **Name**: `sbir-analytics-production-data`
-   **Region**: `us-east-2`
-   **Structure**:
    *   `raw/awards/` - Downloaded CSV files (30-day retention)
    *   `processed/` - Processed data and validation artifacts
    *   `artifacts/` - Metadata and reports (90-day retention)

### Secrets Manager

-   **Secret Name**: `sbir-analytics/neo4j-aura`
-   **Structure**:
    ```json
    {
      "uri": "neo4j+s://...",
      "username": "...",
      "password": "...",
      "database": "neo4j"
    }
    ```

### IAM Roles

1.  **Lambda Execution Role** (`sbir-analytics-lambda-role`)
    *   S3 read/write permissions
    *   Secrets Manager read permissions
    *   CloudWatch Logs write permissions

2.  **Step Functions Execution Role** (`sbir-analytics-sf-role`)
    *   Lambda invoke permissions
    *   CloudWatch Logs write permissions

3.  **GitHub Actions OIDC Role** (`sbir-analytics-github-actions`)
    *   Step Functions start execution permission
    *   CloudWatch Logs read permission

## 5. Deployment Steps

### Step 1: Deploy Infrastructure with CDK

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

### Step 2: Create Secrets

```bash
# Neo4j Aura credentials
aws secretsmanager create-secret \
  --name sbir-analytics/neo4j-aura \
  --secret-string '{
    "uri": "neo4j+s://...",
    "username": "neo4j",
    "password": "...",
    "database": "neo4j"
  }' \
  --region us-east-2
```

### Step 3: Build and Deploy Lambda Layer

```bash
# Build layer
./scripts/lambda/build_layer.sh

# Upload layer
aws lambda publish-layer-version \
  --layer-name sbir-analytics-python-dependencies \
  --zip-file fileb:///tmp/python-dependencies-layer.zip \
  --compatible-runtimes python3.11 \
  --region us-east-2
```

### Step 4: Deploy Lambda Functions

**Note**: Container-based Lambda functions (ingestion-checks, load-neo4j) have been migrated to Dagster Cloud. Only layer-based Lambda functions are deployed via CDK.

The Lambda functions are deployed automatically via CDK. If you need to update them manually:

```bash
# Package and deploy each function
cd scripts/lambda/download_csv
zip -r function.zip lambda_handler.py
aws lambda update-function-code \
  --function-name sbir-analytics-download-csv \
  --zip-file fileb://function.zip \
  --region us-east-2
```

### Step 5: Configure GitHub Actions

Add the following secrets to your GitHub repository:

-   `AWS_ROLE_ARN`: ARN of the GitHub Actions OIDC role
-   `STEP_FUNCTIONS_STATE_MACHINE_ARN`: ARN of the Step Functions state machine

## 6. Lambda Functions

### Lambda Function Structure

Each Lambda function follows this pattern:

```python
import json
import boto3
from typing import Dict, Any

s3_client = boto3.client('s3')
secrets_client = boto3.client('secretsmanager')

def lambda_handler(event: Dict[str, Any], context) -> Dict[str, Any]:
    """
    Event structure:
    {
        "s3_bucket": "sbir-analytics-production-data",
        "s3_key": "...",
        ...
    }
    """
    try:
        # Read inputs from event
        # Execute function logic
        # Upload outputs to S3
        # Return results
        return {
            "statusCode": 200,
            "body": {
                "status": "success",
                "outputs": {...}
            }
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": {
                "status": "error",
                "error": str(e)
            }
        }
```

### Packaging Options

#### Option A: Lambda Layers (Recommended for Simple Functions)

**Use for**: Functions with standard dependencies (pandas, boto3, neo4j)

**Steps**:

1.  Create function code in `scripts/lambda/{function-name}/lambda_handler.py`
2.  Build layer:
    ```bash
    ./scripts/lambda/build_layer.sh
    ```
3.  Deploy layer:
    ```bash
    aws lambda publish-layer-version \
      --layer-name sbir-analytics-python-dependencies \
      --zip-file fileb:///tmp/python-dependencies-layer.zip \
      --compatible-runtimes python3.11
    ```
4.  Deploy function (via CDK or manually)

**Pros**: Fast cold starts, easy updates, smaller packages
**Cons**: 250MB layer limit, dependency management complexity

#### Option B: Dagster Cloud (For Complex Pipelines)

**Use for**: Functions requiring Dagster, complex orchestration, or long-running processes

**Note**: Container-based Lambda functions have been migrated to Dagster Cloud. Use the `trigger-dagster-refresh` Lambda function to trigger Dagster Cloud jobs instead.

**Steps**:

1.  Define Dagster job in `src/assets/jobs/`
2.  Deploy to Dagster Cloud
3.  Use `trigger-dagster-refresh` Lambda to trigger jobs via API

**Pros**: Full Dagster orchestration, better observability, no Lambda timeout limits
**Cons**: Requires Dagster Cloud account

See [Lambda to Dagster Migration](lambda-to-dagster-migration.md) for details.

### Local Testing

#### Mock AWS Services

```python
# Use moto for local testing
from moto import mock_s3, mock_secretsmanager

@mock_s3
@mock_secretsmanager
def test_lambda_function():
    # Set up mock S3 bucket
    s3_client.create_bucket(Bucket='test-bucket')

    # Set up mock secret
    secrets_client.create_secret(
        Name='test-secret',
        SecretString='{"uri": "bolt://localhost:7687"}'
    )

    # Test Lambda function
    event = {"s3_bucket": "test-bucket", "s3_key": "test.csv"}
    result = lambda_handler(event, None)
    assert result["statusCode"] == 200
```

#### Test with SAM Local

```bash
# Install SAM CLI
pip install aws-sam-cli

# Test locally
sam local invoke DownloadCsvFunction --event test-event.json
```

### Environment Variables

Lambda functions use these environment variables:

-   `S3_BUCKET`: S3 bucket name
-   `NEO4J_SECRET_NAME`: Secrets Manager secret name for Neo4j

### Error Handling

Lambda functions should:

1.  Return structured error responses
2.  Log errors to CloudWatch
3.  Use retry policies in Step Functions
4.  Handle transient failures gracefully

Example:

```python
try:
    # Process data
    result = process_data()
    return {"statusCode": 200, "body": {"status": "success", "result": result}}
except ValueError as e:
    # Client error - don't retry
    return {"statusCode": 400, "body": {"status": "error", "error": str(e)}}
except Exception as e:
    # Server error - retry in Step Functions
    print(f"Error: {e}")
    return {"statusCode": 500, "body": {"status": "error", "error": str(e)}}
```

### S3 Integration

#### Reading from S3

```python
def read_from_s3(bucket: str, key: str) -> str:
    response = s3_client.get_object(Bucket=bucket, Key=key)
    return response["Body"].read().decode("utf-8")
```

#### Writing to S3

```python
def write_to_s3(bucket: str, key: str, content: str, content_type: str = "text/plain"):
    s3_client.put_object(
        Bucket=bucket,
        Key=key,
        Body=content.encode("utf-8"),
        ContentType=content_type
    )
```

### Secrets Manager Integration

```python
def get_secret(secret_name: str) -> dict:
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])
```

### Dagster Integration

For Dagster-dependent functions:

1.  Use `build_asset_context()` to create Dagster context
2.  Materialize assets directly
3.  Handle S3 I/O for intermediate storage
4.  Use temporary directories for local processing

Example:

```python
from dagster import build_asset_context
import src.assets.sbir_ingestion as assets_module

# Configure Dagster
config = _make_config(...)
assets_module.get_config = lambda: config

# Materialize asset
context = build_asset_context()
output = assets_module.raw_sbir_awards(context=context)
result = _output_value(output)
```

### Performance Optimization

1.  **Cold starts**: Use provisioned concurrency for critical functions
2.  **Memory**: Increase memory for CPU-intensive functions
3.  **Timeout**: Set appropriate timeouts (15 min default, up to 15 hours)
4.  **Parallel processing**: Use Step Functions Parallel state

### Deployment Checklist

-   [ ] Function code tested locally
-   [ ] Dependencies included in layer or container
-   [ ] Environment variables configured
-   [ ] IAM permissions correct
-   [ ] S3 bucket permissions verified
-   [ ] Secrets Manager access configured
-   [ ] Timeout and memory settings appropriate
-   [ ] Error handling implemented
-   [ ] CloudWatch logging enabled

## 7. Step Functions State Machine

The Step Functions state machine (`sbir-analytics-weekly-refresh`) orchestrates the entire weekly SBIR awards refresh workflow, replacing the previous GitHub Actions-based workflow.

### State Machine Definition

The state machine is defined in `infrastructure/step-functions/weekly-refresh-state-machine.json`.

### States

1.  **DownloadCSV**: Downloads CSV from SBIR.gov and uploads to S3
2.  **CheckChanges**: Choice state - checks if data changed or force refresh
3.  **ProcessPipeline**: Parallel execution of validation and profiling
4.  **IngestionChecks**: Runs Dagster ingestion validation
5.  **EnrichmentChecks**: Runs enrichment coverage analysis
6.  **ResetNeo4j**: Resets Neo4j database (optional)
7.  **LoadNeo4j**: Loads validated awards into Neo4j
8.  **SmokeChecks**: Validates Neo4j data integrity (workflow completes)
9.  **EndNoChanges**: Success state when no changes detected
10. **ErrorHandler**: Catches and handles errors

### Input Format

```json
{
  "force_refresh": false,
  "source_url": "https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv",
  "s3_bucket": "sbir-analytics-production-data"
}
```

### Output Format

```json
{
  "status": "success",
  "execution_arn": "arn:aws:states:...",
  "output": {
    "status": "success",
    "smoke_check_json_s3_key": "artifacts/2025-01-15/neo4j_smoke_check.json",
    ...
  }
}
}
```

### Error Handling

#### Retry Policies

Each state has retry policies configured:

```json
{
  "Retry": [
    {
      "ErrorEquals": ["States.TaskFailed"],
      "IntervalSeconds": 2,
      "MaxAttempts": 3,
      "BackoffRate": 2.0
    }
  ]
}
```

#### Catch Blocks

Error handling via Catch blocks:

```json
{
  "Catch": [
    {
      "ErrorEquals": ["States.ALL"],
      "Next": "ErrorHandler",
      "ResultPath": "$.error"
    }
  ]
}
```

### Conditional Logic

The `CheckChanges` state uses Choice state:

```json
{
  "Type": "Choice",
  "Choices": [
    {
      "Variable": "$.body.changed",
      "BooleanEquals": true,
      "Next": "ProcessPipeline"
    },
    {
      "Variable": "$.force_refresh",
      "BooleanEquals": true,
      "Next": "ProcessPipeline"
    }
  ],
  "Default": "EndNoChanges"
}
```

### Parallel Execution

The `ProcessPipeline` state runs validation and profiling in parallel:

```json
{
  "Type": "Parallel",
  "Branches": [
    {
      "StartAt": "ValidateDataset",
      "States": {...}
    },
    {
      "StartAt": "ProfileInputs",
      "States": {...}
    }
  ],
  "Next": "IngestionChecks"
}
```

### Invoking Step Functions

#### From GitHub Actions

```yaml
- name: Start Step Functions execution
  run: |
    aws stepfunctions start-execution \
      --state-machine-arn ${{ secrets.STEP_FUNCTIONS_STATE_MACHINE_ARN }} \
      --input '{"force_refresh": false, "s3_bucket": "sbir-analytics-production-data"}'
```

#### From AWS CLI

```bash
aws stepfunctions start-execution \
  --state-machine-arn arn:aws:states:us-east-2:123456789012:stateMachine:sbir-analytics-weekly-refresh \
  --input '{"force_refresh": false}'
```

#### From Python

```python
import boto3

sf_client = boto3.client('stepfunctions')

response = sf_client.start_execution(
    stateMachineArn='arn:aws:states:us-east-2:123456789012:stateMachine:sbir-analytics-weekly-refresh',
    input='{"force_refresh": false}'
)

execution_arn = response['executionArn']
```

### Testing Locally

Use Step Functions Local for local testing:

```bash
# Install Step Functions Local
docker pull amazon/aws-stepfunctions-local

# Run locally
docker run -p 8083:8083 amazon/aws-stepfunctions-local
```

### Updating the State Machine

1.  Update JSON definition file
2.  Deploy via CDK:
    ```bash
    cdk deploy sbir-analytics-step-functions
    ```
3.  Or update manually:
    ```bash
    aws stepfunctions update-state-machine \
      --state-machine-arn <arn> \
      --definition file://weekly-refresh-state-machine.json
    ```

## 8. S3 Data Migration and Access

The SBIR ETL pipeline now supports S3-first data access with local fallback. This is crucial for AWS Serverless deployments as it allows data to be stored and accessed from S3.

### Overview

The SBIR ETL pipeline now supports:
- **S3-first data access**: Automatically tries S3 before falling back to local files
- **Local fallback**: If S3 is unavailable or offline, uses local `data/raw/` directory
- **Automatic path resolution**: Builds S3 URLs from local paths when bucket is configured

### Configuration

Set the S3 bucket name via environment variable:

```bash
export SBIR_ANALYTICS_S3_BUCKET=sbir-analytics-production-data
```

### Data Migration Steps

1.  **Upload Files to S3**:
    ```bash
    # Upload SBIR CSV files
    aws s3 sync data/raw/sbir/ s3://sbir-analytics-production-data/data/raw/sbir/ \
      --exclude "*.gitkeep" \
      --exclude ".DS_Store"

    # Upload USPTO CSV files (if needed)
    aws s3 sync data/raw/uspto/ s3://sbir-analytics-production-data/data/raw/uspto/ \
      --exclude "*.gitkeep" \
      --exclude ".DS_Store"
    ```

2.  **Verify Upload**:
    ```bash
    # List files in S3
    aws s3 ls s3://sbir-analytics-production-data/data/raw/sbir/ --recursive
    ```

### How It Works

#### Path Resolution Flow

1.  **If `SBIR_ANALYTICS_S3_BUCKET` is set:**
    *   Builds S3 URL: `s3://sbir-analytics-production-data/data/raw/sbir/awards_data.csv`
    *   Tries to access S3 file
    *   If S3 succeeds → downloads to temp cache and uses it
    *   If S3 fails → falls back to local `data/raw/sbir/awards_data.csv`

2.  **If `SBIR_ANALYTICS_S3_BUCKET` is not set:**
    *   Uses local path directly (backward compatible)

3.  **If `use_s3_first=False` (in `config/base.yaml`):**
    *   Prefers local even if S3 is available

#### S3 File Caching

- S3 files are downloaded to `/tmp/sbir-analytics-s3-cache/` (or system temp directory)
- Files are cached by MD5 hash of S3 path to avoid re-downloading
- Cache persists across runs within the same execution environment

### Testing S3 Access

```bash
# Set environment variable
export SBIR_ANALYTICS_S3_BUCKET=sbir-analytics-production-data

# Run extraction
uv run dagster asset materialize -m src.definitions raw_sbir_awards
```

### AWS Credentials

#### Local Development

Configure AWS credentials:

```bash
aws configure
# Or set environment variables:
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
export AWS_DEFAULT_REGION=us-east-1
```

#### AWS Lambda/Step Functions

AWS Lambda and Step Functions use IAM roles for S3 access. Configure:

1.  Attach IAM role with S3 read/write permissions to your Lambda functions and Step Functions state machine.
    ```json
    {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": ["s3:GetObject", "s3:ListBucket", "s3:PutObject", "s3:DeleteObject"],
          "Resource": [
            "arn:aws:s3:::sbir-analytics-production-data",
            "arn:aws:s3:::sbir-analytics-production-data/*"
          ]
        }
      ]
    }
    ```

## 9. Monitoring

### CloudWatch Logs

-   Lambda functions: `/aws/lambda/sbir-analytics-*`
-   Step Functions: `/aws/vendedlogs/states/sbir-analytics-weekly-refresh`

### CloudWatch Metrics

-   Step Functions execution metrics
-   Lambda invocation metrics
-   Error rates and durations

### X-Ray Tracing

Enable X-Ray tracing in CDK:

```python
function = lambda_.Function(
    ...,
    tracing=lambda_.Tracing.ACTIVE
)
```

### AWS Console

View execution in AWS Console:

```
https://console.aws.amazon.com/states/home?region=us-east-2#/executions/details/{execution-arn}
```

### GitHub Actions

The workflow displays Lambda execution results in the Actions UI. Check the "Invoke Lambda function" step for execution details.

## 10. Troubleshooting

### Common Issues

1.  **Lambda timeout**: Increase timeout in CDK stack or optimize function
2.  **S3 permissions**: Verify IAM role has S3 read/write permissions
3.  **Secrets Manager**: Ensure secret names match exactly
4.  **Lambda functions**: Verify all layer-based Lambda functions are deployed via CDK
5.  **State transition errors**: Check Lambda function logs
6.  **Input/output format**: Ensure JSON structure matches expected format

### Debugging

```bash
# View Step Functions execution
aws stepfunctions describe-execution \
  --execution-arn <execution-arn> \
  --region us-east-2

# View Lambda logs
aws logs tail /aws/lambda/sbir-analytics-download-csv --follow --region us-east-2
```

### Lambda Timeout

If Lambda times out (15-minute limit):
- Check CloudWatch Logs for slow operations
- Consider optimizing scripts or using Step Functions for longer workflows

### Script Not Found

If scripts fail with "Script not found":
- Verify Lambda layer includes all dependencies
- Check that function code is properly packaged
- Ensure scripts are included in the Lambda deployment package

### S3 Access Denied

If S3 uploads fail:
- Verify IAM role has S3 permissions
- Check bucket policy allows Lambda role
- Verify bucket name is correct

### Neo4j Connection Failed

If Neo4j operations fail:
- Verify secret exists in Secrets Manager
- Check secret ARN matches CDK configuration
- Verify Neo4j credentials are correct
- Check network connectivity from Lambda

### File Not Found

**Error:** `FileNotFoundError: Neither S3 (...) nor local (...) file exists`

**Solution:**
- Verify file exists in S3: `aws s3 ls s3://sbir-analytics-production-data/data/raw/sbir/awards_data.csv`
- Verify local fallback path exists: `ls data/raw/sbir/awards_data.csv`
- Check environment variable is set correctly

### Slow Performance

**Symptom:** S3 downloads are slow

**Solution:**
- Files are cached after first download
- Consider using AWS CloudFront or S3 Transfer Acceleration
- For very large files, consider using DuckDB's native S3 support (future enhancement)

## 11. Cost Optimization

-   Step Functions: ~$0.025 per 1,000 state transitions
-   Lambda: ~$0.20 per 1M requests + compute time
-   S3: Storage + requests
-   Secrets Manager: $0.40 per secret per month

Estimated monthly cost for weekly executions: **$5-10**

## 12. Rollback

To rollback to GitHub Actions workflow:

1.  Keep existing GitHub Actions workflow as backup
2.  Lambda function remains available but unused
3.  Data in S3 remains accessible

## 13. Future Enhancements

-   [ ] Add SNS notifications for completion/failures
-   [ ] Add CloudWatch alarms for failures
-   [ ] Implement retry logic with exponential backoff
-   [ ] Add integration tests for Lambda handler
-   [ ] Direct S3 support in DuckDB (via `httpfs` extension)
-   [ ] Support for other cloud storage (GCS, Azure Blob)
-   [ ] Configurable cache directory and TTL
-   [ ] Parallel S3 downloads for multiple files
-   [ ] S3 path validation and health checks

## 14. References

-   [AWS Lambda Container Images](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html)
-   [GitHub Actions OIDC](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
-   [AWS CDK Documentation](https://docs.aws.amazon.com/cdk/)
-   [cloudpathlib documentation](https://cloudpathlib.drivendata.org/)
-   [boto3 S3 documentation](https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html)
