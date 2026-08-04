#!/usr/bin/env sh
# Manage the tailnet-only routes for the Mac mini server profile.

set -eu

ENV_FILE="${SERVER_ENV_FILE:-.env.server}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=scripts/server/env-file.sh
. "$SCRIPT_DIR/env-file.sh"
load_env_key DAGSTER_PORT
load_env_key NEO4J_BOLT_PORT
load_env_key NEO4J_TAILNET_BOLT_ENABLED
load_env_key NEO4J_TAILNET_BOLT_PORT

DAGSTER_PORT="${DAGSTER_PORT:-3000}"
NEO4J_BOLT_PORT="${NEO4J_BOLT_PORT:-7687}"
NEO4J_TAILNET_BOLT_ENABLED="${NEO4J_TAILNET_BOLT_ENABLED:-false}"
NEO4J_TAILNET_BOLT_PORT="${NEO4J_TAILNET_BOLT_PORT:-17687}"
DAGSTER_TARGET="http://127.0.0.1:${DAGSTER_PORT}"
LEGACY_API_TARGET="http://127.0.0.1:8010"
NEO4J_TARGET="127.0.0.1:${NEO4J_BOLT_PORT}"
STATE_HELPER="$SCRIPT_DIR/tailscale-route-state.py"
MUTATION_OUTPUT=""
LAST_MUTATION_OUTPUT=""
PENDING_PORT=""
PENDING_TARGET=""
PENDING_TLS_HOST=""
CREATED_443=0
CREATED_NEO4J=0
ROLLBACK_ON_EXIT=0

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { printf "${BLUE}➤${NC} %s\n" "$1"; }
success() { printf "${GREEN}✓${NC} %s\n" "$1"; }
warn()    { printf "${YELLOW}⚠${NC} %s\n" "$1"; }
error()   { printf "${RED}✖${NC} %s\n" "$1" >&2; }

cleanup_mutation() {
  [ -z "$MUTATION_OUTPUT" ] || rm -f "$MUTATION_OUTPUT"
  MUTATION_OUTPUT=""
}

cleanup_all() {
  cleanup_exit_status=$?
  trap - EXIT HUP INT TERM
  set +e
  cleanup_mutation
  if [ "$ROLLBACK_ON_EXIT" -eq 1 ]; then
    rollback_transaction
  fi
  exit "$cleanup_exit_status"
}
trap cleanup_all EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

require_tailscale() {
  if ! command -v tailscale >/dev/null 2>&1; then
    error "tailscale CLI not found. Install Tailscale and sign in."
    exit 1
  fi
  if ! command -v python3 >/dev/null 2>&1; then
    error "python3 is required for safe Tailscale Serve route inspection."
    exit 1
  fi
  if ! tailscale status >/dev/null 2>&1; then
    error "Tailscale is not running or not logged in. Run: tailscale up"
    exit 1
  fi
}

neo4j_tailnet_enabled() {
  case "$NEO4J_TAILNET_BOLT_ENABLED" in
    1|true|TRUE|yes|YES) return 0 ;;
    0|false|FALSE|no|NO) return 1 ;;
    *)
      error "NEO4J_TAILNET_BOLT_ENABLED must be true or false."
      exit 2
      ;;
  esac
}

validate_neo4j_tailnet_port() {
  case "$NEO4J_TAILNET_BOLT_PORT" in
    ''|*[!0-9]*|??????*)
      error "NEO4J_TAILNET_BOLT_PORT must be an integer between 1 and 65535."
      exit 2
      ;;
  esac
  if [ "$NEO4J_TAILNET_BOLT_PORT" -lt 1 ] || [ "$NEO4J_TAILNET_BOLT_PORT" -gt 65535 ]; then
    error "NEO4J_TAILNET_BOLT_PORT must be an integer between 1 and 65535."
    exit 2
  fi
  if [ "$NEO4J_TAILNET_BOLT_PORT" -eq 443 ]; then
    error "NEO4J_TAILNET_BOLT_PORT must not conflict with managed Serve port 443."
    exit 2
  fi
}

tailscale_dns_name() {
  tailscale status --json 2>/dev/null | python3 -c '
import json, sys
print(json.load(sys.stdin).get("Self", {}).get("DNSName", "").rstrip("."))
'
}

route_state() {
  port="$1"
  target="$2"
  tls_host="${3:-}"
  if ! json=$(tailscale serve status --json 2>/dev/null); then
    error "Could not inspect the current Tailscale Serve configuration."
    return 1
  fi
  if [ -n "$tls_host" ]; then
    printf '%s' "$json" | python3 "$STATE_HELPER" "$port" "$target" "$tls_host"
  else
    printf '%s' "$json" | python3 "$STATE_HELPER" "$port" "$target"
  fi
}

