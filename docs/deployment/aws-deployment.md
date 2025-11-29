# AWS Deployment Options

**Audience**: DevOps, Cloud Engineers
**Prerequisites**: AWS account, AWS CLI configured
**Related**: [Dagster Cloud](dagster-cloud.md), [Docker Guide](docker-guide.md)
**Last Updated**: 2025-11-29

## Overview

AWS deployment options for SBIR ETL pipeline: serverless (Lambda + Step Functions) and batch processing (AWS Batch).

## Architecture Diagrams

### Serverless Architecture

```
┌─────────────┐
│ EventBridge │ (Weekly schedule)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│Step Functions│ (Orchestration)
└──────┬──────┘
       │
       ├──▶ Lambda: Download SBIR data
       ├──▶ Lambda: Validate data
       ├──▶ Lambda: Profile data
       └──▶ Lambda: Upload to S3
              │
              ▼
         ┌────────┐
         │   S3   │ (Data storage)
         └────────┘
```

### Batch Architecture

```
┌─────────────┐
│ EventBridge │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  AWS Batch  │ (Compute)
└──────┬──────┘
       │
       ├──▶ Job: Extract
       ├──▶ Job: Transform
       └──▶ Job: Load
              │
              ▼
         ┌────────┐
         │ Neo4j  │
         └────────┘
```

## Serverless Deployment

**Best for**: Scheduled data refresh, lightweight processing

### Quick Deploy

```bash
cd infrastructure/cdk
pip install -r requirements.txt
cdk deploy --all
```

### Components

**Lambda Functions:**
- `sbir-download` - Download SBIR data
- `sbir-validate` - Validate data quality
- `sbir-profile` - Generate data profile
- `sbir-upload` - Upload to S3

**Step Functions:**
- Orchestrates Lambda execution
- Handles retries and error handling
- Sends notifications

**EventBridge:**
- Weekly schedule (Monday 9 AM UTC)
- Manual triggers via console

### Configuration

**Environment Variables:**
```bash
S3_BUCKET=sbir-etl-production-data
AWS_REGION=us-east-2
LOG_LEVEL=INFO
```

**IAM Permissions:**
- S3: Read/Write to data bucket
- CloudWatch: Write logs
- Secrets Manager: Read secrets

### Monitoring

**CloudWatch Logs:**
- `/aws/lambda/sbir-download`
- `/aws/lambda/sbir-validate`
- `/aws/lambda/sbir-profile`

**CloudWatch Metrics:**
- Lambda duration
- Lambda errors
- Step Functions execution status

**Alarms:**
- Lambda failures
- Step Functions failures
- S3 upload failures

### Cost Optimization

**Lambda:**
- Memory: 512 MB (adjust based on workload)
- Timeout: 5 minutes
- Reserved concurrency: 1 (prevent runaway costs)

**S3:**
- Lifecycle policy: Move to Glacier after 90 days
- Intelligent-Tiering for frequently accessed data

**Estimated Cost**: $5-10/month

## Batch Deployment

**Best for**: Heavy processing, long-running jobs, GPU workloads

### Setup

**1. Create Compute Environment:**
```bash
aws batch create-compute-environment \
  --compute-environment-name sbir-etl-compute \
  --type MANAGED \
  --compute-resources \
    type=EC2,minvCpus=0,maxvCpus=16,desiredvCpus=0,\
    instanceTypes=optimal,subnets=subnet-xxx,\
    securityGroupIds=sg-xxx,instanceRole=ecsInstanceRole
```

**2. Create Job Queue:**
```bash
aws batch create-job-queue \
  --job-queue-name sbir-etl-queue \
  --priority 1 \
  --compute-environment-order order=1,computeEnvironment=sbir-etl-compute
```

**3. Register Job Definition:**
```bash
aws batch register-job-definition \
  --job-definition-name sbir-etl-job \
  --type container \
  --container-properties file://job-definition.json
```

**job-definition.json:**
```json
{
  "image": "ghcr.io/hollomancer/sbir-analytics:latest",
  "vcpus": 4,
  "memory": 8192,
  "command": ["python", "-m", "src.cli.main", "pipeline", "run"],
  "environment": [
    {"name": "NEO4J_URI", "value": "bolt://neo4j:7687"},
    {"name": "S3_BUCKET", "value": "sbir-etl-production-data"}
  ]
}
```

### Job Execution

**Submit Job:**
```bash
aws batch submit-job \
  --job-name sbir-ingestion-$(date +%Y%m%d) \
  --job-queue sbir-etl-queue \
  --job-definition sbir-etl-job
```

**Monitor Job:**
```bash
aws batch describe-jobs --jobs <job-id>
```

**View Logs:**
```bash
aws logs tail /aws/batch/job --follow
```

### Spot Instances

**Save 70-90% on compute costs:**

```bash
aws batch create-compute-environment \
  --compute-resources \
    type=SPOT,\
    allocationStrategy=SPOT_CAPACITY_OPTIMIZED,\
    bidPercentage=100
```

**Trade-offs:**
- May be interrupted
- Longer queue times
- Not suitable for time-sensitive jobs

### Cost Optimization

**Compute:**
- Use Spot instances (70-90% savings)
- Auto-scale to zero when idle
- Right-size instance types

**Storage:**
- Use EFS for shared data
- Clean up old job logs

**Estimated Cost**: $20-50/month (with Spot)

## Comparison

| Feature | Serverless | Batch |
|---------|-----------|-------|
| **Cost** | $5-10/mo | $20-50/mo |
| **Setup** | Easy | Medium |
| **Scalability** | Auto | Manual |
| **Use Case** | Scheduled refresh | Heavy processing |
| **Maintenance** | Low | Medium |

## Migration Guide

### From Docker to AWS

**1. Build and push image:**
```bash
docker build -t sbir-analytics:latest .
docker tag sbir-analytics:latest ghcr.io/hollomancer/sbir-analytics:latest
docker push ghcr.io/hollomancer/sbir-analytics:latest
```

**2. Deploy infrastructure:**
```bash
cd infrastructure/cdk
cdk deploy --all
```

**3. Migrate data to S3:**
```bash
aws s3 sync data/ s3://sbir-etl-production-data/
```

**4. Update environment variables:**
- Set in Lambda/Batch configuration
- Use Secrets Manager for sensitive values

**5. Test deployment:**
```bash
# Trigger Step Functions
aws stepfunctions start-execution \
  --state-machine-arn <arn> \
  --input '{}'
```

### From Lambda to Dagster Cloud

**1. Keep Lambda for data refresh**
**2. Use Dagster Cloud for orchestration**
**3. Lambda writes to S3**
**4. Dagster Cloud reads from S3**

## Troubleshooting

### Lambda Timeout

**Symptoms**: Function times out after 5 minutes

**Solutions:**
- Increase timeout (max 15 minutes)
- Break into smaller functions
- Use Step Functions for long workflows

### Batch Job Fails

**Symptoms**: Job exits with error code

**Solutions:**
- Check CloudWatch logs
- Verify IAM permissions
- Check resource limits (memory, CPU)
- Test locally with Docker

### S3 Access Denied

**Symptoms**: Cannot read/write to S3

**Solutions:**
- Verify IAM role has S3 permissions
- Check bucket policy
- Verify bucket exists
- Check region matches

## Related Documentation

- [Dagster Cloud](dagster-cloud.md) - Primary deployment method
- [Docker Guide](docker-guide.md) - Local development
- [AWS Serverless Guide](aws-deployment.md) - Detailed Lambda setup (archived)
- [AWS Batch Setup](aws-deployment.md) - Detailed Batch setup (archived)
