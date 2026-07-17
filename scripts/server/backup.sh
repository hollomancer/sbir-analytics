#!/usr/bin/env sh
# Offline-consistent Neo4j backup for the Mac mini server profile.

set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.server.yml}"
ENV_FILE="${SERVER_ENV_FILE:-.env.server}"
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
# shellcheck source=scripts/server/env-file.sh
. "$SCRIPT_DIR/env-file.sh"
load_env_key SERVER_BACKUP_DIR
load_env_key SERVER_NEO4J_DIR

BACKUP_DIR="${SERVER_BACKUP_DIR:-./backups}"
NEO4J_DIR="${SERVER_NEO4J_DIR:-./data/neo4j}"
DB_NAME="${NEO4J_DATABASE:-neo4j}"
STAMP="${BACKUP_STAMP:-$(date -u '+%Y%m%dT%H%M%SZ')}"
RESTART_TIMEOUT="${BACKUP_RESTART_TIMEOUT:-180}"

RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { printf "${BLUE}➤${NC} %s\n" "$1"; }
success() { printf "${GREEN}✓${NC} %s\n" "$1"; }
error()   { printf "${RED}✖${NC} %s\n" "$1" >&2; }

compose() {
  if [ -f "$ENV_FILE" ]; then
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "$@"
  else
    docker compose -f "$COMPOSE_FILE" "$@"
  fi
}

case "$DB_NAME" in
  ''|*[!A-Za-z0-9_.-]*)
    error "NEO4J_DATABASE may contain only letters, digits, dots, underscores, and hyphens."
    exit 2
    ;;
esac
case "$STAMP" in
  ''|*[!A-Za-z0-9_.-]*)
    error "BACKUP_STAMP may contain only letters, digits, dots, underscores, and hyphens."
    exit 2
    ;;
esac
case "$RESTART_TIMEOUT" in
  ''|*[!0-9]*) error "BACKUP_RESTART_TIMEOUT must be a positive integer."; exit 2 ;;
esac
[ "$RESTART_TIMEOUT" -gt 0 ] || {
  error "BACKUP_RESTART_TIMEOUT must be positive."
  exit 2
}

for pair in "backup:$BACKUP_DIR" "Neo4j data:$NEO4J_DIR"; do
  label=${pair%%:*}
  path=${pair#*:}
  if ! path_has_active_external_volume "$path"; then
    volume=$(volume_root_for_path "$path" || printf '%s' /Volumes/unknown)
    error "$label path $path requires $volume to be actively mounted."
    exit 1
  fi
done

mkdir -p "$BACKUP_DIR"
BACKUP_DIR=$(CDPATH= cd -- "$BACKUP_DIR" && pwd)
DEST="${BACKUP_DIR}/${DB_NAME}-${STAMP}.dump"

lock_dir="${BACKUP_DIR}/.neo4j-backup.lock"
if ! mkdir "$lock_dir" 2>/dev/null; then
  error "Another backup is running, or a stale lock exists: $lock_dir"
  exit 1
fi
printf '%s\n' "$$" >"$lock_dir/pid"

stage_dir=""
staged_dump=""
restart_required=0
reserved_dest=0
backup_complete=0

restart_neo4j() {
  compose --profile server up -d --no-deps --wait \
    --wait-timeout "$RESTART_TIMEOUT" neo4j >/dev/null
}

cleanup() {
  status=$?
  trap - EXIT HUP INT TERM
  set +e
  if [ "$restart_required" -eq 1 ]; then
    info "Restarting Neo4j after interrupted or failed backup..."
    if ! restart_neo4j; then
      error "Neo4j could not be restarted and become healthy; run: make server-up"
      status=1
    fi
  fi
  if [ -n "$staged_dump" ]; then
    rm -f "$staged_dump"
  fi
  if [ -n "$stage_dir" ]; then
    rmdir "$stage_dir" 2>/dev/null
  fi
  if [ "$reserved_dest" -eq 1 ] && [ "$backup_complete" -eq 0 ]; then
    rm -f "$DEST"
  fi
  rm -f "$lock_dir/pid"
  rmdir "$lock_dir" 2>/dev/null
  exit "$status"
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

# Reserve the final name atomically before stopping Neo4j. The operation lock
# prevents another invocation from racing the dump; noclobber protects against
# an independently-created file with the same timestamp.
if ! (umask 077; set -C; : >"$DEST") 2>/dev/null; then
  error "Backup already exists; refusing to overwrite: $DEST"
  exit 1
fi
reserved_dest=1

if [ -z "$(compose --profile server ps --status running -q neo4j)" ]; then
  error "Neo4j is not running. Start the server stack before backing it up."
  exit 1
fi

stage_dir=$(mktemp -d "${BACKUP_DIR}/.neo4j-backup.XXXXXX")
staged_dump="${stage_dir}/${DB_NAME}.dump"

info "Stopping Neo4j briefly for an offline-consistent dump..."
restart_required=1
if ! compose --profile server stop -t 120 neo4j; then
  error "Neo4j stop did not complete cleanly; attempting recovery."
  exit 1
fi

info "Dumping Neo4j database '$DB_NAME'..."
compose --profile server run --rm --no-deps -T \
  -v "${stage_dir}:/backup" \
  --entrypoint neo4j-admin neo4j \
  database dump "$DB_NAME" --to-path=/backup --overwrite-destination=true

if [ ! -s "$staged_dump" ]; then
  error "neo4j-admin did not produce a nonempty dump."
  exit 1
fi
chmod 600 "$staged_dump"
mv "$staged_dump" "$DEST"
reserved_dest=0
backup_complete=1

info "Restarting Neo4j..."
if ! restart_neo4j; then
  error "Backup completed, but Neo4j did not restart healthy; run: make server-up"
  exit 1
fi
restart_required=0

success "Backup written: $DEST"
info "Copy this off-device (the external SSD is not a backup by itself)."
