# AWS CDK Infrastructure

This directory contains AWS CDK code for deploying the SBIR ETL infrastructure to AWS.

## Prerequisites

1. AWS Account with appropriate permissions
2. AWS CLI configured (`aws configure`)
3. AWS CDK installed (`npm install -g aws-cdk`)
4. Python 3.11+

## Setup

```bash
# Install Python dependencies
pip install -r requirements.txt

# Bootstrap CDK (first time only)
cdk bootstrap aws://ACCOUNT-ID/us-east-2
```

## Deployment

```bash
# Deploy all stacks
cdk deploy --all

# Deploy specific stack
cdk deploy sbir-etl-storage
cdk deploy sbir-etl-security
cdk deploy sbir-etl-lambda
cdk deploy sbir-etl-step-functions
```

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

