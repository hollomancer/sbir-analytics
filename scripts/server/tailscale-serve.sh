#!/usr/bin/env sh
# Manage the two tailnet-only HTTPS routes for the Mac mini server profile.

set -eu

ENV_FILE="${SERVER_ENV_FILE:-.env.server}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=scripts/server/env-file.sh
. "$SCRIPT_DIR/env-file.sh"
load_env_key DAGSTER_PORT
load_env_key SBIR_ANALYTICS_API_PORT

DAGSTER_PORT="${DAGSTER_PORT:-3000}"
API_PORT="${SBIR_ANALYTICS_API_PORT:-8010}"
DAGSTER_TARGET="http://127.0.0.1:${DAGSTER_PORT}"
API_TARGET="http://127.0.0.1:${API_PORT}"
STATE_HELPER="$SCRIPT_DIR/tailscale-route-state.py"
MUTATION_PID=""
MUTATION_OUTPUT=""
LAST_MUTATION_OUTPUT=""
PENDING_PORT=""
PENDING_TARGET=""
CREATED_443=0
CREATED_8443=0
ROLLBACK_ON_EXIT=0

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { printf "${BLUE}➤${NC} %s\n" "$1"; }
success() { printf "${GREEN}✓${NC} %s\n" "$1"; }
warn()    { printf "${YELLOW}⚠${NC} %s\n" "$1"; }
error()   { printf "${RED}✖${NC} %s\n" "$1" >&2; }

stop_mutation() {
  if [ -n "$MUTATION_PID" ] && kill -0 "$MUTATION_PID" 2>/dev/null; then
    kill "$MUTATION_PID" 2>/dev/null || true
    grace=0
    while kill -0 "$MUTATION_PID" 2>/dev/null && [ "$grace" -lt 3 ]; do
      sleep 1
      grace=$((grace + 1))
    done
    if kill -0 "$MUTATION_PID" 2>/dev/null; then
      kill -9 "$MUTATION_PID" 2>/dev/null || true
    fi
  fi
  [ -z "$MUTATION_PID" ] || wait "$MUTATION_PID" 2>/dev/null || true
}

cleanup_mutation() {
  stop_mutation
  [ -z "$MUTATION_OUTPUT" ] || rm -f "$MUTATION_OUTPUT"
  MUTATION_PID=""
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

route_state() {
  port="$1"
  target="$2"
  if ! json=$(tailscale serve status --json 2>/dev/null); then
    error "Could not inspect the current Tailscale Serve configuration."
    return 1
  fi
  printf '%s' "$json" | python3 "$STATE_HELPER" "$port" "$target"
}

run_tailscale_mutation() {
  timeout="${TAILSCALE_SERVE_TIMEOUT:-15}"
  case "$timeout" in
    ''|*[!0-9]*) error "TAILSCALE_SERVE_TIMEOUT must be a positive integer."; return 2 ;;
  esac
  [ "$timeout" -gt 0 ] || { error "TAILSCALE_SERVE_TIMEOUT must be positive."; return 2; }

  LAST_MUTATION_OUTPUT=""
  MUTATION_OUTPUT=$(mktemp "${TMPDIR:-/tmp}/sbir-tailscale-serve.XXXXXX")
  tailscale "$@" >"$MUTATION_OUTPUT" 2>&1 &
  MUTATION_PID=$!
  elapsed=0
  while kill -0 "$MUTATION_PID" 2>/dev/null; do
    if [ "$elapsed" -ge "$timeout" ]; then
      stop_mutation
      LAST_MUTATION_OUTPUT=$(cat "$MUTATION_OUTPUT")
      [ -z "$LAST_MUTATION_OUTPUT" ] || printf '%s\n' "$LAST_MUTATION_OUTPUT" >&2
      error "Tailscale Serve did not finish within ${timeout}s."
      error "If HTTPS consent is pending, enable it using the URL above and rerun."
      cleanup_mutation
      return 124
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  if wait "$MUTATION_PID"; then
    status=0
  else
    status=$?
  fi
  LAST_MUTATION_OUTPUT=$(cat "$MUTATION_OUTPUT")
  cleanup_mutation
  [ -z "$LAST_MUTATION_OUTPUT" ] || printf '%s\n' "$LAST_MUTATION_OUTPUT"
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
  case "$port" in
    443) CREATED_443=1 ;;
    8443) CREATED_8443=1 ;;
  esac
  PENDING_PORT=""
  PENDING_TARGET=""
}

