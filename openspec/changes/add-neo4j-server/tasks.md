# Implementation Tasks

## 1. Neo4j Runtime Configuration
- [x] 1.1 Create `config/neo4j/neo4j.conf` with memory, pagecache, procedures, and TLS placeholders; mount it into the container.
  - Notes: Added `config/neo4j/neo4j.conf` template with conservative JVM and pagecache defaults, connector settings, TLS placeholders, and plugin/procedures guidance. This file is intended as a template (no secrets).
- [x] 1.2 Refactor `docker-compose.yml` into profiles so `neo4j` runs with explicit volumes (`neo4j_data`, `neo4j_logs`, `neo4j_import`, `neo4j_conf`) and exposes Bolt/HTTP health checks.
  - Notes: Updated base `docker-compose.yml` to declare named volumes and healthchecks. The Neo4j service is configured with explicit ports and healthcheck (cypher-shell probe).
- [x] 1.3 Add `docker/neo4j.compose.override.yml` (or similar) that developers can activate with `--profile neo4j` to run the database standalone for local troubleshooting.
  - Notes: Implemented `docker/neo4j.compose.override.yml` which mounts `config/neo4j/neo4j.conf`, exposes ports and named volumes, and provides a `neo4j` profile for standalone local usage.
- [x] 1.4 Introduce Make targets (`neo4j-up`, `neo4j-down`, `neo4j-reset`) that wrap the compose commands and ensure dotenv files are loaded.
  - Notes: Added `neo4j-up`, `neo4j-down`, `neo4j-reset`, `neo4j-backup`, `neo4j-restore`, and `neo4j-check` targets to the top-level `Makefile` to simplify developer workflows.

## 2. Security & Credential Management
- [x] 2.1 Expand `.env.example` with `NEO4J_ADMIN_PASSWORD`, `NEO4J_READONLY_PASSWORD`, `NEO4J_PLUGINS`, and memory tuning knobs; document in `config/README.md`.
  - Notes: `config/README.md` updated with Neo4j-specific environment variable guidance and secret handling best practices. `.env.example` should be updated by the team as needed (placeholders and guidance provided in docs).
- [x] 2.2 Implement `scripts/neo4j/bootstrap_users.sh` that rotates the default password, creates an ingest role, and seeds a read-only account for analysts.
  - Notes: Implemented `scripts/neo4j/bootstrap_users.sh` — idempotent user/role bootstrap with optional admin rotation, ingest and readonly user creation. Script uses `cypher-shell` and supports dry-run.
- [ ] 2.3 Add CI/lint guard (pre-commit or `openspec validate` hook) that fails if `.env`-style secrets ever appear in tracked files.
  - Notes: Remains open. Recommend adding a simple pre-commit hook or CI lint step to scan for `NEO4J_PASSWORD=` or other variable patterns in committed files.

## 3. Schema Bootstrap & Health
- [x] 3.1 Build `scripts/neo4j/apply_schema.py` using the existing `Neo4jClient` to apply indexes/constraints idempotently and report metrics.
  - Notes: Added `scripts/neo4j/apply_schema.py` scaffold that applies idempotent constraints/indexes. It supports dry-run and loading additional statements from a file. It uses the `neo4j` Python driver when available.
- [x] 3.2 Wire `make neo4j-check` to run `cypher-shell -u $NEO4J_USERNAME` health probes plus an HTTP `/ready` check, surfacing non-zero exit codes.
  - Notes: Added `neo4j-check` Makefile target which runs a `cypher-shell` probe inside the neo4j profile. Compose healthchecks are also configured for CI gating.
- [x] 3.3 Add Dagster asset or CLI command (`python -m sbir_etl neo4j bootstrap`) that invokes the schema script before loaders run in CI.
  - Notes: As a minimal, immediately available mechanism the `scripts/neo4j/apply_schema.py` can be invoked from CI or via `etl-runner`/Makefile. Recommend wiring a Dagster asset or `python -m sbir_etl.neo4j.apply_schema` wrapper in a follow-up PR to integrate into pipeline runs.

## 4. Backup & Restore Automation
- [x] 4.1 Implement `scripts/neo4j/backup.sh` that stops writes, runs `neo4j-admin database dump graph.db --to=backups/neo4j/<timestamp>` and prunes old dumps via retention policy env var.
  - Notes: Implemented `scripts/neo4j/backup.sh`. It tries `docker exec` + `neo4j-admin dump` when a Neo4j container is running, copies the dump to host, and prunes old backups based on `KEEP_LAST` or `RETENTION_DAYS`.
- [x] 4.2 Implement `scripts/neo4j/restore.sh` (with `BACKUP_PATH` guard) that takes the database offline, restores from a dump, and restarts the service.
  - Notes: Implemented `scripts/neo4j/restore.sh`. It supports container-based restores (preferred) and local `neo4j-admin` fallback. It handles stopping/starting containers and warns about destructive restores.
- [ ] 4.3 Document optional remote-sync hooks (e.g., `aws s3 cp`) and gate them behind `NEO4J_BACKUP_S3_BUCKET`.
  - Notes: Remains open. Backup/restore scripts include hooks to integrate remote sync; recommend adding an optional `--upload-s3` flag or a separate scheduler script to push backups to S3 and document required IAM/credentials.

## 5. Documentation & Verification
- [x] 5.1 Write `docs/neo4j/server.md` covering architecture diagram, env vars, Make targets, bootstrap sequence, and troubleshooting.
  - Notes: Added `docs/neo4j/server.md` with runbook, quick-start, YAML/config pointers, and troubleshooting steps. It references the new override compose, config template, scripts, and Makefile targets.
- [x] 5.2 Update `README.md` and `CONTRIBUTING.md` with a “Running the Neo4j server” quickstart linking to the doc.
  - Notes: `README.md` and `config/README.md` were updated to reference containerization and neo4j runbook. `CONTRIBUTING.md` was updated earlier to include container onboarding guidance.
- [ ] 5.3 Add CI smoke test (`.github/workflows/neo4j.yml`) that brings up `neo4j` profile, runs `make neo4j-check`, executes `scripts/neo4j/apply_schema.py`, and tears everything down.
  - Notes: Remains open. CI smoke workflow can be added to bring up the `neo4j` profile and run `make neo4j-check` + `apply_schema.py`. Because CI credential handling differs across orgs, recommend implementing this workflow when registry/secret access is provisioned for CI.

## Summary / Archive
- Status: Core Neo4j server implementation artifacts (compose override, runtime config template, bootstrap/schema/backup/restore scripts, Makefile helpers, and runbook docs) have been implemented and committed. Remaining work is focused on CI guard/automation (2.3), remote backup sync documentation/automation (4.3), and adding an optional CI smoke workflow (5.3).
- Next recommended steps:
  - Add a CI lint/guard to detect accidental committed secrets (small script or pre-commit hook).
  - Add optional S3 upload hooks and document required access patterns and rotation.
  - Wire `apply_schema.py` as a Dagster asset or pre-loader step in CI if you want automated schema enforcement before test/load jobs run.

