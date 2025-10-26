#!/usr/bin/env sh
# sbir-etl/scripts/docker/dagster-daemon.sh
#
# Service wrapper for starting the Dagster daemon and running ad-hoc ETL commands.
#
# Responsibilities:
#  - Load environment variables from common locations (.env, /run/secrets)
#  - Wait for upstream dependencies (Neo4j Bolt, Dagster webserver) to be healthy
#  - Start `dagster-daemon run` with graceful privilege drop and signal forwarding
#  - Provide an `etl-runner` mode to run arbitrary ad-hoc commands inside the image
#  - Provide a lightweight healthcheck mode for container HEALTHCHECK
#
# Usage:
#   sh dagster-daemon.sh start
#   sh dagster-daemon.sh etl-runner -- python -m src.scripts.job
#   sh dagster-daemon.sh healthcheck
#
# Notes:
#  - This script is POSIX sh compatible.
#  - It uses sbir-etl/scripts/docker/wait-for-service.sh for robust health polling when available.
#  - It prefers gosu/su-exec/runuser to drop privileges to 'sbir' user when running as root.
#  - Entrypoints should call this script from the image entrypoint; the ENTRYPOINT may also wrap it.
set -eu

# ---------- logging helpers ----------
log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

err() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "ERROR: $*" >&2
}

# ---------- environment loading ----------
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

# ---------- helpers for dropping privileges ----------
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
      exec_prefix=""
      log "Warning: running as root and no gosu/su-exec/runuser/sudo available to drop privileges"
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

  # Fallback: basic TCP loop
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
      # try /dev/tcp if shell supports it
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
    log "curl not available to probe Dagster webserver; skipping web health check"
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

# ---------- healthcheck ----------
# Check that daemon process is running or that webserver is healthy.
# Intended for use as a container HEALTHCHECK command.
healthcheck() {
  # Check for a running dagster-daemon process
  if command -v pgrep >/dev/null 2>&1; then
    if pgrep -f "dagster-daemon run" >/dev/null 2>&1; then
      log "Dagster daemon process running"
      return 0
    fi
  fi

  # Fallback: consider webserver healthy as indication the stack is up
  if command -v curl >/dev/null 2>&1; then
    HOST="${DAGSTER_HOST:-127.0.0.1}"
    PORT="${DAGSTER_PORT:-3000}"
    PATH="${DAGSTER_HEALTH_PATH:-/server_info}"
    CODE=$(curl -s -o /dev/null -w '%{http_code}' "http://${HOST}:${PORT}${PATH}" || echo "000")
    case "$CODE" in
      2*|3*)
        log "Daemon health: webserver healthy (HTTP ${CODE})"
        return 0
        ;;
      *)
        err "Daemon health: webserver unhealthy (HTTP ${CODE})"
        return 1
        ;;
    esac
  fi

  err "Daemon health: no pgrep and no healthy webserver"
  return 1
}

# ---------- start daemon ----------
start_daemon() {
  ENV="${ENVIRONMENT:-dev}"
  CMD="dagster-daemon run"

  log "ENVIRONMENT=${ENV}; preparing to start Dagster daemon"

  # Wait for dependencies: Neo4j required; Dagster webserver recommended
  if ! wait_for_neo4j; then
    err "Dependency check failed: Neo4j not available"
    exit 1
  fi

  # Attempt to wait for webserver, but do not fail hard if it times out; daemon may still start
  if ! wait_for_dagster_web; then
    log "Warning: dagster webserver not proven healthy before daemon start (continuing)"
  fi

  # Choose how to drop privileges if running as root
  EXEC_PREFIX=$(_make_exec_prefix)

  log "Starting Dagster daemon: ${CMD}"
  if [ -n "${EXEC_PREFIX}" ]; then
    log "Dropping privileges via: ${EXEC_PREFIX}"
    # exec to replace shell so proper signal handling happens
    eval "exec ${EXEC_PREFIX} sh -c '${CMD}'"
  else
    exec sh -c "${CMD}"
  fi
}

# ---------- ETL runner (ad-hoc commands) ----------
etl_runner() {
  # Expect the user to pass the command to run after the 'etl-runner' arg
  if [ "$#" -eq 0 ]; then
    err "etl-runner requires a command to execute. Example: etl-runner -- python -m src.scripts.job"
    exit 2
  fi

  # Ensure dependencies available
  if ! wait_for_neo4j; then
    err "Dependency check failed: Neo4j not available"
    exit 1
  fi

  if ! wait_for_dagster_web; then
    log "Warning: dagster webserver not proven healthy before etl-runner run"
  fi

  # Build command from args
  CMD="$(printf '%s ' "$@")"
  EXEC_PREFIX=$(_make_exec_prefix)

  log "Executing ETL runner command: ${CMD}"
  if [ -n "${EXEC_PREFIX}" ]; then
    eval "exec ${EXEC_PREFIX} sh -c '${CMD}'"
  else
    exec sh -c "${CMD}"
  fi
}

# ---------- utility: show usage ----------
usage() {
  cat <<EOF
Usage: $0 <mode> [-- <args>...]
Modes:
  start             Start the dagster-daemon (blocks; intended for container service)
  etl-runner <cmd>  Run an ad-hoc command inside the image (ensures dependencies first)
  healthcheck       Lightweight health check for container (returns 0 on healthy)
  help              Show this usage
Examples:
  $0 start
  $0 etl-runner -- python -m src.scripts.materialize
  $0 healthcheck
EOF
}

# ---------- main ----------
main() {
  if [ "$#" -lt 1 ]; then
    usage
    exit 2
  fi

  cmd="$1"
  shift || true

  load_env

  case "$cmd" in
    start)
      start_daemon
      ;;
    etl-runner)
      # If user provided a leading '--', strip it
      if [ "$#" -ge 1 ] && [ "$1" = "--" ]; then
        shift
      fi
      etl_runner "$@"
      ;;
    healthcheck)
      healthcheck
      exit $?
      ;;
    help|--help|-h)
      usage
      exit 0
      ;;
    *)
      # allow executing arbitrary provided command (fallback)
      log "Executing provided command: $cmd $*"
      exec "$cmd" "$@"
      ;;
  esac
}

main "$@"