run_tailscale_mutation() {
  timeout="${TAILSCALE_SERVE_TIMEOUT:-15}"
  case "$timeout" in
    ''|*[!0-9]*) error "TAILSCALE_SERVE_TIMEOUT must be a positive integer."; return 2 ;;
  esac
  [ "$timeout" -gt 0 ] || { error "TAILSCALE_SERVE_TIMEOUT must be positive."; return 2; }

  LAST_MUTATION_OUTPUT=""
  MUTATION_OUTPUT=$(mktemp "${TMPDIR:-/tmp}/sbir-tailscale-serve.XXXXXX")
  if python3 - "$timeout" "$MUTATION_OUTPUT" tailscale "$@" <<'PY'
import subprocess
import sys

timeout = int(sys.argv[1])
output_path = sys.argv[2]
command = sys.argv[3:]

with open(output_path, "wb") as output:
    try:
        result = subprocess.run(
            command,
            stdout=output,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(124)

raise SystemExit(result.returncode)
PY
  then
    status=0
  else
    status=$?
  fi
  LAST_MUTATION_OUTPUT=$(cat "$MUTATION_OUTPUT")
  cleanup_mutation
  if [ "$status" -eq 124 ]; then
    [ -z "$LAST_MUTATION_OUTPUT" ] || printf '%s\n' "$LAST_MUTATION_OUTPUT" >&2
    error "Tailscale Serve did not finish within ${timeout}s."
    error "If HTTPS consent is pending, enable it using the URL above and rerun."
  else
    [ -z "$LAST_MUTATION_OUTPUT" ] || printf '%s\n' "$LAST_MUTATION_OUTPUT"
  fi
  return "$status"
}

configure_route() {
  port="$1"
  target="$2"
  PENDING_PORT="$port"
  PENDING_TARGET="$target"
  if ! run_tailscale_mutation serve --yes --bg "--https=$port" "$target"; then
    case "$LAST_MUTATION_OUTPUT" in
      *"Serve is not enabled"*|*"serve is not enabled"*)
        error "Enable Tailscale Serve HTTPS using the consent URL above, then rerun this command."
        ;;
    esac
    return 1
  fi

  state=$(route_state "$port" "$target") || return 1
  if [ "$state" != "owned" ]; then
    error "Tailscale did not install the expected HTTPS $port route."
    return 1
  fi
  CREATED_443=1
  PENDING_PORT=""
  PENDING_TARGET=""
}

configure_neo4j_route() {
  port="$1"
  target="$2"
  tls_host="$3"
  PENDING_PORT="$port"
  PENDING_TARGET="$target"
  PENDING_TLS_HOST="$tls_host"
  if ! run_tailscale_mutation serve --yes --bg "--tls-terminated-tcp=$port" "tcp://$target"; then
    return 1
  fi

  state=$(route_state "$port" "$target" "$tls_host") || return 1
  if [ "$state" != "owned" ]; then
    error "Tailscale did not install the expected TLS/TCP $port route."
    return 1
  fi
  CREATED_NEO4J=1
  PENDING_PORT=""
  PENDING_TARGET=""
  PENDING_TLS_HOST=""
}

remove_owned_route() {
  port="$1"
  target="$2"
  tls_host="${3:-}"
  state=$(route_state "$port" "$target" "$tls_host") || return 1
  if [ "$state" != "owned" ]; then
    error "Serve port $port changed ownership; refusing to remove it."
    return 1
  fi
  if [ -n "$tls_host" ]; then
    run_tailscale_mutation serve --yes "--tls-terminated-tcp=$port" off || return 1
  else
    run_tailscale_mutation serve --yes "--https=$port" off || return 1
  fi
  state=$(route_state "$port" "$target" "$tls_host") || return 1
  if [ "$state" != "free" ]; then
    error "Serve port $port was not removed cleanly."
    return 1
  fi
}

rollback_expected_route() {
  port="$1"
  target="$2"
  tls_host="${3:-}"
  if ! state=$(route_state "$port" "$target" "$tls_host"); then
    warn "Could not inspect Serve port $port during rollback; inspect it manually."
    return 1
  fi
  case "$state" in
    owned)
      warn "Rolling back the newly-created Serve port $port route."
      remove_owned_route "$port" "$target" "$tls_host" || {
        warn "Could not roll back Serve port $port; inspect it manually."
        return 1
      }
      ;;
    free) ;;
    *) warn "Serve port $port changed after creation; leaving it untouched." ;;
  esac
}

rollback_transaction() {
  # Disable recursive rollback before issuing any further Tailscale commands.
  ROLLBACK_ON_EXIT=0
  if [ -n "$PENDING_PORT" ]; then
    rollback_expected_route "$PENDING_PORT" "$PENDING_TARGET" "$PENDING_TLS_HOST" || true
    PENDING_PORT=""
    PENDING_TARGET=""
    PENDING_TLS_HOST=""
  fi
  if [ "$CREATED_NEO4J" -eq 1 ]; then
    rollback_expected_route "$NEO4J_TAILNET_BOLT_PORT" "$NEO4J_TARGET" "$NEO4J_TLS_HOST" || true
    CREATED_NEO4J=0
  fi
  if [ "$CREATED_443" -eq 1 ]; then
    rollback_expected_route 443 "$DAGSTER_TARGET" || true
    CREATED_443=0
  fi
}

