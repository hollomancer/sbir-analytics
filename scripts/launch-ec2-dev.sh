#!/bin/bash
#
# SBIR Analytics — Launch EC2 Dev Environment
#
# Runs locally on your Mac/laptop. Creates an EC2 instance with EBS storage,
# waits for it to be ready, then SSHs in and runs setup-ec2-dev.sh.
#
# PREREQUISITES:
#   - AWS CLI v2 configured (aws configure)
#   - An SSH key pair registered in EC2 (or pass --create-key)
#   - Sufficient IAM permissions: ec2:RunInstances, ec2:CreateVolume,
#     ec2:AttachVolume, ec2:DescribeInstances, ec2:CreateTags, etc.
#
# USAGE:
#   ./scripts/launch-ec2-dev.sh                          # interactive — prompts for key pair
#   ./scripts/launch-ec2-dev.sh --key-name my-key        # specify key pair
#   ./scripts/launch-ec2-dev.sh --key-name my-key \
#     --instance-type m5.2xlarge --volume-size 500       # heavy workloads
#
# OPTIONS:
#   --key-name NAME         EC2 key pair name (required, or use --create-key)
#   --key-file PATH         Path to private key for SSH (default: ~/.ssh/<key-name>.pem)
#   --create-key            Create a new key pair and save to ~/.ssh/
#   --instance-type TYPE    Instance type (default: m5.xlarge)
#   --volume-size GB        EBS data volume size in GB (default: 200)
#   --region REGION         AWS region (default: us-east-2)
#   --ami AMI_ID            Override AMI (default: latest Ubuntu 24.04)
#   --spot                  Use spot instance (default: on-demand)
#   --name NAME             Instance name tag (default: sbir-dev)
#   --tailscale-key KEY     Tailscale auth key (passed to setup script)
#   --no-setup              Skip running setup-ec2-dev.sh after launch
#   --dry-run               Show what would be created without doing it
#
# COST:
#   m5.xlarge on-demand: ~$0.192/hr ($46/mo at 40hr/wk)
#   m5.xlarge spot:      ~$0.08/hr  ($19/mo at 40hr/wk)
#   200GB gp3 EBS:       $16/mo (persists even when instance is stopped)

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────

KEY_NAME=""
KEY_FILE=""
CREATE_KEY=false
INSTANCE_TYPE="m5.xlarge"
VOLUME_SIZE=200
REGION="us-east-2"
AMI_ID=""
USE_SPOT=false
INSTANCE_NAME="sbir-dev"
TAILSCALE_KEY=""
RUN_SETUP=true
DRY_RUN=false

# ── Parse arguments ──────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case $1 in
        --key-name)      KEY_NAME="$2"; shift 2 ;;
        --key-file)      KEY_FILE="$2"; shift 2 ;;
        --create-key)    CREATE_KEY=true; shift ;;
        --instance-type) INSTANCE_TYPE="$2"; shift 2 ;;
        --volume-size)   VOLUME_SIZE="$2"; shift 2 ;;
        --region)        REGION="$2"; shift 2 ;;
        --ami)           AMI_ID="$2"; shift 2 ;;
        --spot)          USE_SPOT=true; shift ;;
        --name)          INSTANCE_NAME="$2"; shift 2 ;;
        --tailscale-key) TAILSCALE_KEY="$2"; shift 2 ;;
        --no-setup)      RUN_SETUP=false; shift ;;
        --dry-run)       DRY_RUN=true; shift ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^#//; s/^ //'
            exit 0
            ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

# ── Preflight checks ────────────────────────────────────────────────────────

if ! command -v aws &>/dev/null; then
    echo "ERROR: AWS CLI not found. Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    exit 1
fi

if ! aws sts get-caller-identity &>/dev/null; then
    echo "ERROR: AWS credentials not configured. Run: aws configure"
    exit 1
fi

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo "AWS Account: $ACCOUNT_ID"
echo "Region:      $REGION"
echo ""

# ── Key pair ─────────────────────────────────────────────────────────────────

if [ "$CREATE_KEY" = true ] && [ -z "$KEY_NAME" ]; then
    KEY_NAME="sbir-dev-$(date +%Y%m%d)"
fi

if [ -z "$KEY_NAME" ]; then
    echo "Available key pairs in $REGION:"
    aws ec2 describe-key-pairs --region "$REGION" \
        --query 'KeyPairs[*].KeyName' --output table
    echo ""
    read -rp "Enter key pair name (--key-name): " KEY_NAME
    if [ -z "$KEY_NAME" ]; then
        echo "ERROR: Key pair name required. Use --key-name or --create-key."
        exit 1
    fi
fi

if [ "$CREATE_KEY" = true ]; then
    KEY_FILE="$HOME/.ssh/${KEY_NAME}.pem"
    if aws ec2 describe-key-pairs --region "$REGION" --key-names "$KEY_NAME" &>/dev/null; then
        echo "Key pair '$KEY_NAME' already exists. Using it."
    else
        echo "Creating key pair: $KEY_NAME"
        aws ec2 create-key-pair --region "$REGION" \
            --key-name "$KEY_NAME" \
            --key-type ed25519 \
            --query 'KeyMaterial' --output text > "$KEY_FILE"
        chmod 600 "$KEY_FILE"
        echo "  Saved: $KEY_FILE"
    fi
