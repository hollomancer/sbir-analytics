#!/usr/bin/env sh
# sbir-etl/scripts/docker/etl-runner.sh
#
# ETL Runner wrapper for SBIR ETL container image.
#
# This script is a small service wrapper intended to be used as an entrypoint
# for ad-hoc ETL runs inside the container. It:
#  - loads environment (.env, /app/config/.env, /run/secrets/*)
#  - waits for Neo4j and optionally the Dagster webserver to be reachable
#  - drops privileges to a non-root 'sbir' user when possible
#  - executes the provided command
#
# Usage:
#   sh etl-runner.sh -- python -m src.scripts.materialize
#   sh etl-runner.sh python -m src.scripts.materialize
#
# Exit codes:
#   0  - command executed successfully
#   2  - usage / wrong invocation
#   3  - dependency check failed (Neo4j / Dagster)
#
set -eu

# ---------- logging ----------
log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

err() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "ERROR: $*" >&2
}

# ---------- environment loading ----------
load_env() {
  # Source .env files if present; keep this quiet if missing
  for f in /app/.env /app/config/.env /etc/sbir/.env; do
    if [ -f "$f" ]; then
      log "Sourcing environment from $f"
      # shellcheck disable=SC1090
      . "$f"
    fi
  done

  # Load secrets from /run/secrets (file-per-secret) into env if not already set
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

# ---------- privilege dropping helper ----------
_make_exec_prefix() {
  exec_prefix=""
  if [ "$(id -u)" = "0" ]; then
    if command -v gosu >/dev/null 2>&1; then
      exec_prefix="gosu sbir"
    elif command -v su-exec >/dev/null 2>&1; then
      exec_prefix="su-exec sbir"
    elif command -v runuser >/dev/null 2>&1; then
      exec_prefix="runuser -u sbir --"
    elif command -v sudo >/dev/null 2>&1; then
      exec_prefix="sudo -u sbir --"
    else
      log "No privilege-drop helper found; will run as root (not recommended)"
      exec_prefix=""
    fi
  fi
  printf '%s' "$exec_prefix"
}

# ---------- dependency waits ----------
wait_for_neo4j() {
  HOST="${SBIR_ETL__NEO4J__HOST:-${NEO4J_HOST:-neo4j}}"
  PORT="${SBIR_ETL__NEO4J__PORT:-${NEO4J_PORT:-7687}}"
  TIMEOUT="${SERVICE_STARTUP_TIMEOUT:-120}"
  WAIT_SCRIPT="/app/sbir-etl/scripts/docker/wait-for-service.sh"

  if [ -x "$WAIT_SCRIPT" ]; then
    log "Waiting for Neo4j at ${HOST}:${PORT} (timeout=${TIMEOUT}s)..."
    if "$WAIT_SCRIPT" --host "$HOST" --port "$PORT" --proto tcp --timeout "$TIMEOUT" --interval 5; then
      log "Neo4j is available"
      return 0
    else
      err "Timeout waiting for Neo4j"
      return 1
    fi
  fi

  # Fallback: attempt nc or /dev/tcp
  log "No wait-for helper; performing simple TCP probe for Neo4j ${HOST}:${PORT}"
  start_ts=$(date +%s)
  deadline=$((start_ts + TIMEOUT))
  while [ "$(date +%s)" -le "$deadline" ]; do
    if command -v nc >/dev/null 2>&1; then
      if nc -z "$HOST" "$PORT" >/dev/null 2>&1; then
        log "Neo4j reachable (nc)"
        return 0
      fi
    else
      # Try /dev/tcp if shell supports it
      if (exec 3<>"/dev/tcp/$HOST/$PORT") >/dev/null 2>&1; then
        exec 3<&- || true
        exec 3>&- || true
        log "Neo4j reachable (/dev/tcp)"
        return 0
      fi
    fi
    log "Neo4j not ready; retrying in 5s..."
    sleep 5
  done

  err "Timed out waiting for Neo4j"
  return 1
}

wait_for_dagster_web() {
  # Optional webserver wait; only used if DAGSTER_HEALTH_CHECK is set to true
  enable="${ETL_RUNNER_WAIT_DAGSTER:-${DAGSTER_WAIT:-false}}"
  if [ "${enable}" != "true" ] && [ "${enable}" != "1" ]; then
    log "Skipping Dagster webserver wait (disabled)"
    return 0
  fi

  WEB_HOST="${DAGSTER_HOST:-127.0.0.1}"
  WEB_PORT="${DAGSTER_PORT:-3000}"
  PATH="${DAGSTER_HEALTH_PATH:-/server_info}"
  TIMEOUT="${SERVICE_STARTUP_TIMEOUT:-120}"
  WAIT_SCRIPT="/app/sbir-etl/scripts/docker/wait-for-service.sh"

  if [ -x "$WAIT_SCRIPT" ]; then
    log "Waiting for Dagster webserver at ${WEB_HOST}:${WEB_PORT}${PATH} (timeout=${TIMEOUT}s)..."
    if "$WAIT_SCRIPT" --host "${WEB_HOST}" --port "${WEB_PORT}" --proto http --path "${PATH}" --timeout "${TIMEOUT}" --interval 5; then
      log "Dagster webserver is healthy"
      return 0
    else
      err "Timeout waiting for Dagster webserver"
      return 1
    fi
  fi

  if ! command -v curl >/dev/null 2>&1; then
    log "curl not available to probe Dagster webserver; skipping webserver wait"
    return 0
  fi

  start=$(date +%s)
  deadline=$((start + TIMEOUT))
  while [ "$(date +%s)" -le "$deadline" ]; do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://${WEB_HOST}:${WEB_PORT}${PATH}" || echo 000)
    case "$code" in
      2*|3*)
        log "Dagster webserver responded with HTTP ${code}"
        return 0
        ;;
      *)
        log "Dagster webserver not ready (HTTP ${code}) - sleeping 5s..."
        sleep 5
        ;;
    esac
  done
  err "Timed out waiting for Dagster webserver"
  return 1
}

