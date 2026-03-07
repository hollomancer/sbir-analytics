#!/bin/bash
#
# SBIR Analytics — EC2 Development Environment Setup
#
# Converts an EC2 instance into a full dev environment for sbir-analytics.
# Includes Tailscale for secure mesh networking — access Dagster, Neo4j, etc.
# from any device on your tailnet without SSH tunnels or public IPs.
#
# RECOMMENDED INSTANCE:
#   m5.xlarge  (4 vCPU, 16GB) — standard dev. ~$0.08/hr spot.
#   m5.2xlarge (8 vCPU, 32GB) — USPTO bulk, concurrent loads. ~$0.15/hr spot.
#
# RECOMMENDED STORAGE:
#   200GB gp3 EBS ($0.08/GB/mo = $16/mo). Persists across stop/start.
#
# USAGE:
#   1. Launch EC2 (Ubuntu 24.04, m5.xlarge, us-east-2)
#   2. Attach 200GB gp3 EBS volume
#   3. SSH in:
#      curl -fsSL https://raw.githubusercontent.com/hollomancer/sbir-analytics/main/scripts/setup-ec2-dev.sh | bash
#
#   Optional env vars:
#     TAILSCALE_AUTHKEY=tskey-auth-...  Pre-auth key (skips interactive login)
#     TAILSCALE_HOSTNAME=sbir-dev       Custom hostname on your tailnet
#     IDLE_TIMEOUT=30                   Minutes before auto-stop (0 to disable)
#     EBS_DEVICE=/dev/nvme1n1           Explicit EBS device (default: auto-detect)
#     AWS_REGION=us-east-2              AWS region for CLI config
#
# COST (~40 hrs/week): $35-40/mo spot, $50-65/mo on-demand (includes EBS)

set -euo pipefail

EBS_DEVICE="${EBS_DEVICE:-auto}"
DATA_DIR="/data"
REPO_URL="https://github.com/hollomancer/sbir-analytics.git"
REPO_DIR="$DATA_DIR/sbir-analytics"
IDLE_TIMEOUT="${IDLE_TIMEOUT:-30}"
AWS_REGION="${AWS_REGION:-us-east-2}"
PYTHON_VERSION="3.11"
TAILSCALE_HOSTNAME="${TAILSCALE_HOSTNAME:-sbir-dev}"
TAILSCALE_AUTHKEY="${TAILSCALE_AUTHKEY:-}"

echo "=========================================="
echo "SBIR Analytics — EC2 Dev Environment Setup"
echo "=========================================="

if [ "$EUID" -eq 0 ]; then
    echo "ERROR: Run as regular user, not root."
    exit 1
fi

echo "Instance: $(curl -s http://169.254.169.254/latest/meta-data/instance-type 2>/dev/null || echo 'unknown')"
echo "Memory:   $(free -h | awk '/^Mem:/ {print $2}')"
echo ""

# [1/10] System packages
echo "[1/10] System packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    build-essential git curl wget unzip jq htop tmux tree \
    software-properties-common python3-dev libffi-dev libssl-dev pkg-config \
    > /dev/null

# [2/10] Python + uv
echo "[2/10] Python $PYTHON_VERSION + uv..."
sudo add-apt-repository -y ppa:deadsnakes/ppa > /dev/null 2>&1
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev \
    > /dev/null

if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    export PATH="$HOME/.local/bin:$PATH"
fi

# [3/10] Docker
echo "[3/10] Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sudo sh > /dev/null 2>&1
    sudo usermod -aG docker "$USER"
fi
sudo apt-get install -y -qq docker-compose-plugin > /dev/null 2>&1 || true

# [4/10] Node.js 20 (docx generation, Claude Code)
echo "[4/10] Node.js..."
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - > /dev/null 2>&1
    sudo apt-get install -y -qq nodejs > /dev/null
fi
sudo npm install -g docx > /dev/null 2>&1 || true

# [5/10] Tailscale — mesh VPN for direct access without SSH tunnels
echo "[5/10] Tailscale..."
if ! command -v tailscale &> /dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
fi

