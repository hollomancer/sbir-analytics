# Multi-Location Deployment Setup Guide

This guide explains how to deploy SBIR Analytics using a multi-location architecture:

1. **sbir-analytics-core** (Serverless) - Lightweight ETL assets
2. **sbir-analytics-ml** (Hybrid/EC2) - Heavy ML workloads

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Dagster Cloud UI                         │
│                  (Orchestration & Monitoring)               │
└──────────────┬─────────────────────────┬────────────────────┘
               │                         │
               │                         │
               ▼                         ▼
┌──────────────────────────┐  ┌──────────────────────────┐
│  sbir-analytics-core     │  │  sbir-analytics-ml       │
│  (Serverless)            │  │  (EC2 Agent)             │
├──────────────────────────┤  ├──────────────────────────┤
│ • SBIR ingestion         │  │ • CET ML training        │
│ • USAspending enrichment │  │ • CET drift detection    │
│ • Neo4j graph loading    │  │ • PaECTER embeddings     │
│ • USPTO data loading     │  │ • Fiscal R analysis      │
│ • Transition analysis    │  │ • spaCy NLP extraction   │
│ • M&A detection          │  │                          │
├──────────────────────────┤  ├──────────────────────────┤
│ ~25 lightweight assets   │  │ ~15 heavy ML assets      │
│ <2 min cold start        │  │ No timeout limits        │
│ $0 idle cost            │  │ ~$15/month EC2           │
└──────────────────────────┘  └──────────────────────────┘
```

## Benefits

| Aspect | Serverless Only | Multi-Location |
|--------|----------------|----------------|
| Timeout | ❌ 10 min limit | ✅ No limit |
| Dependencies | ❌ Size limits | ✅ Unlimited |
| Cost (idle) | $0 | ~$15/month |
| Cold starts | ❌ 7+ min | ✅ <2 min (core) |
| ML workloads | ❌ Fails | ✅ Works |

## Prerequisites

- Dagster Cloud account
- AWS account
- GitHub repository with code
- Basic familiarity with EC2

## Setup Steps

### Step 1: Deploy Core Location (Serverless)

The core location is already configured in `dagster_cloud.yaml`. It will deploy automatically on push to main:

```yaml
- location_name: sbir-analytics-core
  code_source:
    module_name: src.definitions_core  # Lightweight assets only
```

**No action needed** - this deploys via existing GitHub Actions workflow.

### Step 2: Launch EC2 Instance for ML Agent

#### Option A: AWS Console (Easiest)

1. Go to AWS Console → EC2 → Launch Instance
2. Configure:
   - **Name**: dagster-ml-agent
   - **AMI**: Ubuntu Server 24.04 LTS
   - **Instance type**: t3.medium (4GB RAM, 2 vCPU)
   - **Key pair**: Create new or use existing
   - **Storage**: 30 GB gp3
   - **Security group**:
     - SSH (22) from your IP
     - HTTPS (443) outbound (for Dagster Cloud)
     - Docker (2375-2376) internal only

3. Click "Launch Instance"

#### Option B: AWS CLI

```bash
# Create security group
aws ec2 create-security-group \
  --group-name dagster-agent-sg \
  --description "Security group for Dagster ML agent" \
  --vpc-id vpc-xxxxx

# Allow SSH from your IP
aws ec2 authorize-security-group-ingress \
  --group-id sg-xxxxx \
  --protocol tcp \
  --port 22 \
  --cidr YOUR_IP/32

# Launch instance
aws ec2 run-instances \
  --image-id ami-0c7217cdde317cfec \  # Ubuntu 24.04 in us-east-2
  --instance-type t3.medium \
  --key-name your-key-name \
  --security-group-ids sg-xxxxx \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=dagster-ml-agent}]'
```

### Step 3: Install Dagster Agent on EC2

#### Automated Setup (Recommended)

SSH into your EC2 instance and run the setup script:

```bash
# SSH into instance
ssh -i your-key.pem ubuntu@YOUR_EC2_IP

