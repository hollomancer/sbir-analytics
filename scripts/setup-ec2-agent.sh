#!/bin/bash
#
# Setup script for Dagster Cloud Hybrid Agent on EC2
#
# This script sets up a Dagster Cloud hybrid agent on an EC2 instance to run
# heavy ML workloads (CET training, fiscal analysis, PaECTER embeddings, etc.)
#
# Usage:
#   1. Launch EC2 instance (t3.medium or larger recommended)
#   2. SSH into instance
#   3. Run: curl -fsSL https://raw.githubusercontent.com/YOUR_REPO/main/scripts/setup-ec2-agent.sh | bash
#   4. Or: scp this script to instance and run: bash setup-ec2-agent.sh
#
# Requirements:
#   - Ubuntu 22.04 or 24.04
#   - At least 4 GB RAM (t3.medium recommended)
#   - 20+ GB disk space
#

set -e  # Exit on error

echo "=========================================="
echo "Dagster Cloud Hybrid Agent Setup"
echo "=========================================="

# Check if running as root
if [ "$EUID" -eq 0 ]; then
  echo "Please run as regular user (not root). The script will use sudo when needed."
  exit 1
fi

# Update system
echo "Updating system packages..."
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker
echo "Installing Docker..."
if ! command -v docker &> /dev/null; then
  curl -fsSL https://get.docker.com -o get-docker.sh
  sudo sh get-docker.sh
  sudo usermod -aG docker $USER
  rm get-docker.sh
  echo "Docker installed. You may need to log out and back in for group changes to take effect."
else
  echo "Docker already installed."
fi

# Install Docker Compose
echo "Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
  sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
  sudo chmod +x /usr/local/bin/docker-compose
else
  echo "Docker Compose already installed."
fi

# Install Python and pip
echo "Installing Python 3.11..."
sudo apt-get install -y python3.11 python3.11-venv python3-pip git

# Install Dagster Cloud CLI
echo "Installing Dagster Cloud CLI..."
python3 -m pip install --user dagster-cloud

# Create directory for agent
AGENT_DIR="$HOME/dagster-agent"
mkdir -p $AGENT_DIR
cd $AGENT_DIR

echo ""
echo "=========================================="
echo "Agent Configuration"
echo "=========================================="
echo ""
echo "Please provide the following information from Dagster Cloud:"
echo "(Go to Settings → Agents in your Dagster Cloud dashboard)"
echo ""

read -p "Dagster Cloud API Token: " DAGSTER_CLOUD_API_TOKEN
read -p "Dagster Cloud Organization: " DAGSTER_CLOUD_ORG
read -p "Deployment name (default: prod): " DAGSTER_CLOUD_DEPLOYMENT
DAGSTER_CLOUD_DEPLOYMENT=${DAGSTER_CLOUD_DEPLOYMENT:-prod}
read -p "Agent queue name (default: ml-queue): " AGENT_QUEUE
AGENT_QUEUE=${AGENT_QUEUE:-ml-queue}

# Create agent configuration
echo "Creating agent configuration..."
cat > $AGENT_DIR/dagster.yaml <<EOF
instance_class:
  module: dagster_cloud.instance
  class: DagsterCloudAgentInstance

dagster_cloud_api:
  agent_token: $DAGSTER_CLOUD_API_TOKEN
  deployment: $DAGSTER_CLOUD_DEPLOYMENT
  agent_label: ec2-ml-agent
  agent_queues:
    - $AGENT_QUEUE

user_code_launcher:
  module: dagster_cloud.workspace.docker
  class: DockerUserCodeLauncher
  config:
    networks:
      - dagster-cloud
    env_vars:
      - AWS_REGION=us-east-2
      # Add other environment variables as needed
EOF

# Create systemd service
echo "Creating systemd service..."
sudo tee /etc/systemd/system/dagster-agent.service > /dev/null <<EOF
[Unit]
Description=Dagster Cloud Hybrid Agent
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$AGENT_DIR
Environment="PATH=/home/$USER/.local/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/$USER/.local/bin/dagster-cloud agent run --agent-heartbeat-interval 30
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Create Docker network for agent
echo "Creating Docker network..."
docker network create dagster-cloud 2>/dev/null || echo "Network already exists"

# Enable and start service
echo "Enabling and starting Dagster agent service..."
sudo systemctl daemon-reload
sudo systemctl enable dagster-agent
sudo systemctl start dagster-agent

echo ""
echo "=========================================="
echo "Setup Complete!"
echo "=========================================="
echo ""
echo "Agent is now running as a systemd service."
echo ""
echo "Useful commands:"
echo "  Check status:  sudo systemctl status dagster-agent"
echo "  View logs:     sudo journalctl -u dagster-agent -f"
echo "  Restart:       sudo systemctl restart dagster-agent"
echo "  Stop:          sudo systemctl stop dagster-agent"
echo ""
echo "Next steps:"
echo "1. Go to your Dagster Cloud dashboard"
echo "2. Navigate to Settings → Agents"
echo "3. Verify 'ec2-ml-agent' appears as 'Running'"
echo "4. Deploy your code location to test"
echo ""
