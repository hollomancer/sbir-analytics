# Running Analysis Jobs with AWS Batch

This guide explains how to run analysis jobs (CET, Fiscal Returns, PaECTER) using AWS Batch for cost-effective, scalable execution.

## Overview

AWS Batch provides on-demand compute for running analysis jobs in containers, with automatic scaling and Spot instance support for 70% cost savings.

### Architecture

```
┌─────────────────────────────┐
│   GitHub Actions Workflow   │
│   - Trigger job submission  │
│   - Monitor completion      │  (2-5 min runtime)
│   - Fetch logs              │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│      AWS Batch Queue        │
│   - Job scheduling          │
│   - Auto-scaling            │
└──────────────┬──────────────┘
               │
               ▼
┌─────────────────────────────┐
│    Spot EC2 Instances       │
│   - Pull Docker image       │
│   - Execute Dagster job     │  (1-6 hours)
│   - Write results to S3     │
└─────────────────────────────┘
```

## Prerequisites

### 1. Deploy Infrastructure

Deploy the AWS Batch CDK stack:

```bash
cd infrastructure/cdk

# First-time setup: Create new resources
cdk deploy sbir-analytics-batch \
  --context create_new_resources=true \
  --context github_repo=hollomancer/sbir-analytics

# Subsequent deploys: Use existing resources
cdk deploy sbir-analytics-batch
```

This creates:
- ✅ ECR repository for analysis job images
- ✅ Compute environment with Spot instances
- ✅ Job queue for scheduling
- ✅ Job definitions for each analysis job type
- ✅ IAM roles for job execution

### 2. Build and Push Docker Image

Build the analysis job Docker image and push to ECR:

```bash
# Trigger the build workflow manually
gh workflow run build-analysis-image.yml

# Or build locally and push
aws ecr get-login-password --region us-east-2 | \
  docker login --username AWS --password-stdin \
  658445659195.dkr.ecr.us-east-2.amazonaws.com

docker build -f Dockerfile.batch-analysis \
  -t sbir-analytics-analysis-jobs:latest .

docker tag sbir-analytics-analysis-jobs:latest \
  658445659195.dkr.ecr.us-east-2.amazonaws.com/sbir-analytics-analysis-jobs:latest

docker push \
  658445659195.dkr.ecr.us-east-2.amazonaws.com/sbir-analytics-analysis-jobs:latest
```

The build workflow automatically:
- Builds on push to `main`
- Caches layers for faster builds
- Tags with `latest` and git SHA
- Pushes to ECR repository

### 3. Verify Setup

Check that infrastructure is ready:

```bash
# Check compute environment
aws batch describe-compute-environments \
  --compute-environments sbir-analytics-analysis-compute-env

# Check job queue
aws batch describe-job-queues \
  --job-queues sbir-analytics-analysis-job-queue

# Check job definitions
aws batch describe-job-definitions \
  --job-definition-name sbir-analytics-analysis-cet-pipeline \
  --status ACTIVE

# Verify ECR image
aws ecr describe-images \
  --repository-name sbir-analytics-analysis-jobs \
  --image-ids imageTag=latest
```

## Running Jobs

### Option 1: GitHub Actions Workflow (Recommended)

1. Go to **Actions** → **Analysis Jobs On-Demand**
2. Click **Run workflow**
3. Select:
   - **Job to run**: `cet_full_pipeline`, `fiscal_returns_mvp`, `paecter_embeddings`, or `all_ml_jobs`
   - **Execution mode**: `aws-batch`
4. Click **Run workflow**

The workflow will:
- Submit job(s) to AWS Batch
- Monitor completion every 30 seconds
- Stream logs to GitHub Actions
- Report status in job summary

**Advantages:**
- ✅ No local setup needed
- ✅ Automatic log collection
- ✅ Progress monitoring
- ✅ Email notifications on failure

### Option 2: AWS CLI

Submit jobs directly using the AWS CLI:

