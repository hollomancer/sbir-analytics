#!/usr/bin/env sh
# sbir-analytics/scripts/docker/healthcheck.sh
#
# Lightweight healthcheck helper for Docker HEALTHCHECK usage.
#
# Supports two modes:
#   - app    : verify Python package import (default)
#   - web    : HTTP health check against a path (e.g. /server_info)
#
# Exits:
#   0 = healthy
#   1 = unhealthy / failure
#   2 = usage / invalid args
#
# Usage examples (Dockerfile HEALTHCHECK):
#   HEALTHCHECK CMD /app/sbir-analytics/scripts/docker/healthcheck.sh --mode app
#   HEALTHCHECK CMD /app/sbir-analytics/scripts/docker/healthcheck.sh --mode web --host 127.0.0.1 --port 3000 --path /server_info
#
# Notes:
# - The script is POSIX sh compatible.
# - The web check requires curl.
#

set -eu

# Default configuration
MODE="app"
HOST="127.0.0.1"
PORT=""
PATH_CHECK="/"
TIMEOUT=5

usage() {
  cat <<EOF
Usage: $0 [--mode app|web] [--host HOST] [--port PORT] [--path PATH] [--timeout SEC]

Modes:
  app     - Attempt a Python import to ensure the runtime package is loadable (default)
  web     - HTTP check (requires curl). Expects a 2xx/3xx response.

Examples:
  $0 --mode app
  $0 --mode web --host 127.0.0.1 --port 3000 --path /server_info
EOF
}

log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

err() {
  log "ERROR: $*"
}

# Basic arg parsing
while [ $# -gt 0 ]; do
  case "$1" in
    --mode)
      MODE="$2"; shift 2 ;;
    --host)
      HOST="$2"; shift 2 ;;
    --port)
      PORT="$2"; shift 2 ;;
    --path)
      PATH_CHECK="$2"; shift 2 ;;
    --timeout)
      TIMEOUT="$2"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      err "Unknown argument: $1"
      usage
      exit 2 ;;
  esac
done

# Validate numeric timeout
case "$TIMEOUT" in
  ''|*[!0-9]*)
    err "--timeout must be an integer"
    exit 2 ;;
esac

# Mode implementations
check_app() {
  # Try importing the project package. Current module names include 'sbir_etl' and 'sbir_analytics'.
  # Try the current top-level application packages
  # Exit 0 on first success, otherwise non-zero.
  log "Running app import check (timeout ${TIMEOUT}s)"
  # Use python -c in a separate process; respect TIMEOUT if available
  if command -v timeout >/dev/null 2>&1; then
    timeout "$TIMEOUT" sh -c "python - <<'PY'\nimport sys\nok=False\nfor mod in ('sbir_etl','sbir_analytics'):\n  try:\n    __import__(mod)\n    ok=True\n    break\n  except Exception as e:\n    pass\nsys.exit(0 if ok else 2)\nPY" >/dev/null 2>&1 || rc=$? ; rc=${rc:-$?}
  else
    python - <<'PY' >/dev/null 2>&1 || rc=$? ; rc=${rc:-$?}
import sys
ok=False
for mod in ('sbir_etl','sbir_analytics'):
  try:
    __import__(mod)
    ok=True
    break
  except Exception:
    pass
sys.exit(0 if ok else 2)
PY
  fi

  if [ "${rc:-0}" -eq 0 ]; then
    log "app import OK"
    return 0
  else
    err "app import failed (rc=${rc:-$?})"
    return 1
  fi
}

check_web() {
  if ! command -v curl >/dev/null 2>&1; then
    err "curl not available for HTTP healthcheck"
    return 1
  fi

  url="http://${HOST}:${PORT}${PATH_CHECK}"
  log "Checking HTTP ${url} (timeout ${TIMEOUT}s)"
  http_code=$(curl -sS --max-time "${TIMEOUT}" -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo "000")
  case "$http_code" in
    2*|3*)
      log "HTTP health ok: ${http_code}"
      return 0
      ;;
    *)
      err "HTTP health failed: ${http_code}"
      return 1
      ;;
  esac
}

# Validate args for selected mode
case "$MODE" in
  app)
    exit_code=$(check_app); exit $exit_code
    ;;
  web)
    if [ -z "$PORT" ]; then
      err "web mode requires --port"
      exit 2
    fi
    exit_code=$(check_web); exit $exit_code
    ;;
  *)
    err "Unknown mode: $MODE"
    usage
    exit 2
    ;;
esac
