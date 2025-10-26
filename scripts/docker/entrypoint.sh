#!/usr/bin/env sh
# sbir-etl/scripts/docker/entrypoint.sh
#
# Container entrypoint for SBIR ETL images.
#
# Responsibilities:
#  - Load environment variables from common locations (.env, /run/secrets)
#  - Provide service-specific startup behavior (dagster-webserver, dagster-daemon, etl-runner)
#  - Wait for upstream dependencies (Neo4j, webserver) to become healthy
#  - Drop privileges to non-root user when possible
#  - Forward signals and exec the chosen command
#
# Usage (container CMD or service-specific entrypoint):
#   ENTRYPOINT ["sh", "/app/scripts/docker/entrypoint.sh", "dagster-webserver"]
#   ENTRYPOINT ["sh", "/app/scripts/docker/entrypoint.sh", "dagster-daemon"]
#   ENTRYPOINT ["sh", "/app/scripts/docker/entrypoint.sh", "etl-runner", "python", "-m", "my.module"]
#
# Environment variables used (documented in .env.example):
#   ENVIRONMENT                - dev|test|prod (affects behavior)
#   SBIR_ETL__NEO4J__HOST      - Neo4j host (default: neo4j)
#   SBIR_ETL__NEO4J__PORT      - Neo4j bolt port (default: 7687)
#   SBIR_ETL__NEO4J__USERNAME  - Neo4j username
#   SBIR_ETL__NEO4J__PASSWORD  - Neo4j password
#   SERVICE_STARTUP_TIMEOUT    - seconds to wait for dependencies (default: 120)
#
# Notes:
# - This script is intentionally POSIX-sh compatible for maximum portability.
# - It uses sbir-etl/scripts/docker/wait-for-service.sh if present to perform health checks.
# - The script will exec the final command so the process receives container signals.
set -eu

# Minimal portable timestamped logging
log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

