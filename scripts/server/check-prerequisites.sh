#!/usr/bin/env sh
# sbir-analytics/scripts/server/check-prerequisites.sh
#
# Preflight checks for the Tailscale-only Mac mini server profile.
#
# Validates, before `make server-up`:
#   * .env.server present and required secrets set (not placeholders)
#   * host bindings are loopback-only (127.0.0.1 / ::1 / localhost)
#   * Docker daemon reachable and has enough memory for the stack
#   * storage directories (external SSD) exist and are writable
#   * host ports for Neo4j / Dagster / API are free
#   * Tailscale is up and logged in
#   * Tailscale Serve does not already map ports 443 or 8443 (no clobber)
#
# Modes:
#   (default)          run every check
#   --bindings-only    only validate loopback bindings + required env
#                      (no Docker/Tailscale needed; used by unit tests)
#
# Env file: reads .env.server from the repo root unless SERVER_ENV_FILE is set.
#
# Exit codes:
#   0  all required checks passed
#   1  one or more required checks failed

set -eu

MODE="all"
if [ "${1:-}" = "--bindings-only" ]; then
  MODE="bindings"
fi

errors=0
warnings=0

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { printf "${BLUE}➤${NC} %s\n" "$1"; }
success() { printf "${GREEN}✓${NC} %s\n" "$1"; }
warn()    { printf "${YELLOW}⚠${NC} %s\n" "$1"; warnings=$((warnings + 1)); }
error()   { printf "${RED}✖${NC} %s\n" "$1"; errors=$((errors + 1)); }

# ---------------------------------------------------------------------------
# Load .env.server (best effort; never abort on a malformed line)
# ---------------------------------------------------------------------------
ENV_FILE="${SERVER_ENV_FILE:-.env.server}"
if [ -f "$ENV_FILE" ]; then
  info "Loading environment from $ENV_FILE"
  set +eu
  # shellcheck disable=SC1090
  . "$ENV_FILE" 2>/dev/null || true
  set -eu
elif [ "$MODE" = "all" ]; then
  error "$ENV_FILE not found. Copy .env.server.example → .env.server first."
fi

# ---------------------------------------------------------------------------
# Loopback binding helpers
# ---------------------------------------------------------------------------
is_loopback() {
  case "$1" in
    127.0.0.1|::1|localhost|127.*) return 0 ;;
    *) return 1 ;;
  esac
}

check_bindings() {
  bind="${SERVER_LOOPBACK:-127.0.0.1}"
  if is_loopback "$bind"; then
    success "Host bind address is loopback: $bind"
  else
    error "SERVER_LOOPBACK='$bind' is not loopback. Refusing non-local exposure."
    error "  Set SERVER_LOOPBACK=127.0.0.1 — Tailscale Serve is the only ingress."
  fi
}

check_required_secrets() {
  # NEO4J_PASSWORD
  if [ -z "${NEO4J_PASSWORD:-}" ]; then
    error "NEO4J_PASSWORD is not set."
  elif [ "${NEO4J_PASSWORD}" = "change_me" ]; then
    error "NEO4J_PASSWORD is still the placeholder 'change_me'."
  else
    success "NEO4J_PASSWORD is set."
  fi

  # API token
  if [ -z "${SBIR_ANALYTICS_API_TOKEN:-}" ]; then
    error "SBIR_ANALYTICS_API_TOKEN is not set (API would refuse to serve)."
  elif printf '%s' "${SBIR_ANALYTICS_API_TOKEN}" | grep -qi 'change_me'; then
    error "SBIR_ANALYTICS_API_TOKEN is still a placeholder. Generate: openssl rand -hex 32"
  else
    success "SBIR_ANALYTICS_API_TOKEN is set."
  fi
}

