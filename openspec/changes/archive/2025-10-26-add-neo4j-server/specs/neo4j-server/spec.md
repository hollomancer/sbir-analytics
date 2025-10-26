# neo4j-server - Implementation Delta

## ADDED Requirements

### Requirement: Configurable Neo4j Deployment Profiles
The project SHALL provide reproducible Neo4j deployments for development, CI, and production-like environments using Compose profiles and shared configuration.

#### Scenario: Profile-specific compose stack
- **WHEN** `docker compose --profile neo4j up` runs
- **THEN** the stack SHALL start the Neo4j container with named volumes for `data`, `logs`, `import`, and `conf`
- **AND** mount `config/neo4j/neo4j.conf` read-only
- **AND** expose Bolt (7687) and HTTP (7474) ports with health checks defined in Compose

#### Scenario: Memory & plugin tuning via environment
- **WHEN** engineers set values such as `NEO4J_server_memory_heap_max__size` or `NEO4J_PLUGINS` in `.env`
- **THEN** the compose profile SHALL pass them to the container
- **AND** the resulting configuration SHALL be reflected in `neo4j.conf` so that dev/CI/prod runs behave consistently

### Requirement: Secure Credential & Role Management
The system SHALL enforce non-default credentials and create least-privilege roles for ingestion vs. read-only access.

#### Scenario: Password rotation on bootstrap
- **WHEN** `make neo4j-bootstrap-users` runs
- **THEN** the script SHALL connect using the initial admin secret
- **AND** set the admin password to `NEO4J_ADMIN_PASSWORD`
- **AND** create dedicated `sbir_ingest` and `sbir_readonly` users with the configured passwords

#### Scenario: Environment-only secret storage
- **WHEN** `.env.example` documents required variables
- **THEN** real `.env` files SHALL remain gitignored
- **AND** no plaintext passwords SHALL exist in repository-tracked files per CI enforcement

### Requirement: Automated Schema Bootstrap
Neo4j SHALL expose a repeatable bootstrap command that prepares constraints, indexes, and seed nodes before loaders run.

#### Scenario: Idempotent schema script
- **WHEN** `scripts/neo4j/apply_schema.py` executes
- **THEN** it SHALL use the project’s Neo4j client to apply unique constraints, indexes, and seed relationship types
- **AND** the script SHALL be idempotent (re-running produces no errors and leaves schema unchanged)
- **AND** failures SHALL exit non-zero with actionable logs

### Requirement: Health Checks & Observability
The Neo4j server SHALL publish health endpoints and metrics so orchestration tools can detect readiness and diagnose issues.

#### Scenario: Bolt + HTTP health verification
- **WHEN** `make neo4j-check` runs
- **THEN** it SHALL invoke `cypher-shell "RETURN 1"` and `curl http://localhost:7474/` (or `/ready`)
- **AND** exit non-zero if either probe fails within the configured timeout
- **AND** emit structured logs to `logs/neo4j/health.log`

#### Scenario: Metrics surfaced to Dagster
- **WHEN** the ETL finishes a load
- **THEN** Dagster SHALL record Neo4j node/relationship counts and heap usage in asset metadata sourced from the health probe output

### Requirement: Backup & Restore Automation
The project SHALL provide scripts to create, retain, and restore Neo4j backups without manual container fiddling.

#### Scenario: Timestamped backups with retention
- **WHEN** `make neo4j-backup` runs
- **THEN** `scripts/neo4j/backup.sh` SHALL call `neo4j-admin database dump` into `backups/neo4j/<timestamp>.dump`
- **AND** prune backups older than the configured retention (e.g., `NEO4J_BACKUP_RETENTION_DAYS`)

#### Scenario: Guarded restore workflow
- **WHEN** `make neo4j-restore BACKUP=backups/neo4j/2024-05-01.dump` runs
- **THEN** the script SHALL stop the Neo4j container, verify the dump exists, restore it via `neo4j-admin load`, and restart the service
- **AND** prompt for confirmation unless `FORCE=1` is set to prevent accidental data loss
