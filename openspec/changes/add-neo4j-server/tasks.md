# Implementation Tasks

## 1. Neo4j Runtime Configuration
- [ ] 1.1 Create `config/neo4j/neo4j.conf` with memory, pagecache, procedures, and TLS placeholders; mount it into the container.
- [ ] 1.2 Refactor `docker-compose.yml` into profiles so `neo4j` runs with explicit volumes (`neo4j_data`, `neo4j_logs`, `neo4j_import`, `neo4j_conf`) and exposes Bolt/HTTP health checks.
- [ ] 1.3 Add `docker/neo4j.compose.override.yml` (or similar) that developers can activate with `--profile neo4j` to run the database standalone for local troubleshooting.
- [ ] 1.4 Introduce Make targets (`neo4j-up`, `neo4j-down`, `neo4j-reset`) that wrap the compose commands and ensure dotenv files are loaded.

## 2. Security & Credential Management
- [ ] 2.1 Expand `.env.example` with `NEO4J_ADMIN_PASSWORD`, `NEO4J_READONLY_PASSWORD`, `NEO4J_PLUGINS`, and memory tuning knobs; document in `config/README.md`.
- [ ] 2.2 Implement `scripts/neo4j/bootstrap_users.sh` that rotates the default password, creates an ingest role, and seeds a read-only account for analysts.
- [ ] 2.3 Add CI/lint guard (pre-commit or `openspec validate` hook) that fails if `.env`-style secrets ever appear in tracked files.

## 3. Schema Bootstrap & Health
- [ ] 3.1 Build `scripts/neo4j/apply_schema.py` using the existing `Neo4jClient` to apply indexes/constraints idempotently and report metrics.
- [ ] 3.2 Wire `make neo4j-check` to run `cypher-shell -u $NEO4J_USERNAME` health probes plus an HTTP `/ready` check, surfacing non-zero exit codes.
- [ ] 3.3 Add Dagster asset or CLI command (`python -m sbir_etl neo4j bootstrap`) that invokes the schema script before loaders run in CI.

## 4. Backup & Restore Automation
- [ ] 4.1 Implement `scripts/neo4j/backup.sh` that stops writes, runs `neo4j-admin database dump graph.db --to=backups/neo4j/<timestamp>` and prunes old dumps via retention policy env var.
- [ ] 4.2 Implement `scripts/neo4j/restore.sh` (with `BACKUP_PATH` guard) that takes the database offline, restores from a dump, and restarts the service.
- [ ] 4.3 Document optional remote-sync hooks (e.g., `aws s3 cp`) and gate them behind `NEO4J_BACKUP_S3_BUCKET`.

## 5. Documentation & Verification
- [ ] 5.1 Write `docs/neo4j/server.md` covering architecture diagram, env vars, Make targets, bootstrap sequence, and troubleshooting.
- [ ] 5.2 Update `README.md` and `CONTRIBUTING.md` with a “Running the Neo4j server” quickstart linking to the doc.
- [ ] 5.3 Add CI smoke test (`.github/workflows/neo4j.yml`) that brings up `neo4j` profile, runs `make neo4j-check`, executes `scripts/neo4j/apply_schema.py`, and tears everything down.
