#!/usr/bin/env sh
# wait-for-service.sh
#
# Wait for a network service to become available.
#
# Usage:
#   wait-for-service.sh --host HOST --port PORT [--proto tcp|http] [--path /health] \
#                       [--user USER --password PASS] [--timeout SEC] [--interval SEC]
#
# Examples:
#   wait-for-service.sh --host neo4j --port 7687 --proto tcp --timeout 120
#   wait-for-service.sh --host web --port 3000 --proto http --path /server_info --timeout 60
#
# Behavior:
# - Returns 0 when the target service responds successfully before timeout.
# - Returns non-zero when the timeout elapses or an unrecoverable error occurs.
#
# Notes:
# - For HTTP checks this script uses `curl`. For TCP checks it prefers `nc` (netcat).
#   If `nc` is not available, the script will report that requirement.
# - Designed to be POSIX-friendly; some advanced features depend on available tools.

set -eu

# Defaults
PROTO="tcp"
HEALTH_PATH="/"
TIMEOUT=120
INTERVAL=5
USER=""
PASSWORD=""

usage() {
  cat <<EOF
Usage:
  $0 --host HOST --port PORT [--proto tcp|http] [--path /health]
        [--user USER --password PASS] [--timeout SEC] [--interval SEC]

Options:
  --host         Hostname or IP of the service (required)
  --port         Port number of the service (required)
  --proto        Protocol to check: tcp (default) or http
  --path         HTTP path to poll (only for http), default "/"
  --user         Basic auth username (HTTP only)
  --password     Basic auth password (HTTP only)
  --timeout      Total seconds to wait before giving up (default: ${TIMEOUT})
  --interval     Seconds between checks (default: ${INTERVAL})
  -h, --help     Show this help and exit

Examples:
  $0 --host neo4j --port 7687 --proto tcp --timeout 120
  $0 --host web --port 3000 --proto http --path /server_info --timeout 60
EOF
}

# Simple argument parsing
while [ $# -gt 0 ]; do
  case "$1" in
    --host)
      HOST="$2"; shift 2 ;;
    --port)
      PORT="$2"; shift 2 ;;
    --proto)
      PROTO="$(echo "$2" | tr '[:upper:]' '[:lower:]')"; shift 2 ;;
    --path)
      HEALTH_PATH="$2"; shift 2 ;;
    --timeout)
      TIMEOUT="$2"; shift 2 ;;
    --interval)
      INTERVAL="$2"; shift 2 ;;
    --user)
      USER="$2"; shift 2 ;;
    --password)
      PASSWORD="$2"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      printf "Unknown argument: %s\n\n" "$1" >&2
      usage; exit 2 ;;
  esac
done

if [ -z "${HOST-}" ] || [ -z "${PORT-}" ]; then
  printf "Error: --host and --port are required\n\n" >&2
  usage
  exit 2
fi

# Validate numeric timeout/interval
case "$TIMEOUT" in
  ''|*[!0-9]*)
    printf "Error: --timeout must be an integer number of seconds\n" >&2
    exit 2 ;;
esac

case "$INTERVAL" in
  ''|*[!0-9]*)
    printf "Error: --interval must be an integer number of seconds\n" >&2
    exit 2 ;;
esac

# Helper functions
_now() {
  # seconds since epoch
  date +%s
}

_elapsed() {
  # $1 = start, returns seconds elapsed
  start=$1
  now="$(_now)"
  echo $(( now - start ))
}

log() {
  printf '[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$1"
}

die() {
  printf '%s\n' "$1" >&2
  exit "${2:-1}"
}

# Trap to handle interrupts gracefully
_on_int() {
  log "Interrupted by user; exiting."
  exit 130
}
trap _on_int INT TERM

# Select check method
check_tcp() {
  # Prefer nc (netcat) if available
  if command -v nc >/dev/null 2>&1; then
    # Use -z for zero-I/O probe; some nc implementations (openbsd/ncat) vary
    # Try POSIX-friendly options first; fallback to simple connection test
    if nc -z "$HOST" "$PORT" >/dev/null 2>&1; then
      return 0
    else
      return 1
    fi
  fi

  # If /dev/tcp is supported by shell, try it (bash/ksh)
  if (exec 3<>"/dev/tcp/$HOST/$PORT") >/dev/null 2>&1; then
    # close descriptor
    exec 3<&- || true
    exec 3>&- || true
    return 0
  fi

  die "TCP check requires 'nc' or a shell with /dev/tcp support. Install netcat and retry."
}

check_http() {
  # Ensure curl exists
  if ! command -v curl >/dev/null 2>&1; then
    die "HTTP check requires 'curl' to be installed in the container."
  fi

  # Compose URL and curl options
  URL="http://${HOST}:${PORT}${HEALTH_PATH}"
  CURL_OPTS="-sS --max-time 5 -o /dev/null -w '%{http_code}'"

  # If basic auth provided, add it
  if [ -n "$USER" ] && [ -n "$PASSWORD" ]; then
    AUTH_OPT="-u ${USER}:${PASSWORD}"
  else
    AUTH_OPT=""
  fi

  # Execute curl and capture http code
  HTTP_CODE=$(sh -c "curl $CURL_OPTS $AUTH_OPT '$URL'" 2>/dev/null || echo "000")
  case "$HTTP_CODE" in
    2*|3*)
      # Treat 2xx and 3xx as healthy
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

# Main wait loop
start_time="$(_now)"
deadline=$(( start_time + TIMEOUT ))
log "Waiting for $PROTO service at ${HOST}:${PORT} (timeout=${TIMEOUT}s, interval=${INTERVAL}s)..."

while [ "$(_now)" -le "$deadline" ]; do
  if [ "$PROTO" = "tcp" ]; then
    if check_tcp; then
      log "TCP service ${HOST}:${PORT} is available."
      exit 0
    fi
  elif [ "$PROTO" = "http" ]; then
    if check_http; then
      log "HTTP service ${HOST}:${PORT}${HEALTH_PATH} is healthy."
      exit 0
    fi
  else
    die "Unsupported protocol: ${PROTO}. Use tcp or http."
  fi

  elapsed="$(_elapsed "$start_time")"
  remaining=$(( deadline - _now ))
  if [ "$remaining" -lt 0 ]; then
    remaining=0
  fi

  log "Still waiting... elapsed=${elapsed}s remaining=${remaining}s"
  sleep "$INTERVAL"
done

# Timeout reached
log "Timed out after ${TIMEOUT} seconds waiting for ${HOST}:${PORT} (${PROTO})."
exit 1
