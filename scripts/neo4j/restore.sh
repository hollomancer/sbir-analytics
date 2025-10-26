#!/usr/bin/env sh
# sbir-etl/scripts/neo4j/restore.sh
#
# Restore a Neo4j logical dump into the repository's Neo4j data volume.
#
# This script supports two main modes:
#  - Restoring into a Docker-managed Neo4j data volume (preferred)
#  - Restoring using a local `neo4j-admin` binary (fallback)
#
# The script attempts a safe approach:
#  1. If a running Docker Neo4j container is detected it will stop it (unless overridden),
#     run a temporary container (same image) that mounts the Neo4j volume and the backup file,
#     invoke `neo4j-admin load --from=... --database=... --force`, then restart the original container.
#  2. If Docker is not available, the script will attempt to run a local `neo4j-admin load` and
#     will warn about the need to ensure the DB is offline.
#
# Important safety notes:
#  - Restoring will overwrite the target database. Backups are destructive for the target DB.
#  - Always validate the backup file and ensure you have an additional backup copy before proceeding.
#  - Provide credentials and secrets via environment variables or secret mounts; do NOT commit them.
#
# Usage:
#   ./restore.sh --backup-path /path/to/neo4j-db-20250101.dump --db neo4j
#
# Options:
#   --backup-path PATH     Path to the dump file (required)
#   --db NAME              Database name to restore into (default: neo4j)
#   --container NAME       Docker container name to target (default: sbir-neo4j or sbir-neo4j-standalone)
#   --force                Pass --force to neo4j-admin load (overwrites without extra prompt)
#   --dry-run              Print actions but do not execute commands
#   --yes                  Assume "yes" to confirmation prompts
#   -h, --help             Show this help
#
# Examples:
#   BACKUP_PATH=backups/neo4j/neo4j-20250101.dump ./restore.sh --db neo4j
#   ./restore.sh --backup-path /tmp/neo4j.dump --container sbir-neo4j --yes
#
set -eu

log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

die() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "ERROR: $*" >&2
  exit 1
}

usage() {
  cat <<EOF
Usage: $0 --backup-path PATH [options]

Options:
  --backup-path PATH     Path to the dump file (required)
  --db NAME              Database name to restore into (default: neo4j)
  --container NAME       Docker container name to target (default: sbir-neo4j or sbir-neo4j-standalone)
  --force                Pass --force to neo4j-admin load
  --dry-run              Print actions but do not execute commands
  --yes                  Assume yes to prompts
  -h, --help             Show this help
EOF
  exit 0
}

# Defaults
BACKUP_PATH=""
DB_NAME="neo4j"
CONTAINER_NAME=""
FORCE_FLAG=0
DRY_RUN=0
ASSUME_YES=0

# Simple arg parsing
while [ $# -gt 0 ]; do
  case "$1" in
    --backup-path)
      shift
      BACKUP_PATH="${1:-}"
      ;;
    --db)
      shift
      DB_NAME="${1:-}"
      ;;
    --container)
      shift
      CONTAINER_NAME="${1:-}"
      ;;
    --force)
      FORCE_FLAG=1
      ;;
    --dry-run)
      DRY_RUN=1
      ;;
    --yes)
      ASSUME_YES=1
      ;;
    -h|--help)
      usage
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
  shift || break
done

if [ -z "$BACKUP_PATH" ]; then
  die "Missing required --backup-path argument"
fi

if [ ! -f "$BACKUP_PATH" ]; then
  die "Backup file not found: $BACKUP_PATH"
fi

BACKUP_BASENAME="$(basename "$BACKUP_PATH")"
BACKUP_DIRNAME="$(cd "$(dirname "$BACKUP_PATH")" >/dev/null 2>&1 && pwd -P)"

confirm_or_die() {
  if [ "$ASSUME_YES" -eq 1 ]; then
    return 0
  fi
  printf '\n'
  printf '%s\n' "$1"
  printf 'Proceed? [y/N]: '
  read ans || true
  case "$ans" in
    [yY]|[yY][eE][sS]) return 0 ;;
    *) die "Aborted by user." ;;
  esac
}

