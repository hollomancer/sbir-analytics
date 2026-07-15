#!/usr/bin/env sh
# sbir-analytics/scripts/server/tailscale-serve.sh
#
# Manage the *only* ingress for the Mac mini server: persistent Tailscale Serve
# routes (tailnet-only HTTPS, automatic TLS termination). See:
#   https://tailscale.com/docs/features/tailscale-serve
#
# Routes managed here (and ONLY these):
#   HTTPS 443  -> Dagster           127.0.0.1:${DAGSTER_PORT:-3000}
#   HTTPS 8443 -> analytics API      127.0.0.1:${SBIR_ANALYTICS_API_PORT:-8010}
#
# Neo4j is NEVER served. Tailscale Funnel is NEVER enabled (tailnet-only).
#
# Subcommands:
#   up      create the routes with --bg (persist across restarts).
#           Refuses to replace an existing mapping on 443 or 8443.
#   status  show current Serve configuration.
#   down    remove ONLY the two routes above. Never runs the destructive
#           global `tailscale serve reset`.
#
# Usage:
#   scripts/server/tailscale-serve.sh up|status|down

set -eu

# Load .env.server tolerantly (values may contain spaces, e.g. cron strings).
ENV_FILE="${SERVER_ENV_FILE:-.env.server}"
if [ -f "$ENV_FILE" ]; then
  set +eu
  # shellcheck disable=SC1090
  . "$ENV_FILE" 2>/dev/null || true
  set -eu
fi

DAGSTER_PORT="${DAGSTER_PORT:-3000}"
API_PORT="${SBIR_ANALYTICS_API_PORT:-8010}"
LOOPBACK="127.0.0.1"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { printf "${BLUE}➤${NC} %s\n" "$1"; }
success() { printf "${GREEN}✓${NC} %s\n" "$1"; }
warn()    { printf "${YELLOW}⚠${NC} %s\n" "$1"; }
error()   { printf "${RED}✖${NC} %s\n" "$1"; }

require_tailscale() {
  if ! command -v tailscale >/dev/null 2>&1; then
    error "tailscale CLI not found. Install Tailscale and sign in."
    exit 1
  fi
  if ! tailscale status >/dev/null 2>&1; then
    error "Tailscale is not running or not logged in. Run: tailscale up"
    exit 1
  fi
}

serve_json() { tailscale serve status --json 2>/dev/null || echo ''; }

port_mapped() {
  # Returns 0 if the given HTTPS port already appears in Serve config.
  printf '%s' "$(serve_json)" | grep -q "\"$1\""
}

cmd_up() {
  require_tailscale

  # Guard: never clobber an existing route on either port.
  if port_mapped 443; then
    error "Serve already maps HTTPS 443. Refusing to overwrite it."
    error "  Inspect: tailscale serve status  •  Remove ours: $0 down"
    exit 1
  fi
  if port_mapped 8443; then
    error "Serve already maps HTTPS 8443. Refusing to overwrite it."
    error "  Inspect: tailscale serve status  •  Remove ours: $0 down"
    exit 1
  fi

  info "Configuring persistent Tailscale Serve routes (--bg)..."
  # 443 -> Dagster
  tailscale serve --bg --https 443 "http://${LOOPBACK}:${DAGSTER_PORT}"
  success "HTTPS 443  -> Dagster (${LOOPBACK}:${DAGSTER_PORT})"
  # 8443 -> API
  tailscale serve --bg --https 8443 "http://${LOOPBACK}:${API_PORT}"
  success "HTTPS 8443 -> analytics API (${LOOPBACK}:${API_PORT})"

  echo ""
  info "Tailnet URLs (MagicDNS):"
  host="$(tailscale status --json 2>/dev/null | grep -oE '"DNSName":"[^"]+"' | head -1 | cut -d'"' -f4 | sed 's/\.$//')"
  if [ -n "$host" ]; then
    echo "  Dagster: https://${host}/"
    echo "  API:     https://${host}:8443/"
  fi
  warn "Tailscale Funnel is intentionally NOT enabled. These are tailnet-only."
}

cmd_status() {
  require_tailscale
  info "Current Tailscale Serve configuration:"
  tailscale serve status || true
}

cmd_down() {
  require_tailscale
  info "Removing ONLY the SBIR server Serve routes (443, 8443)..."
  # `--https <port> off` removes just that mapping; the global
  # `tailscale serve reset` is intentionally NEVER used here.
  if port_mapped 443; then
    tailscale serve --https 443 off || warn "Could not remove HTTPS 443 route."
    success "Removed HTTPS 443 route."
  else
    warn "No HTTPS 443 route to remove."
  fi
  if port_mapped 8443; then
    tailscale serve --https 8443 off || warn "Could not remove HTTPS 8443 route."
    success "Removed HTTPS 8443 route."
  else
    warn "No HTTPS 8443 route to remove."
  fi
  info "Left all other Tailscale configuration untouched."
}

case "${1:-}" in
  up)     cmd_up ;;
  status) cmd_status ;;
  down)   cmd_down ;;
  *)
    echo "Usage: $0 {up|status|down}" >&2
    exit 2
    ;;
esac
