#!/usr/bin/env sh
# sbir-etl/scripts/neo4j/backup.sh
#
# Create a logical dump of the Neo4j database and store it under a host backups directory.
# Supports running against a running Docker container (preferred) or against a local neo4j-admin binary.
#
# Usage:
#   # Default: backup 'neo4j' database into backups/neo4j/<timestamp>.dump and keep last 7 files
#   ./sbir-etl/scripts/neo4j/backup.sh
#
#   # Custom directory, database name, and retention (keep last N)
#   BACKUP_DIR=backups/neo4j DB_NAME=neo4j KEEP_LAST=14 ./sbir-etl/scripts/neo4j/backup.sh
#
# Environment / options:
#   BACKUP_DIR        Host directory where backups are stored (default: backups/neo4j)
#   DB_NAME           Neo4j database name to dump (default: neo4j)
#   NEO4J_CONTAINER   Preferred Docker container name (script will try defaults if not set)
#   KEEP_LAST         Number of most-recent backups to keep (default: 7). If 0, no pruning.
#   RETENTION_DAYS    Alternative retention by age in days (used if KEEP_LAST unset or 0)
#   DRY_RUN           If "1", prints actions but does not execute destructive commands.
#
# Notes:
# - This script attempts to use docker exec + neo4j-admin when a container is running.
# - If no docker container is found, it will attempt to run a local `neo4j-admin` binary.
# - neo4j-admin dump may require the database to be offline depending on Neo4j version/config;
#   validate on your Neo4j version. For large datasets consider stopping writes or using enterprise backup tools.
#
set -eu

# ---- Configuration ----
BACKUP_DIR="${BACKUP_DIR:-backups/neo4j}"
DB_NAME="${DB_NAME:-neo4j}"
KEEP_LAST="${KEEP_LAST:-7}"
RETENTION_DAYS="${RETENTION_DAYS:-0}"
DRY_RUN="${DRY_RUN:-0}"

# Prefer these container names if present
NEO4J_CONTAINER="${NEO4J_CONTAINER:-sbir-neo4j}"
NEO4J_CONTAINER_ALT="${NEO4J_CONTAINER_ALT:-sbir-neo4j-standalone}"

# Timestamp and filenames
TIMESTAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
FILENAME="${DB_NAME}-${TIMESTAMP}.dump"
TMP_CONTAINER_DIR="/backups"
CONTAINER_TMP_PATH="${TMP_CONTAINER_DIR}/${FILENAME}"
HOST_TARGET_DIR="${BACKUP_DIR}"
HOST_TARGET_PATH="${HOST_TARGET_DIR}/${FILENAME}"

log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

die() {
  log "ERROR: $*"
  exit 1
}

run_or_dry() {
  if [ "${DRY_RUN}" = "1" ]; then
    log "DRY-RUN: $*"
  else
    sh -c "$*"
  fi
}

# Create host backup directory
if [ "${DRY_RUN}" = "1" ]; then
  log "DRY-RUN: ensure host backup dir exists: ${HOST_TARGET_DIR}"
else
  mkdir -p "${HOST_TARGET_DIR}" || die "Failed to create backup directory ${HOST_TARGET_DIR}"
fi

# Determine whether a suitable Neo4j docker container is running
docker_container_available() {
  if command -v docker >/dev/null 2>&1; then
    # Check preferred container
    if docker ps --format '{{.Names}}' | grep -q -x "${NEO4J_CONTAINER}"; then
      echo "${NEO4J_CONTAINER}"
      return 0
    fi
    # Check alternate name
    if docker ps --format '{{.Names}}' | grep -q -x "${NEO4J_CONTAINER_ALT}"; then
      echo "${NEO4J_CONTAINER_ALT}"
      return 0
    fi
    # Otherwise try to detect any neo4j container by image
    # pick the first running container whose image contains 'neo4j'
    cont="$(docker ps --filter "ancestor=neo4j" --format '{{.Names}}' | head -n 1 || true)"
    if [ -n "${cont}" ]; then
      echo "${cont}"
      return 0
    fi
  fi
  return 1
}

