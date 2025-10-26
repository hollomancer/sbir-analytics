# Neo4j Server Runbook — SBIR ETL

This runbook describes how to run, configure, bootstrap, back up, and restore the Neo4j server used by the SBIR ETL project. It also documents health checks, troubleshooting steps, and recommended workflows for development and CI.

Locations referenced in this runbook:
- Compose override for standalone Neo4j: `docker/neo4j.compose.override.yml`
  ```sbir-etl/docker/neo4j.compose.override.yml#L1-120
  (see file in repository for the exact content and usage notes)
  ```
- Neo4j runtime config template: `config/neo4j/neo4j.conf`
  ```sbir-etl/config/neo4j/neo4j.conf#L1-200
  (tunable memory, connectors, TLS placeholders, and paths)
  ```
- Helper scripts:
  - Bootstrap users: `scripts/neo4j/bootstrap_users.sh`
    ```sbir-etl/scripts/neo4j/bootstrap_users.sh#L1-240
    (idempotent user/role creation and optional admin rotation)
    ```
  - Schema apply scaffold: `scripts/neo4j/apply_schema.py`
    ```sbir-etl/scripts/neo4j/apply_schema.py#L1-240
    (idempotent index/constraint application scaffold)
    ```
  - Backup: `scripts/neo4j/backup.sh`
    ```sbir-etl/scripts/neo4j/backup.sh#L1-220
    (exports logical dumps and prunes old backups)
    ```
  - Restore: `scripts/neo4j/restore.sh`
    ```sbir-etl/scripts/neo4j/restore.sh#L1-300
    (safe restore using container volumes or local tools)
    ```
- Makefile neo4j helpers: top-level `Makefile` targets include `neo4j-up`, `neo4j-down`, `neo4j-reset`, `neo4j-backup`, `neo4j-restore`, `neo4j-check`.
  ```sbir-etl/Makefile#L140-220
  (neo4j targets and usage)
  ```

Principles
- Keep secrets out of repository files. Use `.env` (gitignored), environment injection via CI, or secret mounts (`/run/secrets/...`) at runtime.
- For development, prefer bind mounts and the `neo4j` profile so you can iterate and inspect volumes easily.
- For CI, the test compose overlay provides an ephemeral Neo4j instance; the artifact image used by tests should be the same as what the CI build produced.

Quick start — local development
1. Copy `.env.example` → `.env` and set Neo4j credentials:
```sbir-etl/.env.example#L1-20
cp .env.example .env
# Edit .env: set NEO4J_USER, NEO4J_PASSWORD, and other values as needed.
```

2. Start a standalone Neo4j (dev) using the override compose:
```sbir-etl/docker/neo4j.compose.override.yml#L1-40
# Using Makefile wrapper:
make neo4j-up

# Or directly:
docker compose --env-file .env -f docker-compose.yml -f docker/neo4j.compose.override.yml --profile neo4j up --build -d
```

3. Verify health:
```sbir-etl/Makefile#L160-180
# Lightweight check via Makefile:
make neo4j-check

# Or manually:
docker compose exec neo4j sh -c "cypher-shell -u ${NEO4J_USER} -p ${NEO4J_PASSWORD} 'RETURN 1'"
```

Configuration (env vars)
- NEO4J_AUTH — full `user/password` (preferred if used)
- NEO4J_USER — admin username (default: `neo4j`)
- NEO4J_PASSWORD / NEO4J_ADMIN_PASSWORD — admin password (do not commit)
- NEO4J_READONLY_PASSWORD — optional, password for read-only analyst user
- NEO4J_PLUGINS — optional plugin list (e.g., `["apoc"]`)
- NEO4J_dbms_memory_pagecache_size — pagecache size (e.g., `256M`)
- NEO4J_dbms_memory_heap_max__size — JVM heap max (e.g., `512M`)
- NEO4J_HTTP_PORT / NEO4J_BOLT_PORT — overridden ports if needed

neo4j.conf
- A template runtime config lives at `config/neo4j/neo4j.conf`. This file contains the most common tunables:
```sbir-etl/config/neo4j/neo4j.conf#L1-40
# Example snippet from the template:
dbms.memory.heap.initial_size=${NEO4J_dbms_memory_heap_initial_size:-512m}
dbms.memory.heap.max_size=${NEO4J_dbms_memory_heap_max__size:-512m}
dbms.memory.pagecache.size=${NEO4J_dbms_memory_pagecache_size:-256M}
dbms.default_listen_address=0.0.0.0
dbms.connector.bolt.listen_address=0.0.0.0:7687
dbms.connector.http.listen_address=0.0.0.0:7474
dbms.security.auth_enabled=true
```
- You can mount a curated `neo4j.conf` into the container with the override compose file:
```sbir-etl/docker/neo4j.compose.override.yml#L18-30
# mounts:
- ./config/neo4j/neo4j.conf:/var/lib/neo4j/conf/neo4j.conf:ro
```

User and role bootstrap
- Use the provided bootstrap script to create an ingest role/user and a read-only user:
```sbir-etl/scripts/neo4j/bootstrap_users.sh#L1-30
# Example:
# Create default ingest and readonly users using environment secrets
NEO4J_PASSWORD=<admin_password> ./scripts/neo4j/bootstrap_users.sh --ingest-user sbir_ingest:ingest_pass --readonly-user sbir_ro:ro_pass
```
- The script is idempotent: it checks role/user existence and will not duplicate resources.