# Download and run setup script
curl -fsSL https://raw.githubusercontent.com/hollomancer/sbir-analytics/main/scripts/setup-ec2-agent.sh -o setup-agent.sh
chmod +x setup-agent.sh
./setup-agent.sh
```

The script will prompt you for:
- Dagster Cloud API Token (from Settings → Tokens)
- Organization name
- Deployment name (default: prod)
- Agent queue name (default: ml-queue)

#### Manual Setup

If you prefer manual setup:

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu
# Log out and back in for group changes

# 2. Install Python and Dagster Cloud CLI
sudo apt-get update
sudo apt-get install -y python3-pip
pip3 install dagster-cloud

# 3. Configure agent
mkdir -p ~/dagster-agent
cd ~/dagster-agent

cat > dagster.yaml <<EOF
instance_class:
  module: dagster_cloud.instance
  class: DagsterCloudAgentInstance

dagster_cloud_api:
  agent_token: YOUR_TOKEN
  deployment: prod
  agent_label: ec2-ml-agent
  agent_queues:
    - ml-queue

user_code_launcher:
  module: dagster_cloud.workspace.docker
  class: DockerUserCodeLauncher
  config:
    networks:
      - dagster-cloud
EOF

# 4. Create Docker network
docker network create dagster-cloud

# 5. Run agent
dagster-cloud agent run
```

### Step 4: Verify Agent is Running

1. Go to Dagster Cloud → Settings → Agents
2. Look for **ec2-ml-agent** with status "Running"
3. Should show queue: **ml-queue**

### Step 5: Deploy ML Location

Push to main branch to trigger deployment:

```bash
git push origin main
```

GitHub Actions will:
1. Build Docker image with ML dependencies
2. Push to GitHub Container Registry
3. Deploy to Dagster Cloud
4. Agent picks up the code location
5. ML assets become available

### Step 6: Test the Setup

In Dagster Cloud UI:

1. **Verify both locations loaded**:
   - Go to Deployment → Code Locations
   - Should see:
     - ✅ sbir-analytics-core (Serverless)
     - ✅ sbir-analytics-ml (Hybrid - ec2-ml-agent)

2. **Test core location** (serverless):
   ```
   Materialize: sbir_ingestion_job
   ```
   Should complete in <5 minutes

3. **Test ML location** (hybrid):
   ```
   Materialize: cet_full_pipeline_job
   ```
   Should run on EC2 agent (no timeout!)

## Cost Breakdown

### Monthly Costs

| Component | Cost | Notes |
|-----------|------|-------|
| Dagster Cloud | Free tier | Up to 1 agent |
| EC2 t3.medium | ~$30 | On-demand 24/7 |
| EC2 t3.small | ~$15 | Sufficient for agent |
| EBS Storage (30GB) | ~$3 | gp3 volume |
| Data transfer | <$1 | Minimal |
| **Total** | **~$15-35/month** | Depending on instance size |

### Cost Optimization

1. **Use t3.small** instead of t3.medium if agent-only (~$15/month)
2. **Use Spot instances** for 70% discount (can be interrupted)
3. **Stop instance** when not using ML jobs (pay only for storage)
4. **Use Reserved Instances** for 1-year commitment (~40% discount)

## Troubleshooting

### Agent not connecting

```bash
# Check agent logs
sudo journalctl -u dagster-agent -f

# Verify API token
cat ~/dagster-agent/dagster.yaml | grep agent_token

# Test connectivity
curl -I https://dagster.cloud
```

### Docker permission denied

```bash
# Add user to docker group
sudo usermod -aG docker $USER
# Log out and back in
```

### ML location timeout

```bash
# Check agent resources
docker stats

# Increase instance size if needed
# t3.medium → t3.large (8GB RAM)
```

### Jobs stuck in queue

1. Verify agent queue matches location:
   - Agent config: `agent_queues: [ml-queue]`
   - Location config: `agent_queue: ml-queue`

2. Check agent is running:
   ```bash
   sudo systemctl status dagster-agent
   ```

## Maintenance

### Update Agent

```bash
pip3 install --upgrade dagster-cloud
sudo systemctl restart dagster-agent
```

### View Logs

```bash
# Real-time logs
sudo journalctl -u dagster-agent -f

# Last 100 lines
sudo journalctl -u dagster-agent -n 100
```

### Backup Configuration

```bash
# Backup agent config
cp ~/dagster-agent/dagster.yaml ~/dagster-agent/dagster.yaml.backup
```

## Next Steps

1. **Set up monitoring**: Add CloudWatch alarms for EC2 health
2. **Enable auto-restart**: Already configured via systemd
3. **Configure AWS credentials**: Add IAM role to EC2 for S3 access
4. **Scale up**: Add more agents for parallel ML job execution
5. **Optimize costs**: Consider Spot instances or smaller instance types

## Support

- Dagster Cloud Docs: https://docs.dagster.io/dagster-cloud
- EC2 Instance Types: https://aws.amazon.com/ec2/instance-types/
- Issues: https://github.com/hollomancer/sbir-analytics/issues
