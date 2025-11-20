#!/usr/bin/env sh
# sbir-analytics/scripts/neo4j/bootstrap_users.sh
#
# Bootstrap Neo4j users and roles for SBIR ETL.
#
# Responsibilities:
#  - Optionally rotate the admin password
#  - Create an ingest user with an 'ingest' role for loaders
#  - Create a read-only user with a 'readonly' role for analysts
#  - Idempotent: will not recreate users/roles if they already exist
#
# Usage:
#   ./bootstrap_users.sh [--rotate-admin NEW_ADMIN_PASSWORD] [--ingest-user NAME:PASS] [--readonly-user NAME:PASS] [--dry-run] [--yes]
#
# Examples:
#   # Create default users (ingest: sbir_ingest / sbir_ingest_pass, readonly: sbir_ro / sbir_ro_pass)
#   ./bootstrap_users.sh
#
#   # Rotate admin password and use custom names/passwords:
#   ./bootstrap_users.sh --rotate-admin "newAdminPass!" \
#       --ingest-user ingest_user:ingest_pass \
#       --readonly-user ro_user:ro_pass
#
# Environment (defaults can be overridden):
#   NEO4J_URI            (bolt URI)        default: bolt://neo4j:7687
#   NEO4J_USER           (admin user)      default: neo4j
#   NEO4J_PASSWORD       (admin password)  required unless running in dry-run
#
# Notes:
# - This script uses `cypher-shell` to execute user/role management commands.
# - Provide credentials via environment (.env) or CI secrets. Do not commit passwords.
# - The script attempts to be conservative: it checks for existence before creating users/roles.
#
# Exit codes:
#  0 - success (or dry-run)
#  >0 - on failure
set -eu

# Basic helpers
log() {
  printf '%s %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

err() {
  log "ERROR: $*"
  exit 1
}

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --rotate-admin NEW_PASS       Rotate admin (NEO4J_USER) password to NEW_PASS
  --ingest-user NAME:PASS       Create ingest user with NAME and PASS (default: sbir_ingest:sbir_ingest_pass)
  --readonly-user NAME:PASS     Create read-only user with NAME and PASS (default: sbir_ro:sbir_ro_pass)
  --dry-run                     Print actions but do not execute cypher commands
  --yes                         Skip interactive confirmation prompts
  -h, --help                    Show this help and exit
EOF
  exit 0
}

# Default values
NEO4J_URI="${NEO4J_URI:-bolt://neo4j:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-}"
INGEST_USER="${INGEST_USER:-sbir_ingest}"
INGEST_PASSWORD="${INGEST_PASSWORD:-sbir_ingest_pass}"
READONLY_USER="${READONLY_USER:-sbir_ro}"
READONLY_PASSWORD="${READONLY_PASSWORD:-sbir_ro_pass}"

# Parsed options
ROTATE_ADMIN_PASS=""
DRY_RUN=0
ASSUME_YES=0

# Parse args (simple)
while [ "${#:-}" -gt 0 ] && [ "${1:-}" != "" ]; do
  case "$1" in
    --rotate-admin)
      shift
      ROTATE_ADMIN_PASS="${1:-}"
      ;;
    --ingest-user)
      shift
      val="${1:-}"
      INGEST_USER="$(printf '%s' "$val" | awk -F: '{print $1}')"
      INGEST_PASSWORD="$(printf '%s' "$val" | awk -F: '{print $2}')"
      ;;
    --readonly-user)
      shift
      val="${1:-}"
      READONLY_USER="$(printf '%s' "$val" | awk -F: '{print $1}')"
      READONLY_PASSWORD="$(printf '%s' "$val" | awk -F: '{print $2}')"
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
      err "Unknown argument: $1"
      ;;
  esac
  shift || break
done

# Check for cypher-shell
if ! command -v cypher-shell >/dev/null 2>&1; then
  err "cypher-shell not found in PATH. Please install or run this script from an environment image that includes it."
fi

# If not dry-run, ensure NEO4J_PASSWORD provided
if [ "${DRY_RUN}" -eq 0 ] && [ -z "${NEO4J_PASSWORD}" ]; then
  err "NEO4J_PASSWORD is not set in environment. Set it or run with --dry-run."
fi

# Build cypher-shell connection args
CYSH_OPTS=""
# cypher-shell accepts --address / -a and -u -p
CYSH_OPTS="${CYSH_OPTS} -a ${NEO4J_URI} -u ${NEO4J_USER}"
# For password, we'll pass -p when invoking (to avoid exposing in ps, but shell will still show the command)
# We'll create a helper to run queries.
run_cypher() {
  # usage: run_cypher "CYPHER QUERY"
  query="$1"
  if [ "${DRY_RUN}" -eq 1 ]; then
    printf '%s\n' "-- DRY-RUN: would run query:" "$query"
    return 0
  fi
  printf '%s\n' "$query" | cypher-shell ${CYSH_OPTS} -p "${NEO4J_PASSWORD}" 2>&1
}