run_or_dry() {
  if [ "$DRY_RUN" -eq 1 ]; then
    log "DRY-RUN: $*"
  else
    sh -c "$*"
  fi
}

# Helper: detect docker container if present
detect_docker_container() {
  # prefer an explicit container name if supplied
  if [ -n "$CONTAINER_NAME" ]; then
    if docker ps --format '{{.Names}}' | grep -q -x "$CONTAINER_NAME"; then
      printf '%s' "$CONTAINER_NAME"
      return 0
    fi
    # also consider stopped container by same name
    if docker ps -a --format '{{.Names}}' | grep -q -x "$CONTAINER_NAME"; then
      printf '%s' "$CONTAINER_NAME"
      return 0
    fi
    return 1
  fi

  # fallback detect common names
  if docker ps --format '{{.Names}}' | grep -q -x "sbir-neo4j"; then
    printf 'sbir-neo4j'
    return 0
  fi
  if docker ps --format '{{.Names}}' | grep -q -x "sbir-neo4j-standalone"; then
    printf 'sbir-neo4j-standalone'
    return 0
  fi

  # look for any running container based on a neo4j image
  cont="$(docker ps --filter "ancestor=neo4j" --format '{{.Names}}' | head -n 1 || true)"
  if [ -n "$cont" ]; then
    printf '%s' "$cont"
    return 0
  fi

  # also consider stopped neo4j container
  cont="$(docker ps -a --filter "ancestor=neo4j" --format '{{.Names}}' | head -n 1 || true)"
  if [ -n "$cont" ]; then
    printf '%s' "$cont"
    return 0
  fi

  return 1
}

# Strategy:
# 1) If docker available and a container/volume found -> attempt docker-based restore
# 2) Else fallback to local neo4j-admin invocation (requires admin tools and DB offline)
if command -v docker >/dev/null 2>&1; then
  # Try to detect target container
  if cont="$(detect_docker_container 2>/dev/null || true)"; then
    log "Detected Neo4j container candidate: ${cont}"
    CONTAINER_NAME_DETECTED="$cont"
  else
    log "No Neo4j container detected via docker"
    CONTAINER_NAME_DETECTED=""
  fi
else
  log "Docker CLI not available on PATH"
  CONTAINER_NAME_DETECTED=""
fi