Schema bootstrap
- Run the schema-apply scaffold to create indexes/constraints before running loaders:
```sbir-etl/scripts/neo4j/apply_schema.py#L1-20
# Dry-run:
python scripts/neo4j/apply_schema.py --dry-run

# Apply:
NEO4J_PASSWORD=<admin_password> python scripts/neo4j/apply_schema.py
```
- The scaffold contains example statements; adapt `SCHEMA_STATEMENTS` to your production schema as needed.

Backup & restore
- Backups: `scripts/neo4j/backup.sh` creates a logical dump using `neo4j-admin dump` inside the running container (preferred) or via a local `neo4j-admin`. It also supports pruning old backups.
```sbir-etl/scripts/neo4j/backup.sh#L1-40
# Default:
./scripts/neo4j/backup.sh

# Custom:
BACKUP_DIR=backups/neo4j DB_NAME=neo4j KEEP_LAST=14 ./scripts/neo4j/backup.sh
```
- Restores: `scripts/neo4j/restore.sh` handles restoring a dump into the Neo4j data volume. It attempts a safe container-based restore and will restart containers appropriately.
```sbir-etl/scripts/neo4j/restore.sh#L1-40
# Example:
BACKUP_PATH=backups/neo4j/neo4j-20250101.dump ./scripts/neo4j/restore.sh --backup-path ${BACKUP_PATH}
```
- Caveats:
  - For large datasets, logical dumps may be slow. Consider enterprise backup solutions for production-scale needs.
  - Some `neo4j-admin` operations require the database to be offline. The restore script tries to handle this by stopping and starting containers when needed.

Makefile helpers
- Use the Makefile targets for convenience:
  - `make neo4j-up` — start the neo4j profile with the override compose
  - `make neo4j-down` — stop and remove compose resources and volumes
  - `make neo4j-reset` — remove named volumes and start with a clean state
  - `make neo4j-backup` — runs the backup script (set `BACKUP_DIR`/`KEEP_LAST` env vars as needed)
  - `make neo4j-restore` — wrapper for restore (requires `BACKUP_PATH`)
  - `make neo4j-check` — runs a quick cypher-shell health probe

Health checks & CI
- The compose override sets a healthcheck that uses `cypher-shell`:
```sbir-etl/docker/neo4j.compose.override.yml#L34-40
healthcheck:
  test: ["CMD-SHELL", "cypher-shell -u ${NEO4J_USER:-neo4j} -p ${NEO4J_PASSWORD:-password} 'RETURN 1' >/dev/null 2>&1 || exit 1"]
  interval: 10s
  timeout: 5s
  retries: 12
```
- In CI, the `docker/docker-compose.test.yml` already depends on Neo4j being healthy before running `pytest`. Ensure CI injects Neo4j credentials via secrets when running compose.

Security recommendations
- Never commit secrets into the repo. Use `.env` (gitignored) for local dev and secret injection mechanisms for CI.
- Restrict admin passwords to short-lived or rotated credentials where possible. Use `scripts/neo4j/bootstrap_users.sh` to rotate or seed accounts.
- If you enable TLS, mount certificates into `/certs` and configure `neo4j.conf` accordingly. Keep private keys in secret stores or restricted mounts.

Troubleshooting checklist
1. Container won't start:
   - Inspect container logs: `docker compose -f docker-compose.yml -f docker/neo4j.compose.override.yml --profile neo4j logs neo4j`
   - Check `neo4j` logs in mounted `neo4j_logs` volume.
2. Healthcheck failing:
   - Run `docker compose exec neo4j cypher-shell -u $NEO4J_USER -p $NEO4J_PASSWORD "RETURN 1"`
   - Ensure `NEO4J_PASSWORD` is correct and not expired/changed.
3. Dumps fail inside container:
   - Ensure sufficient disk space in the container host and the volume used for temporary dumps (`/backups`).
   - Examine `neo4j-admin` output by running the command manually inside a container for diagnostics.
4. Schema install fails:
   - Check `scripts/neo4j/apply_schema.py` logs; inspect error text to determine if the statements are already present or incompatible with the server version.
5. Slow imports or OOM:
   - Increase `dbms.memory.heap.max_size` and `dbms.memory.pagecache.size` in `config/neo4j/neo4j.conf` and restart.
   - Consider chunked loads and prefer offline import tools for large initial imports.

Operational notes & best practices
- For heavy or production workloads, prefer dedicated Neo4j service deployment (clustered or enterprise) outside local docker-compose. Use the compose paths for development/testing only.
- Keep `config/neo4j/neo4j.conf` under version control as a template (no secrets) and document environment-specific overrides.
- Automate backups on schedule (cron or CI scheduled job) and secure backup storage (S3, encrypted storage, etc.).
- Regularly test restore procedures in a staging environment to ensure backups are valid.

CI considerations
- The repo's container CI builds an app image and uses `docker/docker-compose.test.yml` to start an ephemeral Neo4j. Ensure the CI workflow injects `NEO4J_USER` and `NEO4J_PASSWORD` via secrets and that credential rotation does not break CI runs.
- If you add a `neo4j` CI smoke job, prefer to run it in an isolated runner with ephemeral resources and short timeouts.

Where to look in the repo
- Compose override: `docker/neo4j.compose.override.yml`
- Neo4j config template: `config/neo4j/neo4j.conf`
- Bootstrap / schema / backup / restore: `scripts/neo4j/*`
- Makefile neo4j wrappers: `Makefile` (search `neo4j-` targets)
- General containerization and runbook: `docs/deployment/containerization.md`

If you'd like, I can next:
- Implement automated CI job for scheduled backups (uploading to a configured S3 bucket).
- Harden `apply_schema.py` to include full production schema and version-aware compatibility checks.
- Add example TLS configuration and an integration test that validates TLS-enabled Bolt connections.
