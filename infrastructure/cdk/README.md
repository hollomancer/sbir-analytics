# AWS CDK Infrastructure

This directory contains AWS CDK code for deploying the SBIR ETL infrastructure to AWS.

## Prerequisites

1. AWS Account with appropriate permissions
2. AWS CLI configured (`aws configure`)
3. AWS CDK installed (`npm install -g aws-cdk`)
4. Python 3.11+

## Setup

```bash
# Install Python dependencies using uv
uv sync

# Bootstrap CDK (first time only)
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
cdk bootstrap aws://$AWS_ACCOUNT_ID/us-east-2
```

## Deployment

```bash
# Make sure dependencies are synced
uv sync

# Review what will be created
cdk diff

# Deploy all stacks
# Note: Storage stack defaults to importing existing bucket
cdk deploy --all

# Deploy specific stack
# Default: imports existing bucket (if it exists)
cdk deploy sbir-etl-storage
# To create a new bucket instead:
cdk deploy sbir-etl-storage --context create_new_bucket=true

cdk deploy sbir-etl-security
cdk deploy sbir-etl-lambda
cdk deploy sbir-etl-step-functions
```

### Handling Existing Resources

**Storage Stack**: Defaults to importing the existing bucket `sbir-etl-production-data`:
```bash
# Default: imports existing bucket (no context needed)
cdk deploy sbir-etl-storage

# To create a new bucket (will fail if bucket already exists)
cdk deploy sbir-etl-storage --context create_new_bucket="true"
```

**Security Stack**: Defaults to importing existing IAM roles and Secrets Manager secrets:
```bash
# Default: imports existing resources (roles and secrets)
cdk deploy sbir-etl-security

# To create new resources (will fail if they already exist)
cdk deploy sbir-etl-security --context create_new_resources="true"
```

### Fixing Failed Deployments

If a stack is in `ROLLBACK_COMPLETE` or `CREATE_FAILED` state, you must delete it before redeploying:

```bash
# Delete the failed stack via AWS CLI
aws cloudformation delete-stack --stack-name sbir-etl-security --region us-east-2

# Wait for deletion to complete, then redeploy
cdk deploy sbir-etl-security
```

Or delete via AWS Console: CloudFormation → Stacks → Select stack → Delete

## Stacks

1. **StorageStack**: S3 bucket for data storage
2. **SecurityStack**: IAM roles and Secrets Manager
3. **LambdaStack**: Lambda functions
4. **StepFunctionsStack**: Step Functions state machine

## Configuration

Update `cdk.json` with your GitHub repository:

```json
{
  "context": {
    "github_repo": "owner/repo-name"
  }
}
```

## Outputs

After deployment, CDK outputs important ARNs:

- Lambda function ARNs
- Step Functions state machine ARN
- IAM role ARNs
- S3 bucket name

Use these values to configure GitHub Actions secrets.

## Destroying

```bash
# Destroy all stacks
cdk destroy --all
```

**Warning**: This will delete all resources. S3 bucket has `RemovalPolicy.RETAIN` to prevent data loss.