# ---------- usage ----------
usage() {
  cat <<EOF
Usage: $0 -- <cmd>
Run an ad-hoc ETL command inside the container after ensuring dependencies.
Examples:
  $0 -- python -m src.scripts.materialize
  $0 -- dbt run
Notes:
  - Ensure you have a local .env file (copy from .env.example) or the environment
    is populated with the required variables (NEO4J credentials, etc.).
  - Set ETL_RUNNER_WAIT_DAGSTER=true to wait for the Dagster webserver in addition to Neo4j.
EOF
}

# ---------- main ----------
main() {
  if [ "$#" -eq 0 ]; then
    usage
    exit 2
  fi

  # If the first arg is '--', shift it
  if [ "$1" = "--" ]; then
    shift
    if [ "$#" -eq 0 ]; then
      usage
      exit 2
    fi
  fi

  # The remaining args are the command to run
  # Build a single-quoted command string to pass to sh -c safely for exec prefixing.
  CMD_ARGS="$*"

  load_env

  log "ETL Runner invoked. Command: ${CMD_ARGS}"
  log "Loading dependency checks (Neo4j, optional Dagster)..."

  if ! wait_for_neo4j; then
    err "Neo4j did not become available; aborting ETL runner"
    exit 3
  fi

  if ! wait_for_dagster_web; then
    err "Dagster webserver did not become healthy (if required); aborting"
    exit 3
  fi

  # Determine whether to drop privileges
  EXEC_PREFIX="$(_make_exec_prefix)"

  # Execute command
  if [ -n "${EXEC_PREFIX}" ]; then
    log "Executing command as non-root via: ${EXEC_PREFIX}"
    # Use sh -c to accept the command string. Use eval to expand prefix + command properly.
    eval "exec ${EXEC_PREFIX} sh -c '${CMD_ARGS}'"
  else
    log "Executing command directly (no privilege drop available)"
    exec sh -c "${CMD_ARGS}"
  fi
}

main "$@"