# ---------------------------------------------------------------------------
# Docker capacity
# ---------------------------------------------------------------------------
check_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    error "Docker CLI not found."
    return
  fi
  if ! docker info >/dev/null 2>&1; then
    error "Docker daemon is not reachable. Start OrbStack/Docker Desktop."
    return
  fi
  success "Docker daemon is reachable."

  # Total memory available to the Docker VM (bytes). Stack needs ~7.25 GiB of
  # limits (Neo4j 2 + daemon 4 + web 0.75 + API 0.5); warn under 8 GiB.
  total_mem=$(docker info --format '{{.MemTotal}}' 2>/dev/null || echo 0)
  if [ "${total_mem:-0}" -gt 0 ]; then
    min_bytes=$((8 * 1024 * 1024 * 1024))
    if [ "$total_mem" -lt "$min_bytes" ]; then
      warn "Docker VM memory is $((total_mem / 1024 / 1024)) MiB; 8192 MiB recommended."
    else
      success "Docker VM memory: $((total_mem / 1024 / 1024)) MiB."
    fi
  fi
}

# ---------------------------------------------------------------------------
# Storage directories (external SSD)
# ---------------------------------------------------------------------------
check_storage() {
  for pair in \
    "SERVER_DATA_DIR:${SERVER_DATA_DIR:-./data}" \
    "SERVER_REPORTS_DIR:${SERVER_REPORTS_DIR:-./reports}" \
    "SERVER_LOGS_DIR:${SERVER_LOGS_DIR:-./logs}" \
    "SERVER_ARTIFACTS_DIR:${SERVER_ARTIFACTS_DIR:-./artifacts}" \
    "SERVER_NEO4J_DIR:${SERVER_NEO4J_DIR:-./data/neo4j}"; do
    name="${pair%%:*}"
    dir="${pair#*:}"
    case "$dir" in
      /Volumes/*)
        parent="/$(printf '%s' "$dir" | cut -d/ -f2)/$(printf '%s' "$dir" | cut -d/ -f3)"
        if [ ! -d "$parent" ]; then
          error "$name points at $dir but the volume $parent is not mounted."
          continue
        fi
        ;;
    esac
    if [ -d "$dir" ] && [ -w "$dir" ]; then
      success "$name is writable: $dir"
    elif [ ! -e "$dir" ]; then
      warn "$name does not exist yet: $dir (create it before server-up)."
    else
      error "$name is not writable: $dir"
    fi
  done
}

# ---------------------------------------------------------------------------
# Host port availability
# ---------------------------------------------------------------------------
port_in_use() {
  p="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1 && return 0
  elif command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "$p" >/dev/null 2>&1 && return 0
  fi
  return 1
}

check_ports() {
  for pair in \
    "Neo4j HTTP:${NEO4J_HTTP_PORT:-7474}" \
    "Neo4j Bolt:${NEO4J_BOLT_PORT:-7687}" \
    "Dagster:${DAGSTER_PORT:-3000}" \
    "API:${SBIR_ANALYTICS_API_PORT:-8010}"; do
    label="${pair%%:*}"
    p="${pair#*:}"
    if port_in_use "$p"; then
      error "$label host port $p is already in use."
    else
      success "$label host port $p is free."
    fi
  done
}

# ---------------------------------------------------------------------------
# Tailscale connectivity + Serve-route conflicts
# ---------------------------------------------------------------------------
check_tailscale() {
  if ! command -v tailscale >/dev/null 2>&1; then
    error "tailscale CLI not found. Install Tailscale and sign in."
    return
  fi
  if ! tailscale status >/dev/null 2>&1; then
    error "Tailscale is not running or not logged in. Run: tailscale up"
    return
  fi
  success "Tailscale is up."

  # Refuse to clobber existing Serve routes on 443 / 8443.
  serve_json="$(tailscale serve status --json 2>/dev/null || echo '')"
  for port in 443 8443; do
    if printf '%s' "$serve_json" | grep -q "\"$port\""; then
      error "Tailscale Serve already maps port $port. Refusing to overwrite it."
      error "  Inspect with: tailscale serve status"
    else
      success "Tailscale Serve port $port is free."
    fi
  done
}

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------
info "Checking Tailscale-only server prerequisites (mode: $MODE)..."
check_bindings
check_required_secrets

if [ "$MODE" = "all" ]; then
  check_docker
  check_storage
  check_ports
  check_tailscale
fi

echo ""
if [ "$errors" -gt 0 ]; then
  error "$errors error(s), $warnings warning(s). Fix the errors above before server-up."
  exit 1
fi
if [ "$warnings" -gt 0 ]; then
  warn "$warnings warning(s). Review them, then proceed with server-up."
fi
success "Server prerequisites look good."
exit 0