# Start tailscaled if not already running
if ! systemctl is-active --quiet tailscaled 2>/dev/null; then
    sudo systemctl enable --now tailscaled
fi

# Connect to tailnet
if ! tailscale status &>/dev/null; then
    TS_ARGS="--hostname=$TAILSCALE_HOSTNAME"
    if [ -n "$TAILSCALE_AUTHKEY" ]; then
        sudo tailscale up $TS_ARGS --authkey="$TAILSCALE_AUTHKEY"
        echo "  Connected with auth key."
    else
        echo ""
        echo "  *** Tailscale needs authentication. ***"
        echo "  A login URL will appear below — open it in your browser."
        echo "  (To skip this next time, set TAILSCALE_AUTHKEY=tskey-auth-...)"
        echo ""
        sudo tailscale up $TS_ARGS
    fi
else
    echo "  Already connected."
fi

TS_IP=$(tailscale ip -4 2>/dev/null || echo "")
TS_FQDN=$(tailscale status --json 2>/dev/null | jq -r '.Self.DNSName // empty' | sed 's/\.$//' || echo "")
echo "  Tailscale IP:   ${TS_IP:-pending}"
echo "  Tailscale FQDN: ${TS_FQDN:-pending}"

# [6/10] AWS CLI v2
echo "[6/10] AWS CLI..."
if ! command -v aws &> /dev/null; then
    cd /tmp
    curl -sS "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
    unzip -qq awscliv2.zip
    sudo ./aws/install > /dev/null
    rm -rf aws awscliv2.zip
    cd ~
fi

mkdir -p ~/.aws
cat > ~/.aws/config << EOF
[default]
region = $AWS_REGION
output = json
EOF

# [7/10] EBS volume — persistent data storage
echo "[7/10] Persistent storage at $DATA_DIR..."

if [ "$EBS_DEVICE" = "auto" ]; then
    ROOT_DEVICE=$(findmnt -n -o SOURCE / | sed 's/[0-9]*$//' | sed 's/p$//')
    EBS_DEVICE=$(lsblk -dpno NAME,TYPE | grep disk | awk '{print $1}' | while read dev; do
        if [[ "$dev" != "$ROOT_DEVICE"* ]]; then
            if ! findmnt -rno SOURCE "$dev"* > /dev/null 2>&1; then
                echo "$dev"
                break
            fi
        fi
    done)

    if [ -z "$EBS_DEVICE" ]; then
        echo "  No EBS volume found. Using local storage (non-persistent)."
        echo "  To add later: EBS_DEVICE=/dev/nvme1n1 bash setup-ec2-dev.sh"
        sudo mkdir -p "$DATA_DIR"
        sudo chown "$USER":"$USER" "$DATA_DIR"
    fi
fi

if [ -n "$EBS_DEVICE" ] && [ "$EBS_DEVICE" != "auto" ]; then
    echo "  EBS: $EBS_DEVICE"
    # Format only if no filesystem (preserves data on re-runs)
    if ! sudo blkid "$EBS_DEVICE" > /dev/null 2>&1; then
        echo "  Formatting as ext4..."
        sudo mkfs.ext4 -q "$EBS_DEVICE"
    fi
    sudo mkdir -p "$DATA_DIR"
    mountpoint -q "$DATA_DIR" || sudo mount "$EBS_DEVICE" "$DATA_DIR"
    sudo chown "$USER":"$USER" "$DATA_DIR"

    # Auto-mount on reboot
    UUID=$(sudo blkid -s UUID -o value "$EBS_DEVICE")
    grep -q "$UUID" /etc/fstab || \
        echo "UUID=$UUID $DATA_DIR ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab > /dev/null
    echo "  Mounted ($(df -h "$DATA_DIR" | awk 'NR==2 {print $2}') total)"
fi

# Data directories matching mission-specs.md source registry
mkdir -p "$DATA_DIR"/{raw,processed,models,neo4j-data}
mkdir -p "$DATA_DIR/raw"/{sbir,fpds,uspto,sam-gov,usaspending,bea,stateio,irs-soi,patentsview,census-cbp}

echo "  /data/raw/{sbir,fpds,uspto,sam-gov,...}  bulk downloads by source"
echo "  /data/processed/                         DuckDB, enriched parquet"
echo "  /data/models/                            PaECTER, CET classifier"