# Check helper: whether a user exists
user_exists() {
  uname="$1"
  # SHOW USERS lists users; we search by name (case-insensitive)
  if [ "${DRY_RUN}" -eq 1 ]; then
    # Can't detect in dry-run; assume false
    return 1
  fi
  out="$(printf 'SHOW USERS' | cypher-shell ${CYSH_OPTS} -p "${NEO4J_PASSWORD}" 2>/dev/null || true)"
  # The output typically contains a header; we check for uname existence
  echo "$out" | awk '{print tolower($0)}' | grep -q -F "$(printf '%s' "$uname" | tr '[:upper:]' '[:lower:]')" || return 1
  return 0
}

# Check helper: whether a role exists
role_exists() {
  role="$1"
  if [ "${DRY_RUN}" -eq 1 ]; then
    return 1
  fi
  out="$(printf 'SHOW ROLES' | cypher-shell ${CYSH_OPTS} -p "${NEO4J_PASSWORD}" 2>/dev/null || true)"
  echo "$out" | awk '{print tolower($0)}' | grep -q -F "$(printf '%s' "$role" | tr '[:upper:]' '[:lower:]')" || return 1
  return 0
}

# Prompt for confirmation (unless --yes)
confirm_or_die() {
  if [ "${ASSUME_YES}" -eq 1 ]; then
    return 0
  fi
  printf '\n'
  printf '%s\n' "$1"
  printf 'Proceed? [y/N]: '
  read ans || true
  case "$ans" in
    [yY]|[yY][eE][sS]) return 0 ;;
    *) err "Aborted by user." ;;
  esac
}

# Main operations

log "Neo4j bootstrap: starting (URI=${NEO4J_URI}, admin=${NEO4J_USER})"

# 1) Rotate admin password if requested
if [ -n "${ROTATE_ADMIN_PASS}" ]; then
  log "Requested admin password rotation for user ${NEO4J_USER}"
  confirm_or_die "Will rotate admin password for ${NEO4J_USER}. This will change the password used for subsequent operations in this script."
  if [ "${DRY_RUN}" -eq 1 ]; then
    log "DRY-RUN: would run ALTER USER to set password for ${NEO4J_USER}"
  else
    # Use ALTER USER to set password (idempotent for existing user)
    # Note: ALTER USER ... SET PASSWORD is supported in Neo4j 4.x+
    run_cypher "ALTER USER ${NEO4J_USER} SET PASSWORD '${ROTATE_ADMIN_PASS}' CHANGE NOT REQUIRED;"
    # Update the in-memory password variable so subsequent operations use the new one
    NEO4J_PASSWORD="${ROTATE_ADMIN_PASS}"
    log "Admin password rotated; subsequent operations will use the new password."
  fi
fi

# 2) Ensure roles exist: 'ingest' and 'readonly'
for role in ingest readonly; do
  log "Ensuring role '${role}' exists"
  if role_exists "${role}"; then
    log "Role '${role}' already exists; skipping creation."
  else
    log "Role '${role}' does not exist; creating."
    confirm_or_die "About to create role '${role}'."
    run_cypher "CREATE ROLE ${role};"
    log "Role '${role}' created."
  fi
done

# 3) Ensure ingest user exists and has 'ingest' role
log "Ensuring ingest user exists (${INGEST_USER})"
if user_exists "${INGEST_USER}"; then
  log "User ${INGEST_USER} already exists. Attempting to ensure role membership."
  # Grant role if missing
  # We can't easily detect role membership via cypher-shell in a simple portable manner, so attempt grant (idempotent)
  log "Granting ROLE ingest to ${INGEST_USER} (idempotent)"
  run_cypher "GRANT ROLE ingest TO ${INGEST_USER};"
else
  log "Creating user ${INGEST_USER}"
  confirm_or_die "Will create user '${INGEST_USER}' with provided password."
  # Create user and set password; mark CHANGE NOT REQUIRED for automation
  run_cypher "CREATE USER ${INGEST_USER} SET PASSWORD '${INGEST_PASSWORD}' CHANGE NOT REQUIRED;"
  run_cypher "GRANT ROLE ingest TO ${INGEST_USER};"
  log "Created user ${INGEST_USER} and granted ROLE ingest."
fi

# 4) Ensure readonly user exists and has 'readonly' role
log "Ensuring readonly user exists (${READONLY_USER})"
if user_exists "${READONLY_USER}"; then
  log "User ${READONLY_USER} already exists. Ensuring role membership."
  log "Granting ROLE readonly to ${READONLY_USER} (idempotent)"
  run_cypher "GRANT ROLE readonly TO ${READONLY_USER};"
else
  log "Creating user ${READONLY_USER}"
  confirm_or_die "Will create user '${READONLY_USER}' with provided password."
  run_cypher "CREATE USER ${READONLY_USER} SET PASSWORD '${READONLY_PASSWORD}' CHANGE NOT REQUIRED;"
  run_cypher "GRANT ROLE readonly TO ${READONLY_USER};"
  log "Created user ${READONLY_USER} and granted ROLE readonly."
fi

# 5) (Optional) Provide a summary
log "Bootstrap actions complete. Summary:"
log "  - admin user: ${NEO4J_USER} (password changed: ${ROTATE_ADMIN_PASS:+yes}${ROTATE_ADMIN_PASS:-no})"
log "  - ingest user: ${INGEST_USER}"
log "  - readonly user: ${READONLY_USER}"
log "Reminder: do not commit credentials to version control. Store in .env or your secret manager."

exit 0