# Default locations to source environment variables (in priority order)
# - /app/.env (project root mounted into /app)
# - /app/config/.env
# - /run/secrets/* (for docker secret mounted files)
load_env() {
  # Source .env files if present; ignore if not readable.
  ENVFILES="/app/.env /app/config/.env /etc/sbir/.env"
  for f in $ENVFILES; do
    if [ -f "$f" ]; then
      log "Sourcing environment variables from $f"
      # shellcheck disable=SC1090
      . "$f"
    fi
  done

  # If secrets are mounted as files (e.g., /run/secrets/NEO4J_PASSWORD),
  # allow container operator to populate env vars via file contents.
  # Convention: if VAR is not set and /run/secrets/VAR exists, read it.
  if [ -d /run/secrets ]; then
    for secret_file in /run/secrets/*; do
      [ -f "$secret_file" ] || continue
      name=$(basename "$secret_file")
      # only export if not already set
      eval "current=\${$name-}"
      if [ -z "${current}" ]; then
        # read secret content (trim trailing newline)
        value=$(awk '{printf "%s", $0}' "$secret_file")
        export "$name"="$value"
        log "Loaded secret ${name} from /run/secrets"
      fi
    done
  fi
}

# Attempt to drop privileges to non-root 'sbir' user if running as root and gosu/su-exec available.
# Will return with exec_prefix set to the proper command array (or empty for direct exec).
_make_exec_prefix() {
  exec_prefix=""
  if [ "$(id -u)" = "0" ]; then
    # prefer gosu, then su-exec, then runuser, then sudo -u
    if command -v gosu >/dev/null 2>&1; then
      exec_prefix="gosu sbir"
    elif command -v su-exec >/dev/null 2>&1; then
      exec_prefix="su-exec sbir"
    elif command -v runuser >/dev/null 2>&1; then
      exec_prefix="runuser -u sbir --"
    elif command -v sudo >/dev/null 2>&1; then
      exec_prefix="sudo -u sbir --"
    else
      # no helper available; will continue as root but warn
      log "Warning: running as root and no gosu/su-exec/runuser/sudo available to drop privileges"
      exec_prefix=""
    fi
  fi
  # export as plain variable for use with eval exec
  printf '%s' "$exec_prefix"
}

# Wait for the Neo4j service to be available using the included wait script if present.
wait_for_neo4j() {
  HOST="${SBIR_ETL__NEO4J__HOST:-${NEO4J_HOST:-neo4j}}"
  PORT="${SBIR_ETL__NEO4J__PORT:-${NEO4J_PORT:-7687}}"
  TIMEOUT="${SERVICE_STARTUP_TIMEOUT:-120}"
  WAIT_SCRIPT="/app/scripts/docker/wait-for-service.sh"

  if [ -x "$WAIT_SCRIPT" ]; then
    log "Waiting for Neo4j at ${HOST}:${PORT} (timeout=${TIMEOUT}s)..."
    # prefer TCP probe for bolt port
    "$WAIT_SCRIPT" --host "$HOST" --port "$PORT" --proto tcp --timeout "$TIMEOUT" --interval 5 || {
      log "Neo4j did not become available within ${TIMEOUT}s"
      return 1
    }
    log "Neo4j is available"
    return 0
  fi

  # Fallback: simple loop using nc or /dev/tcp
  log "No wait script found; performing basic TCP probe for Neo4j at ${HOST}:${PORT}"
  start=$(date +%s)
  deadline=$((start + TIMEOUT))
  while [ "$(date +%s)" -le "$deadline" ]; do
    if command -v nc >/dev/null 2>&1; then
      if nc -z "$HOST" "$PORT" >/dev/null 2>&1; then
        log "Neo4j available (nc)."
        return 0
      fi
    else
      # Try /dev/tcp if shell supports it
      if (exec 3<>"/dev/tcp/$HOST/$PORT") >/dev/null 2>&1; then
        exec 3<&- || true
        exec 3>&- || true
        log "Neo4j available (/dev/tcp)."
        return 0
      fi
    fi
    log "Neo4j not ready yet; sleeping 5s..."
    sleep 5
  done
  log "Timed out waiting for Neo4j"
  return 1
}

# Wait for the dagster webserver to expose /server_info (HTTP) if desired.
wait_for_dagster_web() {
  WEB_HOST="${DAGSTER_HOST:-127.0.0.1}"
  WEB_PORT="${DAGSTER_PORT:-3000}"
  PATH="${DAGSTER_HEALTH_PATH:-/server_info}"
  TIMEOUT="${SERVICE_STARTUP_TIMEOUT:-120}"
  WAIT_SCRIPT="/app/scripts/docker/wait-for-service.sh"

  if [ -x "$WAIT_SCRIPT" ]; then
    log "Waiting for Dagster webserver at ${WEB_HOST}:${WEB_PORT}${PATH} (timeout=${TIMEOUT}s)..."
    "$WAIT_SCRIPT" --host "${WEB_HOST}" --port "${WEB_PORT}" --proto http --path "${PATH}" --timeout "${TIMEOUT}" --interval 5 || {
      log "Dagster webserver did not become healthy within ${TIMEOUT}s"
      return 1
    }
    log "Dagster webserver is healthy"
    return 0
  fi

  # Fallback: basic curl loop
  if ! command -v curl >/dev/null 2>&1; then
    log "curl not available to probe Dagster webserver; skipping webserver health check"
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
  log "Timed out waiting for Dagster webserver"
  return 1
}

# Forward signals to the child process properly; we exec the child at the end so the kernel
# will handle signals. This helper exists for CLI-run commands executed via eval.
_forward_signal() {
  # placeholder (not used when exec-ing directly)
  :
}

# Show a usage message for the supported service modes
show_usage() {
  cat <<EOF
Usage: $0 <service> [-- <cmd>...]
Services:
  dagster-webserver   Start Dagster webserver (dev-friendly defaults)
  dagster-daemon      Start Dagster daemon (schedules); waits for dependencies
  etl-runner          Run an ad-hoc command inside the app image (pass the command after '--')
  shell               Drop into a shell (useful for debugging)
If invoked with no service or with '-- <cmd>', the provided command will be executed directly.

Examples:
  entrypoint.sh dagster-webserver
  entrypoint.sh dagster-daemon
  entrypoint.sh etl-runner -- python -m src.scripts.my_job
  entrypoint.sh -- python -c 'print(\"hello\")'
EOF
}

# Main dispatcher
main() {
  # Load environment defaults and secrets
  load_env

  # allow overriding arguments via SERVICE env var if no args provided
  if [ "$#" -eq 0 ]; then
    if [ -n "${SERVICE-}" ]; then
      set -- "$SERVICE"
    else
      show_usage
      exit 2
    fi
  fi

  service="$1"
  shift || true

  # compute exec prefix for user switching if needed
  EXEC_PREFIX="$(_make_exec_prefix)"

  case "$service" in
    dagster-webserver)
      log "Starting service: dagster-webserver"
      # Ensure Neo4j is up before starting webserver (helps CI/flaky startup)
      if ! wait_for_neo4j; then
        log "Failed dependency check: Neo4j not available"
        exit 1
      fi

      # If ENVIRONMENT=dev we prefer `dagster dev` which provides auto-reload
      if [ "${ENVIRONMENT:-dev}" = "dev" ]; then
        CMD="dagster dev -h 0.0.0.0 -p 3000"
      else
        # Production-like run (the exact production invocation may differ)
        CMD="dagster api -h 0.0.0.0 -p 3000"
      fi

      log "Exec: ${EXEC_PREFIX} ${CMD}"
      # Use sh -c with exec so that exec replaces the shell and PID 1 is the service
      if [ -n "$EXEC_PREFIX" ]; then
        # eval the full prefixed command
        eval "exec ${EXEC_PREFIX} sh -c '${CMD}'"
      else
        exec sh -c "${CMD}"
      fi
      ;;

    dagster-daemon)
      log "Starting service: dagster-daemon"
      # Wait for Neo4j and webserver to be healthy before starting the daemon
      if ! wait_for_neo4j; then
        log "Failed dependency check: Neo4j not available"
        exit 1
      fi
      # Wait for Dagster web to be available (use defaults)
      if ! wait_for_dagster_web; then
        log "Warning: Dagster webserver did not become healthy in time; proceeding anyway"
      fi

      CMD="dagster-daemon run"
      log "Exec: ${EXEC_PREFIX} ${CMD}"
      if [ -n "$EXEC_PREFIX" ]; then
        eval "exec ${EXEC_PREFIX} sh -c '${CMD}'"
      else
        exec sh -c "${CMD}"
      fi
      ;;

    etl-runner)
      # Accept an explicit command following '--'
      if [ "$#" -eq 0 ]; then
        log "No command provided for etl-runner; show usage"
        show_usage
        exit 2
      fi
      # Ensure dependencies available
      if ! wait_for_neo4j; then
        log "Failed dependency check: Neo4j not available"
        exit 1
      fi

      # Execute the provided command (preserve arguments)
      # If we have an exec prefix, prefix the command; do not use eval for arbitrary args
      if [ -n "$EXEC_PREFIX" ]; then
        # Use sh -c to allow a single string; build safely from "$@"
        CMD="$(printf '%s ' "$@")"
        log "Exec (as sbir): ${EXEC_PREFIX} sh -c '${CMD}'"
        eval "exec ${EXEC_PREFIX} sh -c '${CMD}'"
      else
        log "Exec: $@"
        exec "$@"
      fi
      ;;

    shell)
      # Start an interactive shell for debugging (use /bin/sh or /bin/bash)
      SH="${SHELL:-/bin/sh}"
      log "Starting interactive shell: ${SH}"
      if [ -n "$EXEC_PREFIX" ]; then
        eval "exec ${EXEC_PREFIX} ${SH} -l"
      else
        exec "${SH}" -l
      fi
      ;;

    --)
      # Run arbitrary command passed after '--'
      shift || true
      if [ "$#" -eq 0 ]; then
        show_usage
        exit 2
      fi
      log "Exec: $@"
      exec "$@"
      ;;

    *)
      # Fallback: treat unknown service names as direct commands if they exist
      if echo "$service" | grep -q '/'; then
        if [ -x "$service" ]; then
          log "Executing provided path: $service $*"
          exec "$service" "$@"
        else
          log "Path not executable: $service"
          exit 2
        fi
      elif command -v "$service" >/dev/null 2>&1; then
        log "Executing command from PATH: $service $*"
        exec "$service" "$@"
      else
        log "Unrecognized service: $service"
        show_usage
        exit 2
      fi
      ;;
  esac
}

# Kick off
main "$@"