# [8/10] Repo + dependencies
echo "[8/10] sbir-analytics..."

# SSH key for GitHub push
if [ ! -f ~/.ssh/id_ed25519 ]; then
    ssh-keygen -t ed25519 -C "sbir-dev-ec2" -f ~/.ssh/id_ed25519 -N ""
    echo "  SSH key generated: cat ~/.ssh/id_ed25519.pub -> GitHub"
fi

if [ -d "$REPO_DIR" ]; then
    cd "$REPO_DIR" && git pull --ff-only 2>/dev/null || true
else
    git clone "$REPO_URL" "$REPO_DIR" && cd "$REPO_DIR"
fi

# Symlink data dirs into repo so project code finds them
mkdir -p "$REPO_DIR/data" 2>/dev/null || true
ln -sfn "$DATA_DIR/raw" "$REPO_DIR/data/raw" 2>/dev/null || true
ln -sfn "$DATA_DIR/processed" "$REPO_DIR/data/processed" 2>/dev/null || true
ln -sfn "$DATA_DIR/models" "$REPO_DIR/data/models" 2>/dev/null || true

# Install dependencies
cd "$REPO_DIR"
if [ -f "uv.lock" ]; then
    uv sync 2>/dev/null || {
        uv venv .venv --python "python${PYTHON_VERSION}" 2>/dev/null || true
        uv pip install -r requirements.txt 2>/dev/null || true
    }
elif [ -f "requirements.txt" ]; then
    uv venv .venv --python "python${PYTHON_VERSION}" 2>/dev/null || true
    uv pip install -r requirements.txt 2>/dev/null || true
fi

# [9/10] Auto-stop — saves money when you walk away
echo "[9/10] Auto-stop (${IDLE_TIMEOUT}min idle)..."

if [ "$IDLE_TIMEOUT" -gt 0 ]; then

    sudo tee /usr/local/bin/auto-stop.sh > /dev/null << 'AUTOSTOP'
#!/bin/bash
# Stop (not terminate) EC2 after idle timeout.
# Checks: SSH sessions, Python/Dagster processes, Docker containers, tmux.
# EBS volume and all data persist across stop/start cycles.
IDLE_TIMEOUT_MINUTES=${1:-30}
STATE_FILE="/tmp/auto-stop-last-active"

SSH=$(who | grep -c "pts/" 2>/dev/null || echo 0)
PY=$(pgrep -c -f "python|dagster|uvicorn|jupyter" 2>/dev/null || echo 0)
DOCK=$(docker ps -q 2>/dev/null | wc -l || echo 0)
TMUX=$(tmux list-sessions 2>/dev/null | wc -l || echo 0)

if [ $((SSH + PY + DOCK + TMUX)) -gt 0 ]; then
    date +%s > "$STATE_FILE"; exit 0
fi
[ ! -f "$STATE_FILE" ] && date +%s > "$STATE_FILE" && exit 0

IDLE=$(( $(date +%s) - $(cat "$STATE_FILE") ))
if [ "$IDLE" -ge $((IDLE_TIMEOUT_MINUTES * 60)) ]; then
    logger "auto-stop: Idle ${IDLE_TIMEOUT_MINUTES}+min. Stopping."
    sudo shutdown -h now
fi
AUTOSTOP

    sudo chmod +x /usr/local/bin/auto-stop.sh
    (crontab -l 2>/dev/null | grep -v auto-stop; \
     echo "*/5 * * * * /usr/local/bin/auto-stop.sh $IDLE_TIMEOUT") | crontab -
    echo "  ON: stops after ${IDLE_TIMEOUT}min idle."
fi

# [10/10] Shell environment
echo "[10/10] Shell config..."

if ! grep -q "SBIR Analytics Dev" ~/.bashrc 2>/dev/null; then
cat >> ~/.bashrc << 'BASHRC'

# --- SBIR Analytics Dev Environment ---
export PATH="$HOME/.local/bin:$PATH"
export DATA_DIR="/data"
export SBIR_REPO="/data/sbir-analytics"

