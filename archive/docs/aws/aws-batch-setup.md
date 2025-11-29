# AWS Batch Deployment Setup Guide

This guide shows how to deploy the ML location using AWS Batch instead of a dedicated EC2 instance.

## Benefits vs EC2

✅ **Pay only for job execution time** (not 24/7)
✅ **Auto-scaling** - run 1 or 100 jobs in parallel
✅ **Spot instances** - 70% cheaper than on-demand
✅ **Managed infrastructure** - AWS handles compute lifecycle
✅ **Better resource allocation** - different jobs can use different instance types

## Architecture

```
Small EC2 Agent (t3.micro, ~$7/mo)
       ↓
   AWS Batch
       ↓
   Compute Environment (managed EC2 fleet)
       ↓
   Job Queue
       ↓
   Jobs run as containers (start → execute → stop)
```

## Prerequisites

- AWS Account with permissions for:
  - Batch (CreateComputeEnvironment, RegisterJobDefinition, SubmitJob)
  - EC2 (for compute resources)
  - IAM (for service roles)
  - ECR (for container images)
- Dagster Cloud account
- AWS CLI configured

## Setup Steps

### Step 1: Create ECR Repository

Store your Docker images with ML dependencies:

```bash
aws ecr create-repository \
  --repository-name dagster-ml-workloads \
  --region us-east-2

# Note the repositoryUri (e.g., 123456789012.dkr.ecr.us-east-2.amazonaws.com/dagster-ml-workloads)
ECR_URI=$(aws ecr describe-repositories \
  --repository-names dagster-ml-workloads \
  --region us-east-2 \
  --query 'repositories[0].repositoryUri' \
  --output text)

echo "ECR Repository: $ECR_URI"
```

### Step 2: Build and Push Docker Image

```bash
# Login to ECR
aws ecr get-login-password --region us-east-2 | \
  docker login --username AWS --password-stdin $ECR_URI

# Build image with all ML dependencies
docker build \
  --platform linux/amd64 \
  -t $ECR_URI:latest \
  -f Dockerfile .

# Push to ECR
docker push $ECR_URI:latest
```

### Step 3: Create IAM Roles

#### Batch Service Role

```bash
# Create trust policy
cat > batch-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "batch.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name AWSBatchServiceRole \
  --assume-role-policy-document file://batch-trust-policy.json

# Attach policy
aws iam attach-role-policy \
  --role-name AWSBatchServiceRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSBatchServiceRole
```

#### ECS Task Execution Role

```bash
# Create trust policy for ECS
cat > ecs-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name ecsTaskExecutionRole \
  --assume-role-policy-document file://ecs-trust-policy.json

# Attach policies
aws iam attach-role-policy \
  --role-name ecsTaskExecutionRole \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy
```

#### Job Role (for S3 access, etc.)

```bash
# Create trust policy
cat > job-trust-policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# Create role
aws iam create-role \
  --role-name DagsterBatchJobRole \
  --assume-role-policy-document file://job-trust-policy.json

# Attach S3 access (adjust as needed)
aws iam attach-role-policy \
  --role-name DagsterBatchJobRole \
  --policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess
```

### Step 4: Create AWS Batch Resources

#### Compute Environment

```bash
# Get default VPC and subnets
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query 'Vpcs[0].VpcId' --output text)
SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query 'Subnets[*].SubnetId' --output text | tr '\t' ',')

# Create compute environment (with Spot instances for 70% savings!)
aws batch create-compute-environment \
  --compute-environment-name dagster-ml-spot \
  --type MANAGED \
  --state ENABLED \
  --compute-resources type=SPOT,allocationStrategy=SPOT_CAPACITY_OPTIMIZED,minvCpus=0,maxvCpus=256,desiredvCpus=0,instanceTypes=optimal,subnets=$SUBNET_IDS,securityGroupIds=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=default" --query 'SecurityGroups[0].GroupId' --output text),instanceRole=arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):instance-profile/ecsInstanceRole,bidPercentage=100 \
  --service-role arn:aws:iam::$(aws sts get-caller-identity --query Account --output text):role/AWSBatchServiceRole \
  --region us-east-2

# Or for on-demand (more expensive but guaranteed capacity):
# aws batch create-compute-environment \
#   --compute-environment-name dagster-ml-ondemand \
#   --type MANAGED \
#   --state ENABLED \
#   --compute-resources type=EC2,minvCpus=0,maxvCpus=256,desiredvCpus=0,instanceTypes=c5.large,c5.xlarge,c5.2xlarge,subnets=$SUBNET_IDS,securityGroupIds=... \
#   ...
```

#### Job Queue

```bash
# Create job queue
aws batch create-job-queue \
  --job-queue-name dagster-ml-queue \
  --state ENABLED \
  --priority 1 \
  --compute-environment-order order=1,computeEnvironment=dagster-ml-spot \
  --region us-east-2
```

#### Job Definition

```bash
# Create job definition
aws batch register-job-definition \
  --job-definition-name dagster-ml-job \
  --type container \
  --platform-capabilities EC2 \
  --container-properties '{
    "image": "'$ECR_URI':latest",
    "vcpus": 4,
    "memory": 16384,
    "jobRoleArn": "arn:aws:iam::'$(aws sts get-caller-identity --query Account --output text)':role/DagsterBatchJobRole",
    "executionRoleArn": "arn:aws:iam::'$(aws sts get-caller-identity --query Account --output text)':role/ecsTaskExecutionRole",
    "environment": [
      {"name": "DAGSTER_HOME", "value": "/opt/dagster/dagster_home"},
      {"name": "AWS_REGION", "value": "us-east-2"}
    ]
  }' \
  --region us-east-2
```

### Step 5: Launch Agent EC2 Instance