cmd_up() {
  require_tailscale
  validate_neo4j_tailnet_port
  NEO4J_TLS_HOST=$(tailscale_dns_name || true)
  if [ -z "$NEO4J_TLS_HOST" ]; then
    error "Could not determine this node's Tailscale DNS name for Neo4j TLS."
    exit 1
  fi
  state_443=$(route_state 443 "$DAGSTER_TARGET") || exit 1
  state_legacy_8443=$(route_state 8443 "$LEGACY_API_TARGET") || exit 1
  state_neo4j=$(
    route_state "$NEO4J_TAILNET_BOLT_PORT" "$NEO4J_TARGET" "$NEO4J_TLS_HOST"
  ) || exit 1
  enable_neo4j=0
  if neo4j_tailnet_enabled; then
    enable_neo4j=1
  fi

  if [ "$state_443" = "occupied" ]; then
    error "Serve port 443 has a different owner or target; refusing to overwrite it."
    error "Inspect with: tailscale serve status"
    exit 1
  fi
  case "$state_legacy_8443" in
    owned)
      remove_owned_route 8443 "$LEGACY_API_TARGET"
      success "Removed the retired analytics API route on HTTPS 8443."
      ;;
    occupied)
      warn "Serve port 8443 has another target; leaving it untouched."
      ;;
  esac
  if [ "$state_neo4j" = "occupied" ]; then
    error "Serve port $NEO4J_TAILNET_BOLT_PORT has a different owner or target."
    error "Inspect with: tailscale serve status"
    exit 1
  fi
  if [ "$enable_neo4j" -eq 0 ]; then
    if [ "$state_neo4j" = "owned" ]; then
      remove_owned_route "$NEO4J_TAILNET_BOLT_PORT" "$NEO4J_TARGET" "$NEO4J_TLS_HOST"
      success "Removed the disabled Neo4j TLS/TCP route."
    fi
    state_neo4j="disabled"
  fi

  ROLLBACK_ON_EXIT=1
  if [ "$state_443" = "free" ]; then
    info "Configuring HTTPS 443 -> $DAGSTER_TARGET..."
    configure_route 443 "$DAGSTER_TARGET" || exit 1
  else
    success "HTTPS 443 already has the expected Dagster route."
  fi

  if [ "$state_neo4j" = "disabled" ]; then
    info "Neo4j tailnet access is disabled in $ENV_FILE."
  elif [ "$state_neo4j" = "free" ]; then
    warn "Confirm the group:sbir-neo4j-operators Tailscale grant is active before exposing Bolt."
    info "Configuring TLS/TCP $NEO4J_TAILNET_BOLT_PORT -> $NEO4J_TARGET..."
    configure_neo4j_route "$NEO4J_TAILNET_BOLT_PORT" "$NEO4J_TARGET" "$NEO4J_TLS_HOST" || exit 1
  else
    success "TLS/TCP $NEO4J_TAILNET_BOLT_PORT already has the expected Neo4j route."
  fi

  info "Dagster: https://${NEO4J_TLS_HOST}/"
  if [ "$state_neo4j" != "disabled" ]; then
    info "Neo4j:  bolt+s://${NEO4J_TLS_HOST}:${NEO4J_TAILNET_BOLT_PORT}"
  fi
  ROLLBACK_ON_EXIT=0
  success "Tailscale Serve routes are active (Funnel remains disabled)."
}

cmd_status() {
  require_tailscale
  info "Current Tailscale Serve configuration:"
  tailscale serve status
}

cmd_down() {
  require_tailscale
  validate_neo4j_tailnet_port
  NEO4J_TLS_HOST=$(tailscale_dns_name || true)
  if [ -z "$NEO4J_TLS_HOST" ]; then
    error "Could not determine this node's Tailscale DNS name for Neo4j TLS."
    exit 1
  fi
  state_443=$(route_state 443 "$DAGSTER_TARGET") || exit 1
  state_neo4j=$(route_state "$NEO4J_TAILNET_BOLT_PORT" "$NEO4J_TARGET" "$NEO4J_TLS_HOST") || exit 1

  if [ "$state_443" = "occupied" ] || [ "$state_neo4j" = "occupied" ]; then
    error "A requested port has a different Serve owner or target; nothing was removed."
    error "Inspect with: tailscale serve status"
    exit 1
  fi

  if [ "$state_neo4j" = "owned" ]; then
    remove_owned_route "$NEO4J_TAILNET_BOLT_PORT" "$NEO4J_TARGET" "$NEO4J_TLS_HOST"
    success "Removed the SBIR Neo4j TLS/TCP route."
  else
    warn "No SBIR Neo4j TLS/TCP route to remove."
  fi
  if [ "$state_443" = "owned" ]; then
    remove_owned_route 443 "$DAGSTER_TARGET"
    success "Removed the SBIR HTTPS 443 route."
  else
    warn "No SBIR HTTPS 443 route to remove."
  fi
  info "All other Tailscale configuration was left untouched."
}

case "${1:-}" in
  up) cmd_up ;;
  status) cmd_status ;;
  down) cmd_down ;;
  *)
    echo "Usage: $0 {up|status|down}" >&2
    exit 2
    ;;
esac