alias sb='cd $SBIR_REPO'
alias sbd='cd $DATA_DIR'
alias dagdev='cd $SBIR_REPO && uv run dagster dev -h 0.0.0.0'
alias datasize='du -sh $DATA_DIR/raw/*/ $DATA_DIR/processed/* 2>/dev/null | sort -rh'
alias diskfree='df -h /data'
alias stay-awake='date +%s > /tmp/auto-stop-last-active && echo "Timer reset"'
alias gs='git status'
alias gd='git diff'
alias gl='git log --oneline -20'
alias tsip='tailscale ip -4'
alias tsurl='echo "http://$(tailscale status --json | jq -r ".Self.DNSName" | sed "s/\.$//")"'

echo "  SBIR Dev | $(df -h /data 2>/dev/null | awk 'NR==2{print $3"/"$2}' || echo 'no EBS') disk | $(free -h | awk '/Mem:/{print $3"/"$2}') mem | ts: $(tailscale ip -4 2>/dev/null || echo 'off')"
# --- end SBIR ---
BASHRC
fi

cat > ~/.tmux.conf << 'TMUX'
set -g mouse on
set -g history-limit 50000
set -g default-terminal "screen-256color"
bind | split-window -h -c "#{pane_current_path}"
bind - split-window -v -c "#{pane_current_path}"
TMUX

git config --global init.defaultBranch main
git config --global pull.ff only

# ============================================================================
# DONE
# ============================================================================

IP=$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4 2>/dev/null || echo '<ip>')
TS_IP=$(tailscale ip -4 2>/dev/null || echo '<tailscale-ip>')
TS_FQDN=$(tailscale status --json 2>/dev/null | jq -r '.Self.DNSName // empty' | sed 's/\.$//' || echo '<hostname>.tail<xxxxx>.ts.net')

echo ""
echo "=========================================="
echo "Setup Complete"
echo "=========================================="
echo ""
echo "TAILSCALE (preferred — no SSH tunnels needed):"
echo ""
echo "  Tailscale IP:   $TS_IP"
echo "  Tailscale FQDN: $TS_FQDN"
echo ""
echo "  From any device on your tailnet:"
echo "    Dagster UI:    http://$TS_FQDN:3000"
echo "    Neo4j Browser: http://$TS_FQDN:7474"
echo "    Neo4j Bolt:    bolt://$TS_FQDN:7687"
echo ""
echo "  VS Code Remote-SSH (via Tailscale):"
echo ""
echo "    Host sbir-dev"
echo "      HostName $TS_FQDN"
echo "      User $USER"
echo "      ForwardAgent yes"
echo ""
echo "SSH FALLBACK — add to ~/.ssh/config on your Mac:"
echo ""
echo "  Host sbir-dev-ec2"
echo "    HostName $IP"
echo "    User $USER"
echo "    IdentityFile ~/.ssh/<your-key>.pem"
echo "    ForwardAgent yes"
echo "    LocalForward 3000 localhost:3000"
echo "    LocalForward 7474 localhost:7474"
echo "    LocalForward 7687 localhost:7687"
echo ""
echo "COMMANDS:"
echo "  sb              cd to repo"
echo "  dagdev          Dagster dev server (:3000)"
echo "  datasize        data directory sizes"
echo "  diskfree        EBS free space"
echo "  stay-awake      reset auto-stop timer"
echo "  tsip            show Tailscale IP"
echo "  tsurl           show Tailscale base URL"
echo ""
echo "NEXT STEPS:"
echo "  1. aws configure                     (or attach IAM role)"
echo "  2. cat ~/.ssh/id_ed25519.pub         (add to GitHub)"
echo "  3. git remote set-url origin git@github.com:hollomancer/sbir-analytics.git"
echo "  4. aws s3 sync s3://<bucket>/raw/ /data/raw/"
echo "  5. npm install -g @anthropic-ai/claude-code && cd $REPO_DIR && claude"
echo ""
echo "PORTS (accessible via Tailscale — no tunnels needed):"
echo "  3000  Dagster UI"
echo "  7474  Neo4j Browser"
echo "  7687  Neo4j Bolt"
echo ""
