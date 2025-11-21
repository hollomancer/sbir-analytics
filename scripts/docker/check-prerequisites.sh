#!/usr/bin/env sh
# sbir-analytics/scripts/docker/check-prerequisites.sh
#
# Check prerequisites for Docker development setup
# Validates Docker installation, version, daemon status, port availability, and disk space

set -e

errors=0
warnings=0

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() {
  printf "${BLUE}➤${NC} %s\n" "$1"
}

success() {
  printf "${GREEN}✓${NC} %s\n" "$1"
}

warn() {
  printf "${YELLOW}⚠${NC} %s\n" "$1"
  warnings=$((warnings + 1))
}

error() {
  printf "${RED}✖${NC} %s\n" "$1"
  errors=$((errors + 1))
}

info "Checking prerequisites for Docker development setup..."

# Check Docker CLI
if ! command -v docker >/dev/null 2>&1; then
  error "Docker CLI not found"
  echo "  Install from: https://www.docker.com/products/docker-desktop"
else
  docker_version=$(docker --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
  major=$(echo "$docker_version" | cut -d. -f1)
  minor=$(echo "$docker_version" | cut -d. -f2)
  if [ "$major" -lt 20 ] || ([ "$major" -eq 20 ] && [ "$minor" -lt 10 ]); then
    error "Docker version $docker_version is too old (need 20.10+)"
  else
    success "Docker CLI found: $docker_version"
  fi
fi

# Check Docker Compose V2
if ! docker compose version >/dev/null 2>&1; then
  error "Docker Compose V2 not found"
  echo "  Docker Compose V2 should be included with Docker Desktop"
  echo "  For Docker Engine, install: https://docs.docker.com/compose/install/"
else
  compose_version=$(docker compose version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
  success "Docker Compose V2 found: $compose_version"
fi

# Check Docker daemon
if ! docker info >/dev/null 2>&1; then
  error "Docker daemon not running"
  echo "  Start Docker Desktop or run: sudo systemctl start docker (Linux)"
else
  success "Docker daemon is running"
fi

# Check ports (macOS and Linux compatible)
info "Checking port availability..."
for port in 3000 7474 7687; do
  if command -v lsof >/dev/null 2>&1; then
    # macOS/Linux with lsof
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
      warn "Port $port is in use (may cause conflicts)"
      echo "    Check with: lsof -i :$port"
    else
      success "Port $port is available"
    fi
  elif command -v netstat >/dev/null 2>&1; then
    # Linux with netstat
    if netstat -tuln 2>/dev/null | grep -q ":$port "; then
      warn "Port $port is in use (may cause conflicts)"
    else
      success "Port $port is available"
    fi
  else
    warn "Cannot check port $port (lsof/netstat not available)"
  fi
done

# Check disk space (need ~5GB for image + data)
info "Checking disk space..."
if command -v df >/dev/null 2>&1; then
  # Get available space in GB (works on macOS and Linux)
  if [ "$(uname)" = "Darwin" ]; then
    # macOS
    available=$(df -g . | tail -1 | awk '{print $4}')
  else
    # Linux
    available=$(df -BG . | tail -1 | awk '{print $4}' | sed 's/G//')
  fi
  
  if [ "$available" -lt 5 ]; then
    warn "Low disk space: ${available}GB available (recommend 5GB+)"
    echo "    Docker image + data requires ~5GB"
  else
    success "Sufficient disk space: ${available}GB available"
  fi
else
  warn "Cannot check disk space (df not available)"
fi

# Summary
echo ""
if [ $errors -gt 0 ]; then
  error "Prerequisites check failed with $errors error(s)"
  echo ""
  echo "Fix the issues above and run this script again."
  exit 1
elif [ $warnings -gt 0 ]; then
  warn "Prerequisites check passed with $warnings warning(s)"
  echo ""
  echo "You can proceed, but review the warnings above."
  exit 0
else
  success "All prerequisites met!"
  echo ""
  echo "You're ready to run: make docker-build"
  exit 0
fi