# If we have a docker container, attempt the docker-based restore
if [ -n "$CONTAINER_NAME_DETECTED" ]; then
  log "Preparing docker-based restore into container '${CONTAINER_NAME_DETECTED}' (database=${DB_NAME})"
  confirm_or_die "This will overwrite database '${DB_NAME}' in the Neo4j data volume used by container '${CONTAINER_NAME_DETECTED}'. Ensure you have a separate backup copy. Continue?"

  # Inspect container for image and data volume name mapped to /data
  IMAGE_NAME="$(docker inspect --format '{{.Config.Image}}' "${CONTAINER_NAME_DETECTED}" 2>/dev/null || true)"
  if [ -z "$IMAGE_NAME" ]; then
    die "Could not determine image for container ${CONTAINER_NAME_DETECTED}"
  fi
  log "Container image: ${IMAGE_NAME}"

  # attempt to find the named volume mounted at /data
  DATA_VOLUME="$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "${CONTAINER_NAME_DETECTED}" 2>/dev/null || true)"
  if [ -z "$DATA_VOLUME" ]; then
    # fallback: try common volume names
    if docker volume ls --format '{{.Name}}' | grep -q -x "neo4j_data"; then
      DATA_VOLUME="neo4j_data"
    elif docker volume ls --format '{{.Name}}' | grep -q -x "sbir-neo4j_data"; then
      DATA_VOLUME="sbir-neo4j_data"
    else
      # if still empty, warn and ask user to provide container or volume explicitly
      log "Could not auto-detect the Neo4j data volume for container '${CONTAINER_NAME_DETECTED}'"
      die "Please pass --container with an explicit container name or ensure your container mounts a named volume at /data"
    fi
  fi
  log "Detected data volume: ${DATA_VOLUME}"

  # Record whether the container is running so we can stop/start it
  RUNNING=0
  if docker ps --format '{{.Names}}' | grep -q -x "${CONTAINER_NAME_DETECTED}"; then
    RUNNING=1
  fi

  # Stop container if running
  if [ "$RUNNING" -eq 1 ]; then
    log "Stopping container ${CONTAINER_NAME_DETECTED} (it is running now)"
    if [ "$DRY_RUN" -eq 1 ]; then
      log "DRY-RUN: docker stop ${CONTAINER_NAME_DETECTED}"
    else
      docker stop "${CONTAINER_NAME_DETECTED}" || die "Failed to stop container ${CONTAINER_NAME_DETECTED}"
    fi
  else
    log "Container ${CONTAINER_NAME_DETECTED} is not running (will operate on its volumes)"
  fi

  # Run a temporary container using the same image, mounting the data volume and the backup directory
  log "Running temporary container to perform neo4j-admin load"
  TMP_RUN_CMD="docker run --rm -v ${DATA_VOLUME}:/data -v ${BACKUP_DIRNAME}:/backups ${IMAGE_NAME} neo4j-admin load --from=/backups/${BACKUP_BASENAME} --database=${DB_NAME}"
  if [ "$FORCE_FLAG" -eq 1 ]; then
    TMP_RUN_CMD="${TMP_RUN_CMD} --force"
  fi

  run_or_dry "$TMP_RUN_CMD" || {
    # If the load failed, consider restarting the container to restore service and surface logs (user assistance)
    log "Restore operation failed inside temporary container"
    if [ "$RUNNING" -eq 1 ]; then
      log "Attempting to restart original container ${CONTAINER_NAME_DETECTED} to restore service"
      if [ "$DRY_RUN" -eq 1 ]; then
        log "DRY-RUN: docker start ${CONTAINER_NAME_DETECTED}"
      else
        docker start "${CONTAINER_NAME_DETECTED}" || log "Warning: failed to restart ${CONTAINER_NAME_DETECTED}; manual intervention may be required"
      fi
    fi
    die "neo4j-admin load failed; consult container logs for details"
  }

  log "neo4j-admin load completed successfully"

  # Restart original container if it was running before
  if [ "$RUNNING" -eq 1 ]; then
    log "Starting container ${CONTAINER_NAME_DETECTED}"
    if [ "$DRY_RUN" -eq 1 ]; then
      log "DRY-RUN: docker start ${CONTAINER_NAME_DETECTED}"
    else
      docker start "${CONTAINER_NAME_DETECTED}" || die "Failed to start container ${CONTAINER_NAME_DETECTED}"
    fi
    log "Container ${CONTAINER_NAME_DETECTED} started"
  fi

  log "Restore finished. Verify database health and connectivity (cypher-shell or HTTP /server_info)."
  exit 0
fi

# If Docker path not taken, fallback to local neo4j-admin invocation
log "Fallback: attempting local neo4j-admin restore"
if ! command -v neo4j-admin >/dev/null 2>&1; then
  die "neo4j-admin binary not found on PATH. Install Neo4j tools or use the docker-based restore by running this script on a host with Docker."
fi

log "Local restore into database '${DB_NAME}' using neo4j-admin"
log "WARNING: The target Neo4j server must be offline for neo4j-admin load to succeed. Ensure you have stopped the Neo4j service and have a backup."

confirm_or_die "About to run local neo4j-admin load, which will overwrite database '${DB_NAME}'. Ensure the DB is stopped. Continue?"

LOCAL_CMD="neo4j-admin load --from='${BACKUP_PATH}' --database='${DB_NAME}'"
if [ "$FORCE_FLAG" -eq 1 ]; then
  LOCAL_CMD="${LOCAL_CMD} --force"
fi

run_or_dry "$LOCAL_CMD" || die "Local neo4j-admin load failed"

log "Local neo4j-admin load completed. Start Neo4j and verify database health."

exit 0
