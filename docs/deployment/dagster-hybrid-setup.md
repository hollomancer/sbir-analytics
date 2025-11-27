# Dagster Cloud Hybrid Setup Guide

This guide explains how to set up Dagster Hybrid deployment to avoid the 10-minute timeout and dependency size limits of Dagster Cloud Serverless.

## What is Dagster Hybrid?

- **Your code runs on your infrastructure** (AWS ECS, EC2, or GitHub Actions)
- **Dagster Cloud provides the UI** and orchestration
- **No timeouts** on code loading
- **No dependency size limits**

## Option A: AWS ECS Fargate (Recommended)

### Prerequisites
- AWS account with ECS permissions
- Dagster Cloud account
- AWS CLI installed locally

### Step 1: Create ECR Repository

```bash
# Create repository for Docker images
aws ecr create-repository \
  --repository-name dagster-sbir-analytics \
  --region us-east-2

# Note the repositoryUri from output
```

### Step 2: Set Up Dagster Cloud Agent in ECS

1. Go to Dagster Cloud → Settings → Agents
2. Click "Add Agent" → "ECS" → "Create Agent"
3. Follow the wizard to:
   - Create ECS cluster (or use existing)
   - Create agent task definition
   - Run agent service

Or use the CLI:

```bash
# Install Dagster Cloud CLI
pip install dagster-cloud

# Create agent
dagster-cloud agent create \
  --name sbir-analytics-agent \
  --type ECS \
  --region us-east-2
```

### Step 3: Configure GitHub Secrets

Add these to your repository secrets (Settings → Secrets and variables → Actions):

```bash
DAGSTER_CLOUD_API_TOKEN  # From Dagster Cloud → Settings → Tokens
AWS_ROLE_ARN             # Already have this
```

### Step 4: Deploy

```bash
# Push to main branch to trigger deployment
git push origin main

# Or trigger manually
gh workflow run deploy-hybrid.yml
```

### Step 5: Monitor

Visit your Dagster Cloud dashboard to see:
- Agent status (should be "Running")
- Code location status (should load successfully)
- No more timeouts! 🎉

---

## Option B: AWS EC2 (More Control)

### Step 1: Launch EC2 Instance

```bash
# Launch Ubuntu instance (t3.medium recommended for heavy workloads)
aws ec2 run-instances \
  --image-id ami-0c55b159cbfafe1f0 \
  --instance-type t3.medium \
  --key-name your-key-name \
  --security-group-ids sg-xxxxx \
  --subnet-id subnet-xxxxx \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=dagster-agent}]'
```

### Step 2: Install Docker and Agent

```bash
# SSH into instance
ssh -i your-key.pem ubuntu@ec2-instance-ip

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Install Dagster Cloud agent
pip3 install dagster-cloud

# Set up agent config
export DAGSTER_CLOUD_API_TOKEN=your_token
dagster-cloud agent start \
  --deployment prod \
  --agent-token $DAGSTER_CLOUD_API_TOKEN
```

### Step 3: Deploy Code

Use the same GitHub Actions workflow from Option A.

---

## Cost Estimates

### ECS Fargate
- **Agent**: ~$15-20/month (0.25 vCPU, 0.5 GB RAM, running 24/7)
- **Job execution**: Pay per second when jobs run
- **Example**: 10 jobs/day, 1 hour each = ~$30/month total

### EC2
- **t3.medium**: ~$30/month (on-demand)
- **t3.small**: ~$15/month (may be sufficient for agent only)
- **Spot instances**: 70% discount (but can be interrupted)

---

## Troubleshooting

### Agent not connecting
```bash
# Check agent logs
dagster-cloud agent logs

# Verify API token
dagster-cloud agent status
```

### Build failing
```bash
# Test Docker build locally
docker build --build-arg BUILD_WITH_R=false -t test .

# Check ECR permissions
aws ecr describe-repositories --region us-east-2
```

### Jobs timing out
- Increase task resources in ECS task definition
- Check CloudWatch logs for errors
- Verify AWS credentials are available in task

---

## Next Steps

1. **Remove serverless config**: Delete `.github/workflows/dagster-cloud-hybrid.yml` if using ECS
2. **Set up monitoring**: Add CloudWatch alarms for agent health
3. **Configure auto-scaling**: Scale ECS tasks based on queue depth
4. **Add secrets management**: Use AWS Secrets Manager for sensitive values
