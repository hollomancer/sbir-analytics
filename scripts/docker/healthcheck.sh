#!/usr/bin/env sh
# sbir-etl/scripts/docker/healthcheck.sh
#
# Lightweight healthcheck helper for Docker HEALTHCHECK usage.
#
# Supports three modes:
#   - app    : verify Python package import (default)
#   - web    : HTTP health check against a path (e.g. /server_info)
#   - neo4j  : run a lightweight cypher-shell command (if available) or TCP probe
#
# Exits:
#   0 = healthy
#   1 = unhealthy / failure
#   2 = usage / invalid args
#
# Usage examples (Dockerfile HEALTHCHECK):
#   HEALTHCHECK CMD /app/sbir-etl/scripts/docker/healthcheck.sh --mode app
#   HEALTHCHECK CMD /app/sbir-etl/scripts/docker/healthcheck.sh --mode web --host 127.0.0.1 --port 3000 --path /server_info
#   HEALTHCHECK CMD /app/sbir-etl/scripts/docker/healthcheck.sh --mode neo4j --host neo4j --port 7687 --user neo4j --password "${NEO4J_PASSWORD}"
#
# Notes:
# - The script is POSIX sh compatible.
# - Minimal external dependencies: curl (for http checks), cypher-shell (for neo4j checks) and nc (netcat) for TCP probes.
# - If required tooling is missing, the script falls back to portable probes where possible.
#

set -eu

# Default configuration
MODE="app"
HOST="127.0.0.1"
PORT=""
PATH_CHECK="/"
USER=""
PASSWORD=""
TIMEOUT=5

usage() {
  cat <<EOF
Usage: $0 [--mode app|web|neo4j] [--host HOST] [--port PORT] [--path PATH]
          [--user USER --password PASS] [--timeout SEC]

Modes:
  app     - Attempt a Python import to ensure the runtime package is loadable (default)
  web     - HTTP check (requires curl). Expects a 2xx/3xx response.
  neo4j   - Attempt a cypher-shell 'RETURN 1' check if available, otherwise a TCP probe.

Examples:
  $0 --mode app
  $0 --mode web --host 127.0.0.1 --port 3000 --path /server_info
  $0 --mode neo4j --host neo4j --port 7687 --user neo4j --password secret
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
    --user)
      USER="$2"; shift 2 ;;
    --password)
      PASSWORD="$2"; shift 2 ;;
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

# Helper: TCP probe via nc or /dev/tcp fallback
tcp_probe() {
  host="$1"
  port="$2"
  # Prefer nc
  if command -v nc >/dev/null 2>&1; then
    # Use timeout wrapper if available
    if command -v timeout >/dev/null 2>&1; then
      timeout "$TIMEOUT" sh -c "nc -z '$host' '$port'" >/dev/null 2>&1
      return $?
    else
      nc -z "$host" "$port" >/dev/null 2>&1
      return $?
    fi
  fi

  # shell /dev/tcp fallback (may not be available in sh strictly, but try)
  if (exec 3<>"/dev/tcp/$host/$port") >/dev/null 2>&1; then
    exec 3<&- || true
    exec 3>&- || true
    return 0
  fi

  # No suitable method
  err "tcp_probe: no nc and /dev/tcp not available"
  return 1
}

# Mode implementations
check_app() {
  # Try importing the project package. Common module names include 'sbir_etl' or 'src'.
  # Try in order: sbir_etl, src
  # Exit 0 on first success, otherwise non-zero.
  log "Running app import check (timeout ${TIMEOUT}s)"
  # Use python -c in a separate process; respect TIMEOUT if available
  if command -v timeout >/dev/null 2>&1; then
    timeout "$TIMEOUT" sh -c "python - <<'PY'\nimport sys\nok=False\nfor mod in ('sbir_etl','src'):\n  try:\n    __import__(mod)\n    ok=True\n    break\n  except Exception as e:\n    pass\nsys.exit(0 if ok else 2)\nPY" >/dev/null 2>&1 || rc=$? ; rc=${rc:-$?}
  else
    python - <<'PY' >/dev/null 2>&1 || rc=$? ; rc=${rc:-$?}
import sys
ok=False
for mod in ('sbir_etl','src'):
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

check_neo4j() {
  # Prefer cypher-shell if available
  if command -v cypher-shell >/dev/null 2>&1; then
    if [ -z "$USER" ] || [ -z "$PASSWORD" ]; then
      err "cypher-shell available but no credentials supplied (--user/--password)"
      return 1
    fi
    log "Running cypher-shell auth check"
    # Use timeout if available
    if command -v timeout >/dev/null 2>&1; then
      timeout "$TIMEOUT" sh -c "cypher-shell -u \"$USER\" -p \"$PASSWORD\" 'RETURN 1' >/dev/null 2>&1"
      rc=$?
    else
      cypher-shell -u "$USER" -p "$PASSWORD" "RETURN 1" >/dev/null 2>&1
      rc=$?
    fi

    if [ "$rc" -eq 0 ]; then
      log "neo4j cypher-shell check ok"
      return 0
    else
      err "neo4j cypher-shell check failed (rc=${rc})"
      # fall through to tcp probe attempt
    fi
  fi

  # Fallback to TCP probe on host:port
  if [ -z "$PORT" ]; then
    err "No port specified for neo4j TCP probe"
    return 1
  fi
  log "Falling back to TCP probe for Neo4j at ${HOST}:${PORT}"
  if tcp_probe "$HOST" "$PORT"; then
    log "Neo4j TCP probe ok"
    return 0
  else
    err "Neo4j TCP probe failed"
    return 1
  fi
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
  neo4j)
    if [ -z "$PORT" ]; then
      err "neo4j mode requires --port"
      exit 2
    fi
    exit_code=$(check_neo4j); exit $exit_code
    ;;
  *)
    err "Unknown mode: $MODE"
    usage
    exit 2
    ;;
esac
