# USAspending Database Download - EC2 Automation

This guide explains how to set up automated monthly downloads of the USAspending database using EC2 and GitHub Actions.

## Overview

The USAspending full database is ~217GB, which exceeds Lambda's 15-minute timeout. This solution uses EC2 to download the database and upload it to S3.

**File Detection:** The workflow automatically checks if a new file is available before downloading, using HTTP HEAD requests to compare Last-Modified dates and file sizes with existing S3 files.

**Architecture:**
- **GitHub Actions** workflow triggers monthly (or manually)
- **EC2 instance** (t3.large) starts, downloads, uploads to S3, then stops
- **AWS Systems Manager (SSM)** executes the download script remotely
- **Cost:** ~$0.21 per download (~$0.84/month if run weekly)

## Prerequisites

1. AWS account with appropriate permissions
2. EC2 instance with SSM agent installed (Amazon Linux 2/2023 includes it by default)
3. IAM role attached to EC2 with S3 write permissions
4. GitHub repository with AWS OIDC configured

## Setup Steps

### 1. Create EC2 Instance

```bash
# Launch EC2 instance (t3.large recommended)
aws ec2 run-instances \
  --image-id ami-0c02fb55956c7d316 \  # Amazon Linux 2023 (us-east-2)
  --instance-type t3.large \
  --iam-instance-profile Name=your-ec2-role \
  --security-group-ids sg-xxx \
  --subnet-id subnet-xxx \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=usaspending-download}]'

# Get the instance ID
INSTANCE_ID=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=usaspending-download" \
  --query 'Reservations[0].Instances[0].InstanceId' \
  --output text)

echo "Instance ID: $INSTANCE_ID"
```

### 2. Create IAM Role for EC2

The EC2 instance needs:
- **S3 write access** to `sbir-etl-production-data` bucket
- **SSM agent permissions** (usually included in `AmazonSSMManagedInstanceCore`)

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:PutObjectAcl",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::sbir-etl-production-data",
        "arn:aws:s3:::sbir-etl-production-data/*"
      ]
    }
  ]
}
```

Attach the role to the instance:
```bash
aws ec2 associate-iam-instance-profile \
  --instance-id $INSTANCE_ID \
  --iam-instance-profile Name=usaspending-download-role
```

### 3. Configure GitHub Secrets

Add the EC2 instance ID to GitHub secrets:  # pragma: allowlist secret

1. Go to GitHub repository → Settings → Secrets and variables → Actions
2. Add secret: `EC2_INSTANCE_ID` = your EC2 instance ID
3. Ensure `AWS_ROLE_ARN` is already configured (for OIDC)

### 4. Test the Workflow

1. Go to Actions → "USAspending Database Download"
2. Click "Run workflow"
3. Select:
   - **Database type:** `test` (for first test, smaller file)
   - **Force refresh:** `false`
4. Monitor the workflow execution

## Workflow Details

### Scheduled Execution

The workflow runs monthly on the 6th at 2 AM UTC:
```yaml
schedule:
  - cron: "0 2 6 * *"
```

### Manual Execution

You can trigger manually with options:
- **Database type:** `full` or `test`
- **Date:** Override date (YYYYMMDD format)
- **Source URL:** Override download URL
- **Force refresh:** Download even if file exists

### What the Workflow Does

1. **Starts EC2 instance** (if stopped)
2. **Uploads download script** via SSM
3. **Executes download** using the script
4. **Monitors progress** (waits up to 3 hours)
5. **Stops EC2 instance** when complete

### Download Script

The script (`scripts/usaspending/download_database.py`):
- Downloads from `https://files.usaspending.gov/database_download/`
- Streams directly to S3 using multipart upload
- Computes SHA256 hash for integrity
- Handles large files efficiently (100MB chunks)

## Cost Breakdown

**Per Download:**
- EC2 t3.large: $0.0832/hour × 2.5 hours = **$0.21**
- S3 storage: ~$0.023/GB/month (first month)
- Data transfer: Free (within same region)

**Monthly (if run weekly):**
- EC2: ~$0.84
- S3 storage: ~$5-10 (depending on retention)

