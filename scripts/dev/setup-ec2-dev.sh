#!/usr/bin/env bash
#
# EC2 Development Environment Setup
#
# Run this on a fresh EC2 instance (Amazon Linux 2023 / Ubuntu 22.04+)
# to bootstrap the containerized SBIR Analytics dev environment.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/hollomancer/sbir-analytics/main/scripts/dev/setup-ec2-dev.sh | bash
#   # or after cloning:
#   ./scripts/dev/setup-ec2-dev.sh
#
set -euo pipefail

REPO_URL="https://github.com/hollomancer/sbir-analytics.git"
INSTALL_DIR="${HOME}/sbir-analytics"
COMPOSE_VERSION="v2.29.1"

echo "=== SBIR Analytics EC2 Dev Setup ==="
echo ""

# --- Detect OS ---
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="${ID}"
else
    OS_ID="unknown"
fi

# --- Install Docker ---
install_docker() {
    if command -v docker &> /dev/null; then
        echo "[OK] Docker already installed: $(docker --version)"
        return
    fi

    echo "[...] Installing Docker"
    case "${OS_ID}" in
        amzn)
            sudo yum install -y docker
            ;;
        ubuntu|debian)
            sudo apt-get update -qq
            sudo apt-get install -y docker.io
            ;;
        *)
            echo "[WARN] Unknown OS '${OS_ID}', attempting generic install"
            curl -fsSL https://get.docker.com | sudo sh
            ;;
    esac

    sudo systemctl enable docker
    sudo systemctl start docker
    sudo usermod -aG docker "${USER}"
    echo "[OK] Docker installed"
}

# --- Install Docker Compose V2 ---
install_compose() {
    if docker compose version &> /dev/null 2>&1; then
        echo "[OK] Docker Compose already installed: $(docker compose version --short 2>/dev/null || echo 'v2')"
        return
    fi

    echo "[...] Installing Docker Compose ${COMPOSE_VERSION}"
    sudo mkdir -p /usr/local/lib/docker/cli-plugins
    sudo curl -SL \
        "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-$(uname -m)" \
        -o /usr/local/lib/docker/cli-plugins/docker-compose
    sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
    echo "[OK] Docker Compose installed"
}

# --- Install supporting tools ---
install_tools() {
    echo "[...] Installing supporting tools"
    case "${OS_ID}" in
        amzn)
            sudo yum install -y git jq htop
            ;;
        ubuntu|debian)
            sudo apt-get install -y git jq htop
            ;;
    esac

    # AWS CLI v2
    if ! command -v aws &> /dev/null; then
        echo "[...] Installing AWS CLI v2"
        curl -sS "https://awscli.amazonaws.com/awscli-exe-linux-$(uname -m).zip" -o /tmp/awscliv2.zip
        unzip -q /tmp/awscliv2.zip -d /tmp
        sudo /tmp/aws/install
        rm -rf /tmp/aws /tmp/awscliv2.zip
    fi
    echo "[OK] Tools installed"
}

# --- Clone or update repo ---
setup_repo() {
    if [ -d "${INSTALL_DIR}/.git" ]; then
        echo "[OK] Repository already cloned at ${INSTALL_DIR}"
        cd "${INSTALL_DIR}"
        git pull --ff-only origin main || true
    else
        echo "[...] Cloning repository"
        git clone "${REPO_URL}" "${INSTALL_DIR}"
        cd "${INSTALL_DIR}"
    fi
}

# --- Create .env ---
create_env() {
    local ENV_FILE="${INSTALL_DIR}/.env"
    if [ -f "${ENV_FILE}" ]; then
        echo "[OK] .env already exists, skipping"
        return
    fi

    echo "[...] Creating .env"
    cat > "${ENV_FILE}" << 'EOF'
# EC2 Development Environment
ENVIRONMENT=dev
COMPOSE_PROFILES=ec2-dev

# DuckDB is the primary data store (no Neo4j required)
# To opt-in to Neo4j, change profile to: ec2-dev,neo4j
# NEO4J_USER=neo4j
# NEO4J_PASSWORD=dev-password

# Dagster
DAGSTER_PORT=3000

# AWS (uses instance role by default)
AWS_DEFAULT_REGION=us-east-2
EOF
    echo "[OK] .env created"
}

# --- Main ---
install_docker
install_compose
install_tools
setup_repo
create_env

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  cd ${INSTALL_DIR}"
echo ""
echo "  # Start dev environment (DuckDB-only, no Neo4j)"
echo "  docker compose --profile ec2-dev up -d --build"
echo ""
echo "  # Or with Neo4j (optional)"
echo "  docker compose --profile ec2-dev --profile neo4j up -d --build"
echo ""
echo "  # Open Dagster UI"
echo "  echo \"http://\$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):3000\""
echo ""
echo "NOTE: If this is the first run, log out and back in"
echo "      so the 'docker' group takes effect."
