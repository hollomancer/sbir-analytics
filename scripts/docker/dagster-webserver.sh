#!/usr/bin/env sh
# sbir-analytics/scripts/docker/dagster-webserver.sh
#
# Service wrapper for starting the Dagster webserver inside the container.
# Provides:
#  - env loading (.env, /run/secrets)
#  - start command that adapts for dev vs prod
#  - a lightweight healthcheck mode suitable for Docker HEALTHCHECK
#
# Usage:
#   sh dagster-webserver.sh start
#   sh dagster-webserver.sh healthcheck   # exits 0 when /server_info is healthy
#
# This script is POSIX sh compatible so it can run in slim images.

set -eu

# ---------- logging helpers ----------
log() {
  # Simple timestamped log
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

err() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "ERROR: $*" >&2
}

# ---------- load environment ----------
load_env() {
  # Source common .env locations if present
  for f in /app/.env /app/config/.env /etc/sbir/.env; do
    if [ -f "$f" ]; then
      log "Sourcing environment from $f"
      # shellcheck disable=SC1090
      . "$f"
    fi
  done

  # Load secrets from /run/secrets if present (file-per-secret)
  if [ -d /run/secrets ]; then
    for sf in /run/secrets/*; do
      [ -f "$sf" ] || continue
      name=$(basename "$sf")
      # Only set if not already present
      eval "current=\${$name-}"
      if [ -z "${current}" ]; then
        value=$(awk '{printf "%s", $0}' "$sf")
        export "$name"="$value"
        log "Loaded secret ${name} from /run/secrets"
      fi
    done
  fi
}

# ---------- healthcheck ----------
# Usage: dagster-webserver.sh healthcheck
# Returns 0 if webserver /server_info returns 2xx/3xx, non-zero otherwise.
healthcheck() {
  HOST="${DAGSTER_HOST:-127.0.0.1}"
  PORT="${DAGSTER_PORT:-3000}"
  PATH="${DAGSTER_HEALTH_PATH:-/server_info}"
  TIMEOUT="${HEALTHCHECK_TIMEOUT:-5}"

  if ! command -v curl >/dev/null 2>&1; then
    err "curl not available for healthcheck"
    return 2
  fi

  URL="http://${HOST}:${PORT}${PATH}"
  HTTP_CODE=$(curl -sS --max-time "${TIMEOUT}" -o /dev/null -w '%{http_code}' "$URL" || echo "000")
  case "$HTTP_CODE" in
    2*|3*)
      log "Healthcheck OK: ${URL} -> ${HTTP_CODE}"
      return 0
      ;;
    *)
      err "Healthcheck failed: ${URL} -> ${HTTP_CODE}"
      return 1
      ;;
  esac
}

# ---------- start server ----------
start_server() {
  # Defaults
  HOST="${DAGSTER_HOST:-0.0.0.0}"
  PORT="${DAGSTER_PORT:-3000}"
  ENV="${ENVIRONMENT:-dev}"
  # Allow overriding dagster command via DAGSTER_CMD env var
  if [ -n "${DAGSTER_CMD-}" ]; then
    CMD="${DAGSTER_CMD}"
  else
    if [ "$ENV" = "dev" ]; then
      CMD="dagster dev -h ${HOST} -p ${PORT}"
    else
      # production-like invocation; adjust as desired for your deployment
      CMD="dagster api -h ${HOST} -p ${PORT}"
    fi
  fi

  log "Using environment: ${ENV}"
  log "Starting Dagster webserver with command: ${CMD}"
  # exec to replace shell so signals reach the process directly
  # If gosu is provided and running as root, prefer running as sbir user for security.
  if [ "$(id -u)" = "0" ]; then
    if command -v gosu >/dev/null 2>&1; then
      log "Dropping privileges to 'sbir' via gosu"
      exec gosu sbir sh -c "${CMD}"
    elif command -v su-exec >/dev/null 2>&1; then
      log "Dropping privileges to 'sbir' via su-exec"
      exec su-exec sbir sh -c "${CMD}"
    else
      log "No privilege-drop helper found; running as root (not recommended)"
      exec sh -c "${CMD}"
    fi
  else
    exec sh -c "${CMD}"
  fi
}

# ---------- main ----------
main() {
  if [ "$#" -ge 1 ]; then
    case "$1" in
      healthcheck)
        healthcheck
        exit $?
        ;;
      start)
        # fallthrough to normal start sequence
        ;;
      *)
        # allow passing arbitrary command to run (exec)
        log "Executing provided command: $*"
        exec "$@"
        ;;
    esac
  fi

  load_env

  # Provide some notice of environment and key vars (but avoid printing secrets)
  log "Starting dagster-webserver wrapper. ENVIRONMENT=${ENVIRONMENT:-<unset>}, DAGSTER_PORT=${DAGSTER_PORT:-3000}"

  # Start server (this function will block)
  start_server
}

# If invoked directly, call main with all args
main "$@"
