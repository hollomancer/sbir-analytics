# Lambda Migration Guide - Weekly Award Data Refresh

This guide documents the migration of the weekly award data refresh workflow from GitHub Actions to AWS Lambda.

## Overview

The weekly award data refresh workflow has been migrated to AWS Lambda to:
- Reduce GitHub Actions compute costs
- Improve scalability and reliability
- Store data in S3 instead of Git
- Remove Git operations from the workflow

## Architecture

### Components

1. **GitHub Actions Workflow** (`.github/workflows/weekly-award-data-refresh.yml`)
   - Triggers Lambda function via AWS SDK
   - Passes workflow_dispatch inputs to Lambda
   - No longer performs Git operations

2. **AWS Lambda Function** (`src/lambda/weekly_refresh_handler.py`)
   - Executes all validation and processing scripts
   - Downloads CSV from sbir.gov
   - Compares hash with previous S3 version
   - Uploads CSV and metadata to S3
   - Optionally loads data to Neo4j

3. **Lambda Container Image** (`docker/lambda/Dockerfile`)
   - Based on AWS Lambda Python 3.11 runtime
   - Contains all project dependencies
   - Includes scripts and documentation

4. **Infrastructure** (`infrastructure/lambda/weekly-refresh.tf`)
   - Terraform configuration for Lambda function
   - IAM roles and policies
   - ECR repository for container image

## Setup

### Prerequisites

- AWS CLI configured with appropriate credentials
- Docker installed and running
- Terraform installed (for infrastructure)
- AWS account with permissions to create Lambda functions, ECR repositories, and IAM roles

### 1. Create Infrastructure

```bash
cd infrastructure/lambda

# Copy example variables file
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values

# Initialize Terraform
terraform init

# Review changes
terraform plan

# Apply infrastructure
terraform apply
```

This creates:
- ECR repository: `sbir-etl/weekly-refresh`
- Lambda function: `sbir-weekly-refresh`
- IAM role with S3 and Secrets Manager permissions
- CloudWatch Log Group

**Note**: Update `terraform.tfvars` with your S3 bucket name and optional Neo4j secret ARN before applying.

### 2. Configure Secrets Manager

Store Neo4j credentials in AWS Secrets Manager (optional):

```bash
aws secretsmanager create-secret \
  --name sbir-etl/neo4j-credentials \
  --secret-string '{
    "NEO4J_URI": "neo4j+s://...",
    "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": "...",
    "NEO4J_DATABASE": "neo4j"
  }'
```

Update Terraform variables:
```hcl
neo4j_secret_name = "sbir-etl/neo4j-credentials"
neo4j_secret_arn  = "arn:aws:secretsmanager:us-east-1:...:secret:sbir-etl/neo4j-credentials"
```

### 3. Configure GitHub Actions

Add the following secrets to your GitHub repository:

- `AWS_ROLE_ARN`: ARN of the IAM role for GitHub Actions OIDC
- `NEO4J_SECRET_NAME`: Secrets Manager secret name (optional)

### 4. Deploy Lambda Function

```bash
./scripts/deploy/lambda-deploy.sh
```

This script:
1. Builds the Docker image
2. Pushes to ECR
3. Updates the Lambda function code

## Workflow

### Scheduled Execution

The workflow runs every Monday at 9 AM UTC via GitHub Actions cron:

```yaml
schedule:
  - cron: "0 9 * * 1"
```

### Manual Execution

Trigger manually via GitHub Actions UI with optional inputs:
- `force_refresh`: Force refresh even if CSV hash unchanged
- `source_url`: Override default SBIR.gov URL

### Lambda Execution Flow

1. **Download CSV**: Downloads from sbir.gov (or override URL)
2. **Change Detection**: Calculates SHA-256 hash and compares with S3 metadata
3. **Processing** (if changed or force_refresh):
   - Validate dataset
   - Profile inputs
   - Run ingestion checks
   - Run enrichment checks
   - Optionally load to Neo4j
4. **Upload to S3**: Uploads CSV and all metadata to S3

## S3 Structure

```
s3://sbir-etl-production-data/
├── data/raw/sbir/
│   ├── award_data.csv                    # Latest CSV
│   └── award_data_YYYY-MM-DD.csv        # Versioned CSVs
└── reports/awards_data_refresh/
    ├── latest.json                       # Latest metadata
    ├── latest.md                         # Latest summary
    ├── inputs_profile.json
    ├── enrichment_summary.json
    └── ...                               # Other metadata files
```

## Testing

### Local Testing

Test the Lambda function locally using Docker:

```bash
# Set AWS credentials (or use AWS profile)
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
export AWS_DEFAULT_REGION=us-east-1
export S3_BUCKET=sbir-etl-production-data

# Run local test
./scripts/test/lambda-local-test.sh
```

This builds the container image and runs the Lambda handler with a test event.

### CloudWatch Logs

Lambda logs are available in CloudWatch:
- Log Group: `/aws/lambda/sbir-weekly-refresh`
- Retention: 30 days

View logs:
```bash
aws logs tail /aws/lambda/sbir-weekly-refresh --follow
```

### CloudWatch Metrics

Monitor Lambda execution:
- Invocations
- Duration
- Errors
- Throttles

View metrics:
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=sbir-weekly-refresh \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 3600 \
  --statistics Sum
```

### GitHub Actions

The workflow displays Lambda execution results in the Actions UI. Check the "Invoke Lambda function" step for execution details.

## Troubleshooting

### Lambda Timeout

If Lambda times out (15-minute limit):
- Check CloudWatch Logs for slow operations
- Consider optimizing scripts or using Step Functions for longer workflows

### Script Not Found

If scripts fail with "Script not found":
- Verify scripts are copied to container image
- Check Dockerfile COPY commands
- Ensure scripts are executable

### S3 Access Denied

If S3 uploads fail:
- Verify IAM role has S3 permissions
- Check bucket policy allows Lambda role
- Verify bucket name is correct

### Neo4j Connection Failed

If Neo4j operations fail:
- Verify secret exists in Secrets Manager
- Check secret ARN matches Terraform configuration
- Verify Neo4j credentials are correct
- Check network connectivity from Lambda

## Cost Optimization

- Lambda: Pay per invocation (first 1M requests free/month)
- S3: Pay for storage and requests (minimal for weekly refresh)
- CloudWatch Logs: First 5GB free/month
- ECR: Pay for storage (minimal for single image)

Estimated monthly cost: < $5 for weekly executions

## Rollback

To rollback to GitHub Actions workflow:

1. Revert `.github/workflows/weekly-award-data-refresh.yml` to previous version
2. Lambda function remains available but unused
3. Data in S3 remains accessible

## Future Enhancements

- [ ] Add SNS notifications for completion/failures
- [ ] Use Step Functions for longer workflows
- [ ] Add CloudWatch alarms for failures
- [ ] Implement retry logic with exponential backoff
- [ ] Add integration tests for Lambda handler

## References

- [AWS Lambda Container Images](https://docs.aws.amazon.com/lambda/latest/dg/images-create.html)
- [GitHub Actions OIDC](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)