fi

if [ -z "$KEY_FILE" ]; then
    # Try common locations
    for candidate in "$HOME/.ssh/${KEY_NAME}.pem" "$HOME/.ssh/${KEY_NAME}" "$HOME/.ssh/${KEY_NAME}.cer"; do
        if [ -f "$candidate" ]; then
            KEY_FILE="$candidate"
            break
        fi
    done
    if [ -z "$KEY_FILE" ]; then
        read -rp "Path to private key for '$KEY_NAME': " KEY_FILE
    fi
fi

if [ ! -f "$KEY_FILE" ]; then
    echo "ERROR: Key file not found: $KEY_FILE"
    exit 1
fi

echo "Key pair:  $KEY_NAME"
echo "Key file:  $KEY_FILE"

# ── AMI lookup ───────────────────────────────────────────────────────────────

if [ -z "$AMI_ID" ]; then
    echo ""
    echo "Finding latest Ubuntu 24.04 LTS AMI..."
    AMI_ID=$(aws ec2 describe-images --region "$REGION" \
        --owners 099720109477 \
        --filters \
            "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" \
            "Name=state,Values=available" \
        --query 'Images | sort_by(@, &CreationDate) | [-1].ImageId' \
        --output text)

    if [ "$AMI_ID" = "None" ] || [ -z "$AMI_ID" ]; then
        echo "ERROR: Could not find Ubuntu 24.04 AMI in $REGION."
        echo "Specify manually with --ami."
        exit 1
    fi
fi

echo "AMI:       $AMI_ID"

# ── Security group ───────────────────────────────────────────────────────────

SG_NAME="sbir-dev-sg"
SG_ID=$(aws ec2 describe-security-groups --region "$REGION" \
    --filters "Name=group-name,Values=$SG_NAME" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo "None")

if [ "$SG_ID" = "None" ] || [ -z "$SG_ID" ]; then
    echo ""
    echo "Creating security group: $SG_NAME"

    # Get default VPC
    VPC_ID=$(aws ec2 describe-vpcs --region "$REGION" \
        --filters "Name=is-default,Values=true" \
        --query 'Vpcs[0].VpcId' --output text)

    if [ "$VPC_ID" = "None" ] || [ -z "$VPC_ID" ]; then
        echo "ERROR: No default VPC found in $REGION. Create one or specify a VPC."
        exit 1
    fi

    SG_ID=$(aws ec2 create-security-group --region "$REGION" \
        --group-name "$SG_NAME" \
        --description "SBIR dev - SSH access" \
        --vpc-id "$VPC_ID" \
        --query 'GroupId' --output text)

    # Allow SSH from current IP
    MY_IP=$(curl -s https://checkip.amazonaws.com)
    aws ec2 authorize-security-group-ingress --region "$REGION" \
        --group-id "$SG_ID" \
        --protocol tcp --port 22 --cidr "${MY_IP}/32"

    echo "  SG: $SG_ID (SSH from $MY_IP)"
else
    echo "Security group: $SG_ID (existing)"
fi

# ── Summary & confirmation ───────────────────────────────────────────────────

echo ""
echo "=========================================="
echo "Launch Configuration"
echo "=========================================="
echo "  Instance:  $INSTANCE_TYPE"
echo "  AMI:       $AMI_ID (Ubuntu 24.04)"
echo "  Region:    $REGION"
echo "  Key:       $KEY_NAME"
echo "  EBS data:  ${VOLUME_SIZE}GB gp3"
echo "  Name:      $INSTANCE_NAME"
echo "  Spot:      $USE_SPOT"
echo "  Setup:     $RUN_SETUP"
echo "=========================================="

if [ "$DRY_RUN" = true ]; then
    echo ""
    echo "[DRY RUN] Would create the above. Exiting."
    exit 0
fi

echo ""
read -rp "Launch? [y/N] " CONFIRM
if [[ ! "$CONFIRM" =~ ^[Yy] ]]; then
    echo "Cancelled."
    exit 0
fi

# ── Launch instance ──────────────────────────────────────────────────────────

echo ""
echo "Launching instance..."

# Build the block device mapping: root (30GB) + data volume
BLOCK_DEVICES=$(cat <<EOF
[
  {
    "DeviceName": "/dev/sda1",
    "Ebs": {
      "VolumeSize": 30,
      "VolumeType": "gp3",
      "DeleteOnTermination": true
    }
  },
  {
    "DeviceName": "/dev/sdf",
    "Ebs": {
      "VolumeSize": $VOLUME_SIZE,
      "VolumeType": "gp3",
      "DeleteOnTermination": false
    }
  }
]
EOF
)

RUN_ARGS=(
    --region "$REGION"
    --image-id "$AMI_ID"
    --instance-type "$INSTANCE_TYPE"
    --key-name "$KEY_NAME"
    --security-group-ids "$SG_ID"
    --block-device-mappings "$BLOCK_DEVICES"
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME}]"
    --query 'Instances[0].InstanceId'
    --output text
)