**Annual:**
- EC2: ~$10-12
- S3 storage: ~$60-120 (with lifecycle policies)

## File Detection & Monitoring

### How New Files Are Detected

The workflow includes automatic file detection that runs before each download:

1. **HTTP HEAD Request**: Checks the source URL for file availability
2. **Last-Modified Comparison**: Compares source file's Last-Modified header with S3 file
3. **Size Comparison**: Falls back to Content-Length comparison if Last-Modified unavailable
4. **S3 Lookup**: Finds the most recent file in S3 for the database type

**Detection Script:** `scripts/usaspending/check_new_file.py`

**Usage:**
```bash
# Check if new file is available
python scripts/usaspending/check_new_file.py \
  --database-type full \
  --s3-bucket sbir-etl-production-data

# Output JSON format
python scripts/usaspending/check_new_file.py \
  --database-type full \
  --json
```

### Automated Monitoring Options

#### Option 1: GitHub Actions Workflow (Current)
- **Frequency**: Monthly schedule + manual trigger
- **Detection**: Built into workflow (checks before download)
- **Cost**: Free (GitHub Actions minutes)

#### Option 2: Lambda Function + EventBridge
- **Frequency**: Daily checks (configurable)
- **Detection**: Lambda function checks for new files
- **Auto-trigger**: Can automatically trigger download if new file detected
- **Cost**: ~$0.0000167 per check (negligible)

**Setup Lambda Checker:**
```bash
# Deploy the check Lambda function
cd infrastructure/cdk
# Add to lambda_stack.py layer_functions list:
# "check-usaspending-file"

# Create EventBridge rule for daily checks
aws events put-rule \
  --name usaspending-file-check \
  --schedule-expression "rate(1 day)" \
  --state ENABLED

# Add Lambda as target
aws events put-targets \
  --rule usaspending-file-check \
  --targets "Id=1,Arn=arn:aws:lambda:us-east-2:ACCOUNT:function:sbir-analytics-check-usaspending-file"
```

#### Option 3: Manual Monitoring
- Check USAspending website: https://www.usaspending.gov/data
- Monitor their announcements or RSS feeds
- Use the check script manually when needed

## Troubleshooting

### EC2 Instance Not Starting

**Problem:** Workflow fails to start instance

**Solution:**
- Check IAM role is attached to instance
- Verify instance is in a valid state (not terminated)
- Check security group allows SSM (port 443)

### SSM Command Fails

**Problem:** Script upload or execution fails

**Solution:**
```bash
# Check SSM agent status on instance
aws ssm describe-instance-information \
  --filters "Key=InstanceIds,Values=$INSTANCE_ID"

# Check recent SSM commands
aws ssm list-commands --instance-id $INSTANCE_ID
```

### Download Times Out

**Problem:** Download exceeds 3-hour workflow timeout

**Solution:**
- Increase workflow timeout in `.github/workflows/usaspending-database-download.yml`
- Check network speed (may need larger instance type)
- Verify source URL is accessible

### File Already Exists

**Problem:** Workflow skips download because file exists

**Solution:**
- Use `force_refresh: true` in manual workflow trigger
- Or delete the existing file from S3 first

## Alternative: Lambda Orchestrator

Instead of GitHub Actions, you could use a Lambda function to orchestrate EC2:

```python
# Lambda function that starts EC2, runs SSM command, stops EC2
# Triggered by EventBridge (monthly schedule)
```

This would:
- Reduce GitHub Actions usage
- Centralize automation in AWS
- Cost: ~$0.0000167 per invocation (negligible)

## Monitoring

### CloudWatch Logs

SSM command output is available in CloudWatch:
- Log group: `/aws/ssm/commands`
- Filter by instance ID and command ID

### S3 Verification

After download, verify the file:
```bash
aws s3 ls s3://sbir-etl-production-data/raw/usaspending/database/ --recursive
aws s3 head-object s3://sbir-etl-production-data/raw/usaspending/database/2025-11-20/usaspending-db_20251106.zip
```

## Next Steps

1. Set up EC2 instance and IAM role
2. Add `EC2_INSTANCE_ID` to GitHub secrets
3. Test with `test` database type first
4. Schedule monthly runs or trigger manually as needed