remove_owned_route() {
  port="$1"
  target="$2"
  state=$(route_state "$port" "$target") || return 1
  if [ "$state" != "owned" ]; then
    error "HTTPS $port changed ownership; refusing to remove it."
    return 1
  fi
  run_tailscale_mutation serve --yes "--https=$port" off || return 1
  state=$(route_state "$port" "$target") || return 1
  if [ "$state" != "free" ]; then
    error "HTTPS $port was not removed cleanly."
    return 1
  fi
}

rollback_expected_route() {
  port="$1"
  target="$2"
  if ! state=$(route_state "$port" "$target"); then
    warn "Could not inspect HTTPS $port during rollback; inspect it manually."
    return 1
  fi
  case "$state" in
    owned)
      warn "Rolling back the newly-created HTTPS $port route."
      remove_owned_route "$port" "$target" || {
        warn "Could not roll back HTTPS $port; inspect it manually."
        return 1
      }
      ;;
    free) ;;
    *) warn "HTTPS $port changed after creation; leaving it untouched." ;;
  esac
}

rollback_transaction() {
  # Disable recursive rollback before issuing any further Tailscale commands.
  ROLLBACK_ON_EXIT=0
  if [ -n "$PENDING_PORT" ]; then
    rollback_expected_route "$PENDING_PORT" "$PENDING_TARGET" || true
    PENDING_PORT=""
    PENDING_TARGET=""
  fi
  if [ "$CREATED_8443" -eq 1 ]; then
    rollback_expected_route 8443 "$API_TARGET" || true
    CREATED_8443=0
  fi
  if [ "$CREATED_443" -eq 1 ]; then
    rollback_expected_route 443 "$DAGSTER_TARGET" || true
    CREATED_443=0
  fi
}

cmd_up() {
  require_tailscale
  state_443=$(route_state 443 "$DAGSTER_TARGET") || exit 1
  state_8443=$(route_state 8443 "$API_TARGET") || exit 1

  for pair in "443:$state_443" "8443:$state_8443"; do
    port=${pair%%:*}
    state=${pair#*:}
    if [ "$state" = "occupied" ]; then
      error "HTTPS $port has a different Serve owner or target; refusing to overwrite it."
      error "Inspect with: tailscale serve status"
      exit 1
    fi
  done

  ROLLBACK_ON_EXIT=1
  if [ "$state_443" = "free" ]; then
    info "Configuring HTTPS 443 -> $DAGSTER_TARGET..."
    configure_route 443 "$DAGSTER_TARGET" || exit 1
  else
    success "HTTPS 443 already has the expected Dagster route."
  fi

  if [ "$state_8443" = "free" ]; then
    info "Configuring HTTPS 8443 -> $API_TARGET..."
    configure_route 8443 "$API_TARGET" || exit 1
  else
    success "HTTPS 8443 already has the expected API route."
  fi

  host=$(tailscale status --json 2>/dev/null | python3 -c '
import json, sys
print(json.load(sys.stdin).get("Self", {}).get("DNSName", "").rstrip("."))
' || true)
  if [ -n "$host" ]; then
    info "Dagster: https://${host}/"
    info "API:     https://${host}:8443/"
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
  state_443=$(route_state 443 "$DAGSTER_TARGET") || exit 1
  state_8443=$(route_state 8443 "$API_TARGET") || exit 1

  if [ "$state_443" = "occupied" ] || [ "$state_8443" = "occupied" ]; then
    error "A requested port has a different Serve owner or target; nothing was removed."
    error "Inspect with: tailscale serve status"
    exit 1
  fi

  if [ "$state_443" = "owned" ]; then
    remove_owned_route 443 "$DAGSTER_TARGET"
    success "Removed the SBIR HTTPS 443 route."
  else
    warn "No SBIR HTTPS 443 route to remove."
  fi
  if [ "$state_8443" = "owned" ]; then
    remove_owned_route 8443 "$API_TARGET"
    success "Removed the SBIR HTTPS 8443 route."
  else
    warn "No SBIR HTTPS 8443 route to remove."
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