Launch a tiny instance (t3.micro is enough) to run the agent:

```bash
# Launch minimal instance
aws ec2 run-instances \
  --image-id ami-0c7217cdde317cfec \
  --instance-type t3.micro \
  --key-name your-key-name \
  --security-group-ids sg-xxxxx \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=dagster-batch-agent}]' \
  --region us-east-2
```

### Step 6: Configure Agent for AWS Batch

SSH into the agent instance and configure it:

```bash
ssh -i your-key.pem ubuntu@AGENT_IP

# Install Dagster Cloud CLI
pip3 install dagster-cloud

# Create agent configuration
mkdir -p ~/dagster-agent
cd ~/dagster-agent

cat > dagster.yaml <<EOF
instance_class:
  module: dagster_cloud.instance
  class: DagsterCloudAgentInstance

dagster_cloud_api:
  agent_token: YOUR_DAGSTER_CLOUD_TOKEN
  deployment: prod
  agent_label: batch-ml-agent
  agent_queues:
    - ml-queue

user_code_launcher:
  module: dagster_cloud.workspace.batch
  class: BatchUserCodeLauncher
  config:
    job_queue: dagster-ml-queue
    job_definition: dagster-ml-job
    region: us-east-2
EOF

# Create systemd service (same as EC2 setup)
sudo tee /etc/systemd/system/dagster-agent.service > /dev/null <<EOF
[Unit]
Description=Dagster Cloud Batch Agent
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/dagster-agent
Environment="PATH=/home/ubuntu/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/ubuntu/.local/bin/dagster-cloud agent run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Start agent
sudo systemctl daemon-reload
sudo systemctl enable dagster-agent
sudo systemctl start dagster-agent
```

### Step 7: Update dagster_cloud.yaml

Update your ML location to use the Batch agent:

```yaml
locations:
  # ... core location ...

  - location_name: sbir-analytics-ml
    code_source:
      module_name: src.definitions_ml
    build:
      directory: .
      registry: 123456789012.dkr.ecr.us-east-2.amazonaws.com/dagster-ml-workloads
    agent_queue: ml-queue  # Routes to batch-ml-agent
```

### Step 8: Deploy and Test

```bash
# Push to trigger deployment
git push origin main
```

Then test in Dagster Cloud:
1. Materialize a CET job
2. Check AWS Batch console to see job run
3. Container starts → executes → stops automatically

## Monitoring

### AWS Batch Console

View job status in AWS Batch:
- Submitted → Pending → Runnable → Starting → Running → Succeeded/Failed

### CloudWatch Logs

```bash
# View job logs
aws logs tail /aws/batch/job --follow
```

### Cost Tracking

```bash
# View Batch costs
aws ce get-cost-and-usage \
  --time-period Start=2024-11-01,End=2024-11-30 \
  --granularity MONTHLY \
  --metrics BlendedCost \
  --filter file://filter.json

# filter.json:
{
  "Dimensions": {
    "Key": "SERVICE",
    "Values": ["AWS Batch"]
  }
}
```

## Cost Optimization Tips

### 1. Use Spot Instances (70% savings)

Already configured in the compute environment above. Jobs may be interrupted but will automatically retry.

### 2. Right-Size Instances

Monitor job resource usage and adjust:

```bash
# Update job definition with appropriate resources
aws batch register-job-definition \
  --job-definition-name dagster-ml-job \
  --container-properties vcpus=2,memory=8192  # Smaller if sufficient
```

### 3. Use Reserved Instances for Agent

If agent runs 24/7, buy a reserved t3.micro (40% discount):

```bash
aws ec2 purchase-reserved-instances-offering \
  --instance-count 1 \
  --reserved-instances-offering-id <offering-id>
```

### 4. Schedule Jobs Strategically

Run non-urgent jobs during off-peak hours for better Spot availability.

## Troubleshooting

### Job Stuck in RUNNABLE

**Cause**: No available compute resources
**Fix**: Increase maxvCpus in compute environment or check Spot availability

```bash
aws batch update-compute-environment \
  --compute-environment dagster-ml-spot \
  --compute-resources maxvCpus=512
```

### Job Failing Immediately

**Cause**: Image pull error or IAM permissions
**Fix**: Check CloudWatch logs, verify ECR permissions

```bash
# Allow Batch to pull from ECR
aws ecr get-login-password --region us-east-2 | \
  docker login --username AWS --password-stdin $ECR_URI
```

### High Costs

**Cause**: Jobs not shutting down, on-demand instead of Spot
**Fix**: Verify Spot compute environment, check for stuck jobs

## Comparison: EC2 vs AWS Batch

| Aspect | EC2 Always-On | AWS Batch |
|--------|---------------|-----------|
| **Setup** | Simple | Moderate |
| **Cost (10 jobs/week)** | ~$30/mo | ~$11/mo (with Spot) |
| **Cost (100 jobs/week)** | ~$60/mo | ~$28/mo (with Spot) |
| **Scaling** | Manual | Automatic |
| **Idle cost** | Full instance | Agent only (~$7) |
| **Cold start** | None | ~1-2 min |
| **Spot interruption** | N/A | Auto-retry |
| **Maintenance** | More | Less |

## Next Steps

1. **Monitor costs**: Set up AWS Budgets alert
2. **Optimize resources**: Adjust vCPU/memory per job type
3. **Add more queues**: Separate queues for different job priorities
4. **Enable notifications**: SNS for job failures
5. **Set up auto-scaling**: Configure compute environment scaling policies

## Resources

- AWS Batch Docs: https://docs.aws.amazon.com/batch/
- Dagster Cloud Batch: https://docs.dagster.io/deployment/dagster-plus/deployment/agents/batch
- Spot Instance Best Practices: https://aws.amazon.com/ec2/spot/