if [ "$USE_SPOT" = true ]; then
    RUN_ARGS+=(--instance-market-options '{"MarketType":"spot","SpotOptions":{"SpotInstanceType":"persistent","InstanceInterruptionBehavior":"stop"}}')
fi

INSTANCE_ID=$(aws ec2 run-instances "${RUN_ARGS[@]}")

echo "  Instance ID: $INSTANCE_ID"

# Tag the data volume so it's easy to find later
aws ec2 create-tags --region "$REGION" \
    --resources "$INSTANCE_ID" \
    --tags Key=Project,Value=sbir-analytics Key=ManagedBy,Value=launch-ec2-dev

# ── Wait for running ────────────────────────────────────────────────────────

echo "  Waiting for instance to start..."
aws ec2 wait instance-running --region "$REGION" --instance-ids "$INSTANCE_ID"

PUBLIC_IP=$(aws ec2 describe-instances --region "$REGION" \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo "  Public IP: $PUBLIC_IP"

# Tag the data EBS volume
DATA_VOLUME_ID=$(aws ec2 describe-instances --region "$REGION" \
    --instance-ids "$INSTANCE_ID" \
    --query 'Reservations[0].Instances[0].BlockDeviceMappings[?DeviceName==`/dev/sdf`].Ebs.VolumeId' \
    --output text)

if [ -n "$DATA_VOLUME_ID" ] && [ "$DATA_VOLUME_ID" != "None" ]; then
    aws ec2 create-tags --region "$REGION" \
        --resources "$DATA_VOLUME_ID" \
        --tags Key=Name,Value="${INSTANCE_NAME}-data" Key=Project,Value=sbir-analytics
    echo "  Data volume: $DATA_VOLUME_ID (${VOLUME_SIZE}GB, persists on termination)"
fi

# ── Wait for SSH ─────────────────────────────────────────────────────────────

echo "  Waiting for SSH..."
for i in $(seq 1 30); do
    if ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=yes \
        -i "$KEY_FILE" "ubuntu@$PUBLIC_IP" "echo ok" &>/dev/null; then
        break
    fi
    sleep 5
done

if ! ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o BatchMode=yes \
    -i "$KEY_FILE" "ubuntu@$PUBLIC_IP" "echo ok" &>/dev/null; then
    echo "ERROR: Cannot SSH to $PUBLIC_IP after 2.5 minutes."
    echo "  Instance is running ($INSTANCE_ID). Try manually:"
    echo "  ssh -i $KEY_FILE ubuntu@$PUBLIC_IP"
    exit 1
fi

echo "  SSH ready."

# ── Run setup ────────────────────────────────────────────────────────────────

if [ "$RUN_SETUP" = true ]; then
    echo ""
    echo "Running setup-ec2-dev.sh on the instance..."
    echo "=========================================="

    SETUP_ENV=""
    if [ -n "$TAILSCALE_KEY" ]; then
        SETUP_ENV="TAILSCALE_AUTHKEY='$TAILSCALE_KEY'"
    fi

    ssh -o StrictHostKeyChecking=no -i "$KEY_FILE" "ubuntu@$PUBLIC_IP" \
        "$SETUP_ENV curl -fsSL https://raw.githubusercontent.com/hollomancer/sbir-analytics/main/scripts/setup-ec2-dev.sh | bash"
fi

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "=========================================="
echo "Instance Ready"
echo "=========================================="
echo ""
echo "  Instance ID: $INSTANCE_ID"
echo "  Public IP:   $PUBLIC_IP"
echo "  SSH:         ssh -i $KEY_FILE ubuntu@$PUBLIC_IP"
echo ""
echo "  To stop (preserves data):"
echo "    aws ec2 stop-instances --region $REGION --instance-ids $INSTANCE_ID"
echo ""
echo "  To start again:"
echo "    aws ec2 start-instances --region $REGION --instance-ids $INSTANCE_ID"
echo "    # Public IP will change — use Tailscale for stable access"
echo ""
echo "  To terminate (deletes instance, keeps data volume):"
echo "    aws ec2 terminate-instances --region $REGION --instance-ids $INSTANCE_ID"
echo "    # Data volume $DATA_VOLUME_ID persists — reattach to a new instance"
echo ""

# Save instance info for convenience
STATE_FILE="$HOME/.sbir-dev-instance"
cat > "$STATE_FILE" <<EOF
INSTANCE_ID=$INSTANCE_ID
PUBLIC_IP=$PUBLIC_IP
REGION=$REGION
KEY_FILE=$KEY_FILE
DATA_VOLUME_ID=$DATA_VOLUME_ID
INSTANCE_NAME=$INSTANCE_NAME
CREATED=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
echo "Instance info saved to $STATE_FILE"