# Perform a dump via docker exec (preferred)
do_docker_backup() {
  container="$1"
  log "Using Docker container: ${container}"
  # Ensure /backups exists in container (create as root)
  if [ "${DRY_RUN}" = "1" ]; then
    log "DRY-RUN: docker exec ${container} mkdir -p ${TMP_CONTAINER_DIR} && chown neo4j:neo4j ${TMP_CONTAINER_DIR}"
  else
    docker exec "${container}" sh -c "mkdir -p '${TMP_CONTAINER_DIR}' && chown neo4j:neo4j '${TMP_CONTAINER_DIR}'" || die "Failed to create ${TMP_CONTAINER_DIR} in container ${container}"
  fi

  # Run neo4j-admin dump inside container. We run as the image user if possible.
  # Note: depending on image, neo4j-admin may require to be run as 'neo4j' user; running as root is also acceptable on many images.
  log "Starting neo4j-admin dump for database '${DB_NAME}' inside container ${container} (to ${CONTAINER_TMP_PATH})"
  if [ "${DRY_RUN}" = "1" ]; then
    log "DRY-RUN: docker exec ${container} neo4j-admin dump --database='${DB_NAME}' --to='${CONTAINER_TMP_PATH}'"
  else
    # Try running as neo4j user, fallback to root if exit code non-zero
    if docker exec --user neo4j "${container}" sh -c "neo4j-admin dump --database='${DB_NAME}' --to='${CONTAINER_TMP_PATH}'" >/dev/null 2>&1; then
      log "neo4j-admin dump completed inside container (as neo4j)"
    else
      log "neo4j-admin dump as 'neo4j' user failed; retrying as root to capture diagnostic output"
      # Run and stream output to help debugging if it fails
      if ! docker exec "${container}" sh -c "neo4j-admin dump --database='${DB_NAME}' --to='${CONTAINER_TMP_PATH}'"; then
        die "neo4j-admin dump failed inside container ${container}"
      fi
    fi
  fi

  # Copy dump file out to host
  log "Copying dump from container:${CONTAINER_TMP_PATH} to host:${HOST_TARGET_PATH}"
  if [ "${DRY_RUN}" = "1" ]; then
    log "DRY-RUN: docker cp ${container}:${CONTAINER_TMP_PATH} ${HOST_TARGET_PATH}"
  else
    docker cp "${container}:${CONTAINER_TMP_PATH}" "${HOST_TARGET_PATH}" || die "docker cp failed"
    # Remove temporary file inside container to avoid filling disk
    docker exec "${container}" sh -c "rm -f '${CONTAINER_TMP_PATH}' || true" || log "Warning: could not remove ${CONTAINER_TMP_PATH} inside ${container}"
  fi
  log "Backup successful: ${HOST_TARGET_PATH}"
}

# Perform a local neo4j-admin backup (if neo4j-admin exists locally)
do_local_backup() {
  log "Attempting local neo4j-admin backup to ${HOST_TARGET_PATH}"
  if [ "${DRY_RUN}" = "1" ]; then
    log "DRY-RUN: neo4j-admin dump --database='${DB_NAME}' --to='${HOST_TARGET_PATH}'"
  else
    if ! command -v neo4j-admin >/dev/null 2>&1; then
      die "neo4j-admin not found locally. Install Neo4j tools or run this script against a running Neo4j container."
    fi
    neo4j-admin dump --database="${DB_NAME}" --to="${HOST_TARGET_PATH}" || die "Local neo4j-admin dump failed"
    log "Local backup successful: ${HOST_TARGET_PATH}"
  fi
}

# Prune old backups: keep most recent KEEP_LAST files OR remove files older than RETENTION_DAYS when KEEP_LAST=0
prune_old_backups() {
  # Only prune if KEEP_LAST > 0 or RETENTION_DAYS > 0
  if [ "${KEEP_LAST:-0}" -gt 0 ]; then
    log "Pruning backups to keep latest ${KEEP_LAST} files in ${HOST_TARGET_DIR}"
    if [ "${DRY_RUN}" = "1" ]; then
      log "DRY-RUN: Would prune files older than the most recent ${KEEP_LAST} files"
      return 0
    fi
    # List backup files sorted by modification time (newest first)
    # Keep the first KEEP_LAST, remove the rest
    # Use POSIX-compatible utilities
    set +e
    files_to_delete="$(ls -1t "${HOST_TARGET_DIR}" 2>/dev/null | sed -n "$((KEEP_LAST + 1)),\$p")"
    set -e
    if [ -n "${files_to_delete}" ]; then
      echo "${files_to_delete}" | while IFS= read -r f; do
        rm -f "${HOST_TARGET_DIR}/${f}" && log "Pruned old backup: ${HOST_TARGET_DIR}/${f}"
      done
    else
      log "No backups to prune (fewer than ${KEEP_LAST} present)"
    fi
  elif [ "${RETENTION_DAYS:-0}" -gt 0 ]; then
    log "Pruning backups older than ${RETENTION_DAYS} days in ${HOST_TARGET_DIR}"
    if [ "${DRY_RUN}" = "1" ]; then
      log "DRY-RUN: find ${HOST_TARGET_DIR} -type f -mtime +${RETENTION_DAYS} -print"
      return 0
    fi
    find "${HOST_TARGET_DIR}" -type f -mtime +"${RETENTION_DAYS}" -print -exec rm -f {} \; | while IFS= read -r p; do
      log "Pruned old backup: ${p}"
    done
  else
    log "No pruning requested (KEEP_LAST=${KEEP_LAST}, RETENTION_DAYS=${RETENTION_DAYS})"
  fi
}

# ---- Main ----
log "Starting Neo4j backup for database: ${DB_NAME}"
log "Host backup dir: ${HOST_TARGET_DIR}"
log "Output filename: ${FILENAME}"
log "Retention policy: KEEP_LAST=${KEEP_LAST}, RETENTION_DAYS=${RETENTION_DAYS}"

# Attempt docker backup first if docker exists and container available
if command -v docker >/dev/null 2>&1; then
  if container="$(docker_container_available)"; then
    do_docker_backup "${container}"
    prune_old_backups
    exit 0
  else
    log "No running Neo4j Docker container detected (looked for '${NEO4J_CONTAINER}'/'${NEO4J_CONTAINER_ALT}' or image 'neo4j')"
  fi
else
  log "Docker CLI not available on PATH"
fi

# Fallback: local neo4j-admin
do_local_backup
prune_old_backups
exit 0
