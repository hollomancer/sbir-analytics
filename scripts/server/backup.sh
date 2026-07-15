#!/usr/bin/env sh
# sbir-analytics/scripts/server/backup.sh
#
# Offline-consistent Neo4j backup for the Mac mini server profile.
#
# Uses `neo4j-admin database dump` inside the running Neo4j container and copies
# the dump to ${SERVER_BACKUP_DIR}. The Compose stack keeps running; only the
# `neo4j` database is briefly quiesced by neo4j-admin as needed.
#
# Env (from .env.server):
#   SERVER_BACKUP_DIR   destination for dumps (default ./backups)
#   NEO4J_CONTAINER_NAME  container to target (default sbir-server-neo4j)
#
# Usage:
#   scripts/server/backup.sh

set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.server.yml}"
ENV_FILE="${SERVER_ENV_FILE:-.env.server}"
BACKUP_DIR="${SERVER_BACKUP_DIR:-./backups}"
DB_NAME="${NEO4J_DATABASE:-neo4j}"

RED='\033[0;31m'; GREEN='\033[0;32m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { printf "${BLUE}➤${NC} %s\n" "$1"; }
success() { printf "${GREEN}✓${NC} %s\n" "$1"; }
error()   { printf "${RED}✖${NC} %s\n" "$1"; }

COMPOSE="docker compose -f ${COMPOSE_FILE}"
if [ -f "$ENV_FILE" ]; then
  COMPOSE="docker compose -f ${COMPOSE_FILE} --env-file ${ENV_FILE}"
fi

# Timestamp is passed in so the script stays deterministic for callers/tests.
STAMP="${BACKUP_STAMP:-$(date -u '+%Y%m%dT%H%M%SZ')}"
mkdir -p "$BACKUP_DIR"

info "Dumping Neo4j database '${DB_NAME}' inside the container..."
# Dump to a temp path inside the container, then copy out.
$COMPOSE --profile server exec -T neo4j sh -c \
  "neo4j-admin database dump ${DB_NAME} --to-path=/tmp/backup --overwrite-destination=true" \
  || { error "neo4j-admin dump failed"; exit 1; }

CID="$($COMPOSE --profile server ps -q neo4j)"
if [ -z "$CID" ]; then
  error "Could not resolve the neo4j container id."
  exit 1
fi

DEST="${BACKUP_DIR}/${DB_NAME}-${STAMP}.dump"
docker cp "${CID}:/tmp/backup/${DB_NAME}.dump" "$DEST"
success "Backup written: ${DEST}"
info "Copy this off-device (the external SSD is not a backup by itself)."
