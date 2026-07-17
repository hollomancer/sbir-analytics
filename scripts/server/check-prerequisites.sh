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
# Load allowlisted .env.server values as data (never execute the file)
# ---------------------------------------------------------------------------
ENV_FILE="${SERVER_ENV_FILE:-.env.server}"
COMPOSE_FILE="${SERVER_COMPOSE_FILE:-docker-compose.server.yml}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -f "$ENV_FILE" ]; then
  info "Loading environment from $ENV_FILE"
  # shellcheck source=scripts/server/env-file.sh
  . "$SCRIPT_DIR/env-file.sh"
  for key in \
    SERVER_LOOPBACK NEO4J_PASSWORD SBIR_ANALYTICS_API_TOKEN \
    SERVER_DATA_DIR SERVER_REPORTS_DIR SERVER_LOGS_DIR \
    SERVER_ARTIFACTS_DIR SERVER_NEO4J_DIR SERVER_BACKUP_DIR \
    NEO4J_HTTP_PORT NEO4J_BOLT_PORT DAGSTER_PORT \
    SBIR_ANALYTICS_API_PORT; do
    load_env_key "$key"
  done
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

  # Total memory available to the Docker VM (bytes). Stack has ~7 GiB of
  # limits across Neo4j, Dagster, and the API; warn under 8 GiB.
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
    "SERVER_NEO4J_DIR:${SERVER_NEO4J_DIR:-./data/neo4j}" \
    "SERVER_BACKUP_DIR:${SERVER_BACKUP_DIR:-./backups}"; do
    name="${pair%%:*}"
    dir="${pair#*:}"
    if ! path_has_active_external_volume "$dir"; then
      parent=$(volume_root_for_path "$dir" || printf '%s' /Volumes/unknown)
      error "$name points at $dir but $parent is not an active mount."
      continue
    fi
    if [ -d "$dir" ] && [ -w "$dir" ]; then
      success "$name is writable: $dir"
    elif [ ! -e "$dir" ]; then
      error "$name does not exist yet: $dir (create it before server-up)."
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

compose() {
  if [ -f "$ENV_FILE" ]; then
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
  else
    docker compose -f "$COMPOSE_FILE" "$@"
  fi
}

server_service_owns_port() {
  service="$1"
  container_port="$2"
  host_port="$3"
  cid=$(compose --profile server ps --status running -q "$service" 2>/dev/null || true)
  [ -n "$cid" ] || return 1
  docker port "$cid" "${container_port}/tcp" 2>/dev/null | \
    grep -Fqx "127.0.0.1:${host_port}"
}

valid_port() {
  case "$1" in
    ''|*[!0-9]*) return 1 ;;
  esac
  [ "$1" -ge 1 ] && [ "$1" -le 65535 ]
}

check_ports() {
  for pair in \
    "Neo4j HTTP|neo4j|7474|${NEO4J_HTTP_PORT:-7474}" \
    "Neo4j Bolt|neo4j|7687|${NEO4J_BOLT_PORT:-7687}" \
    "Dagster|dagster-webserver|3000|${DAGSTER_PORT:-3000}" \
    "API|analytics-api|${SBIR_ANALYTICS_API_PORT:-8010}|${SBIR_ANALYTICS_API_PORT:-8010}"; do
    label=${pair%%|*}; rest=${pair#*|}
    service=${rest%%|*}; rest=${rest#*|}
    container_port=${rest%%|*}; p=${rest#*|}
    if ! valid_port "$p"; then
      error "$label host port '$p' is not an integer from 1 through 65535."
      continue
    fi
    if port_in_use "$p"; then
      if server_service_owns_port "$service" "$container_port" "$p"; then
        success "$label host port $p is already owned by this server stack."
      else
        error "$label host port $p is already in use."
      fi
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

  if ! command -v python3 >/dev/null 2>&1; then
    error "python3 is required to validate Tailscale Serve ownership safely."
    return
  fi

  # Allow our exact routes (for idempotent restarts), allow free ports, and
  # reject every other mapping or Funnel-enabled route.
  if ! serve_json=$(tailscale serve status --json 2>/dev/null); then
    error "Could not inspect the Tailscale Serve configuration."
    return
  fi
  for pair in \
    "443:http://127.0.0.1:${DAGSTER_PORT:-3000}" \
    "8443:http://127.0.0.1:${SBIR_ANALYTICS_API_PORT:-8010}"; do
    port=${pair%%:*}
    target=${pair#*:}
    if ! state=$(printf '%s' "$serve_json" | \
      python3 "$SCRIPT_DIR/tailscale-route-state.py" "$port" "$target"); then
      error "Tailscale Serve returned invalid JSON."
      return
    fi
    case "$state" in
      free) success "Tailscale Serve port $port is free." ;;
      owned) success "Tailscale Serve port $port already has the expected route." ;;
      *)
        error "Tailscale Serve port $port has a different owner or target."
        error "  Inspect with: tailscale serve status"
        ;;
    esac
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