```bash
# Submit CET pipeline job
aws batch submit-job \
  --job-name cet-pipeline-$(date +%Y%m%d-%H%M%S) \
  --job-queue sbir-analytics-analysis-job-queue \
  --job-definition sbir-analytics-analysis-cet-pipeline

# Submit Fiscal Returns job
aws batch submit-job \
  --job-name fiscal-returns-$(date +%Y%m%d-%H%M%S) \
  --job-queue sbir-analytics-analysis-job-queue \
  --job-definition sbir-analytics-analysis-fiscal-returns

# Submit PaECTER job
aws batch submit-job \
  --job-name paecter-embeddings-$(date +%Y%m%d-%H%M%S) \
  --job-queue sbir-analytics-analysis-job-queue \
  --job-definition sbir-analytics-analysis-paecter-embeddings
```

### Option 3: AWS Console

1. Navigate to [AWS Batch Console](https://console.aws.amazon.com/batch)
2. Select **Jobs** → **Submit new job**
3. Configure:
   - **Job name**: `ml-cet-20250130`
   - **Job definition**: `sbir-analytics-analysis-cet-pipeline`
   - **Job queue**: `sbir-analytics-analysis-job-queue`
4. Click **Submit job**

## Monitoring Jobs

### GitHub Actions

When running via GitHub Actions, monitoring is automatic:
- Job status updates every 30 seconds
- Logs streamed to workflow output
- Summary with job IDs and links

### AWS Console

View jobs in the [AWS Batch Console](https://console.aws.amazon.com/batch/home?region=us-east-2#jobs):

- **SUBMITTED**: Job queued, waiting for compute
- **PENDING**: Waiting for EC2 instance to start
- **RUNNABLE**: Ready to run, waiting for capacity
- **STARTING**: Container starting
- **RUNNING**: Job executing
- **SUCCEEDED**: Completed successfully
- **FAILED**: Job failed (check logs)

### CloudWatch Logs

View detailed logs:

```bash
# List log streams
aws logs describe-log-streams \
  --log-group-name /aws/batch/sbir-analytics-ml \
  --order-by LastEventTime \
  --descending

# Tail logs for a specific job
aws logs tail /aws/batch/sbir-analytics-ml \
  --follow \
  --format short
```

Or via console: [CloudWatch Logs](https://console.aws.amazon.com/cloudwatch/home?region=us-east-2#logsV2:log-groups/log-group/$252Faws$252Fbatch$252Fsbir-analytics-ml)

### AWS CLI

```bash
# Check job status
aws batch describe-jobs --jobs <JOB_ID>

# List recent jobs
aws batch list-jobs \
  --job-queue sbir-analytics-analysis-job-queue \
  --job-status RUNNING

# Cancel a job
aws batch terminate-job \
  --job-id <JOB_ID> \
  --reason "User requested cancellation"
```

## Cost Analysis

### Compute Costs

**Spot Instances** (70% discount vs on-demand):

| Instance Type | vCPUs | RAM | Spot Price/hr | Use Case |
|---------------|-------|-----|---------------|----------|
| c5.2xlarge | 8 | 16 GB | ~$0.10 | CET, PaECTER |
| c5.4xlarge | 16 | 32 GB | ~$0.20 | Large analysis jobs |
| m5.2xlarge | 8 | 32 GB | ~$0.12 | Memory-intensive |

**Example Monthly Costs:**

| Scenario | Weekly Jobs | Runtime | Instances | Cost/Month |
|----------|-------------|---------|-----------|------------|
| Light usage | 4 jobs | 1 hr each | c5.2xlarge | ~$1.60 |
| Regular usage | 12 jobs | 1 hr each | c5.2xlarge | ~$4.80 |
| Heavy usage | 30 jobs | 2 hr each | c5.2xlarge | ~$24.00 |

### Hidden Costs

- **ECR storage**: ~$0.10/GB/month (minimal for single image)
- **CloudWatch Logs**: ~$0.50/GB ingested (minimal)
- **Data transfer**: Free within same region

### Cost Comparison

| Approach | 4 jobs/week @ 1hr | Cost/Month |
|----------|-------------------|------------|
| **AWS Batch (Spot)** | 4 hrs | **~$1.60** ✅ |
| GitHub Actions | Free tier | $0 ✅ |
| EC2 always-on | 730 hrs | ~$15 |
| ECS Fargate | 4 hrs | ~$4.80 |

**Winner for production ML:**
- AWS Batch for >6 hour jobs or >7GB RAM
- GitHub Actions for <6 hour jobs within free tier

## Job Definitions

### CET Full Pipeline

**Job Definition:** `sbir-analytics-analysis-cet-pipeline`

- **vCPUs**: 8
- **Memory**: 16 GB
- **Timeout**: 6 hours
- **Retries**: 2 (for Spot interruptions)

Runs: Company Emerging Technologies classification pipeline

### Fiscal Returns MVP

**Job Definition:** `sbir-analytics-analysis-fiscal-returns`

- **vCPUs**: 4
- **Memory**: 8 GB
- **Timeout**: 4 hours
- **Retries**: 2

Runs: Economic impact analysis using R (stateior package)

### PaECTER Embeddings

**Job Definition:** `sbir-analytics-analysis-paecter-embeddings`

- **vCPUs**: 8
- **Memory**: 16 GB
- **Timeout**: 6 hours
- **Retries**: 2

Runs: Patent-award matching using sentence-transformers

## Troubleshooting

### Job Stuck in RUNNABLE

**Symptom**: Job stays in RUNNABLE state for >10 minutes

**Causes:**
1. Insufficient Spot capacity
2. VPC/subnet issues
3. Image pull errors

**Solutions:**
```bash
# Check compute environment status
aws batch describe-compute-environments \
  --compute-environments sbir-analytics-analysis-compute-env

# View detailed job status
aws batch describe-jobs --jobs <JOB_ID>

# Check CloudWatch logs for errors
aws logs tail /aws/batch/job
```

### Job Failed

**Symptom**: Job shows FAILED status

**Solutions:**

1. Check CloudWatch logs:
```bash
aws logs tail /aws/batch/sbir-analytics-ml \
  --log-stream-names <LOG_STREAM_NAME> \
  --format short
```

2. Common issues:
   - **OOM (Out of Memory)**: Increase memory in job definition
   - **Import errors**: Rebuild Docker image with dependencies
   - **S3 permissions**: Check IAM role permissions
   - **Secrets Manager**: Verify Neo4j credentials accessible

3. Re-run with more resources:
```bash
aws batch submit-job \
  --job-name retry-$(date +%Y%m%d-%H%M%S) \
  --job-queue sbir-analytics-analysis-job-queue \
  --job-definition sbir-analytics-analysis-cet-pipeline \
  --container-overrides '{
    "vcpus": 16,
    "memory": 32768
  }'
```

### Spot Instance Interrupted

**Symptom**: Job fails with "Host EC2 instance terminated"

**Solution**: Jobs automatically retry (configured for 2 attempts). If persistent:

```bash
# Check Spot interruption rate
aws ec2 describe-spot-price-history \
  --instance-types c5.2xlarge \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --product-descriptions "Linux/UNIX"
```

Consider switching to on-demand for critical jobs:
- Update compute environment type from `SPOT` to `EC2`
- Costs 3x more but guaranteed availability

### Docker Image Not Found

**Symptom**: "CannotPullContainerError"

**Solution:**

```bash
# Verify image exists in ECR
aws ecr describe-images \
  --repository-name sbir-analytics-analysis-jobs

# Re-build and push image
gh workflow run build-analysis-image.yml
```

### Permission Denied Errors

**Symptom**: "AccessDenied" when accessing S3 or Secrets Manager

**Solution:**

Check IAM role has required permissions:
```bash
# View job task role
aws iam get-role --role-name sbir-analytics-batch-job-task-role

# View attached policies
aws iam list-attached-role-policies \
  --role-name sbir-analytics-batch-job-task-role

# Update CDK stack if permissions missing
cd infrastructure/cdk
cdk deploy sbir-analytics-batch
```

## Advanced Configuration

### Override Job Parameters

Run with custom configuration:

```bash
aws batch submit-job \
  --job-name custom-cet-$(date +%Y%m%d-%H%M%S) \
  --job-queue sbir-analytics-analysis-job-queue \
  --job-definition sbir-analytics-analysis-cet-pipeline \
  --container-overrides '{
    "vcpus": 16,
    "memory": 32768,
    "environment": [
      {"name": "CUSTOM_CONFIG", "value": "production"}
    ]
  }'
```

### Parallel Job Execution

Submit multiple jobs to run in parallel:

```bash
# Submit all jobs at once (they run in parallel)
for JOB in cet-pipeline fiscal-returns paecter-embeddings; do
  aws batch submit-job \
    --job-name "ml-${JOB}-$(date +%Y%m%d-%H%M%S)" \
    --job-queue sbir-analytics-analysis-job-queue \
    --job-definition "sbir-analytics-analysis-${JOB}"
done
```

### Custom Docker Image Tags

Use specific image versions:

```bash
# Build with custom tag
docker build -f Dockerfile.batch-analysis -t sbir-analytics-analysis-jobs:v1.2.3 .
docker tag sbir-analytics-analysis-jobs:v1.2.3 \
  658445659195.dkr.ecr.us-east-2.amazonaws.com/sbir-analytics-analysis-jobs:v1.2.3
docker push \
  658445659195.dkr.ecr.us-east-2.amazonaws.com/sbir-analytics-analysis-jobs:v1.2.3

# Update job definition to use specific tag
# (Edit in CDK stack or create new revision)
```

### Scheduled Jobs

Set up EventBridge rules for scheduled execution:

```bash
# Create rule for weekly execution
aws events put-rule \
  --name weekly-ml-jobs \
  --schedule-expression "cron(0 3 ? * MON *)" \
  --state ENABLED

# Add Batch target
aws events put-targets \
  --rule weekly-ml-jobs \
  --targets "Id"="1","Arn"="arn:aws:batch:us-east-2:ACCOUNT:job-queue/sbir-analytics-analysis-job-queue","RoleArn"="ROLE_ARN","BatchParameters"={"JobDefinition"="sbir-analytics-analysis-cet-pipeline","JobName"="weekly-cet"}
```

## Comparison: GitHub Actions vs AWS Batch

| Feature | GitHub Actions | AWS Batch |
|---------|----------------|-----------|
| **Max Runtime** | 6 hours | Unlimited |
| **Max Memory** | 7 GB | 244 GB+ |
| **Max vCPUs** | 2 | 96+ |
| **Cost (4 jobs/week)** | $0 | ~$1.60/month |
| **Cold Start** | None | 1-3 min |
| **Spot Instances** | No | Yes (70% savings) |
| **Parallel Jobs** | Limited | Unlimited |
| **Setup Time** | 0 min | 30 min |
| **Best For** | Testing, infrequent | Production, large jobs |

## Migration from GitHub Actions

To migrate from GitHub Actions to AWS Batch:

1. **Deploy infrastructure** (one-time setup)
   ```bash
   cd infrastructure/cdk
   cdk deploy sbir-analytics-batch --context create_new_resources=true
   ```

2. **Build Docker image** (automatic on push to main)
   ```bash
   git push origin main  # Triggers build-analysis-image.yml
   ```

3. **Test single job**
   - Go to Actions → Analysis Jobs On-Demand
   - Select execution mode: `aws-batch`
   - Choose job and run

4. **Monitor and optimize**
   - Check CloudWatch logs
   - Adjust vCPU/memory if needed
   - Monitor costs in AWS Cost Explorer

5. **Schedule regular jobs** (optional)
   - Use EventBridge rules or keep GitHub Actions scheduler
   - Both can coexist

## Next Steps

1. ✅ Deploy infrastructure: `cdk deploy sbir-analytics-batch`
2. ✅ Build Docker image: Push to main or run workflow manually
3. ✅ Test job execution: Run single job via GitHub Actions
4. ✅ Monitor costs: Check AWS Cost Explorer after 1 week
5. ✅ Optimize: Adjust resources based on actual usage

## Support

- **Infrastructure issues**: Check CDK stack deployment
- **Docker build failures**: Review build-analysis-image.yml logs
- **Job execution errors**: Check CloudWatch Logs
- **Cost concerns**: Review AWS Cost Explorer
- **Questions**: See [deployment-comparison.md](./deployment-comparison.md)
