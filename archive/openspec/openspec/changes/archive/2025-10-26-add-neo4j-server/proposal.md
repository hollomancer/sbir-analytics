# Implement Dedicated Neo4j Server

## Why

The repository currently treats Neo4j as an incidental dependency instead of a first-class service, which makes the ETL pipeline fragile and hard to operate:

- `docker-compose.yml:2` defines a single Neo4j container with hardcoded defaults, no dedicated `neo4j.conf`, and no volume hygiene, so every teammate guesses at memory limits, plugin enablement, and import paths.
- There are no scripts or Make targets for lifecycle management (start, stop, health check, password rotation), forcing engineers to poke at `docker compose` manually and making CI automation impossible.
- We lack any automated schema bootstrap, health verification, or backups—if the container restarts or a constraint needs to be re-applied, the process is manual and undocumented, putting the only graph datastore at risk.

To unblock downstream work (e.g., relationship loaders, CET graph analytics, and MCP integrations) we need a spec-backed change that defines how the Neo4j server is built, configured, secured, and operated across environments.

## What Changes

- **Server packaging & configuration**: create a dedicated `neo4j-server` compose profile with named volumes, mountable `config/neo4j/neo4j.conf`, explicit plugin/extension toggles, and memory tuning surfaced via `.env`.
- **Lifecycle automation**: add `scripts/neo4j/*.sh` (start, stop, wait, health, seed) plus Make targets (`neo4j-up`, `neo4j-reset`, `neo4j-check`) so CI and developers can manage the database consistently.
- **Security & roles**: wire environment-driven credential rotation (`NEO4J_ADMIN_PASSWORD`, `NEO4J_READONLY_PASSWORD`), enforce non-default users, and introduce bootstrap logic that creates read-only + ingestion roles with least-privilege constraints.
- **Schema bootstrap & migrations**: ship a repeatable `scripts/neo4j/apply_schema.py` that runs `neo4j-admin`/Bolt commands to create constraints, indexes, and seed reference nodes before loaders push data.
- **Backups & observability**: provide `scripts/neo4j/backup.sh`/`restore.sh`, timestamped dumps under `backups/neo4j/`, health probes (`cypher-shell RETURN 1` + HTTP `/ready`), and metrics surfaced through Dagster asset metadata.
- **Documentation**: add `docs/neo4j/server.md` describing the architecture, env vars, TLS guidance, and troubleshooting so onboarding engineers can operate the graph safely.

## Impact

### Affected Specs
- **neo4j-server** *(new)*: captures requirements for provisioning, securing, monitoring, and backing up the project’s Neo4j instance.

### Affected Code
- `docker-compose.yml` plus new `docker/neo4j.compose.override.yml` (profiles, health checks, volume mounts).
- `config/neo4j/neo4j.conf`, `.env.example`, and `config/README.md` to describe server settings.
- `scripts/neo4j/` helpers (`wait-for.sh`, `apply_schema.py`, `backup.sh`, `restore.sh`, `healthcheck.sh`).
- `Makefile` targets for start/stop/check/backup plus CI glue (`.github/workflows/neo4j.yml`).
- `docs/neo4j/server.md` for operational runbooks.

### Dependencies
- Neo4j CLI utilities (`neo4j-admin`, `cypher-shell`) shipped inside the container image.
- Optional: `awscli`/`rclone` if we decide to sync backups to object storage (documented but gated behind env flags).

### Risks / Mitigations
- **Data loss during migration**: backup-before-restore scripts plus dry-run flags mitigate accidental wipes.
- **Credential leakage**: move secrets to `.env`/runtime env vars, never commit values, add documentation reminders.
- **Operational drift**: codify every server action behind scripts/Make targets and enforce via CI smoke tests.

### Out of Scope
- Managed Neo4j Aura or Kubernetes deployments (this change focuses on local + self-hosted Compose environments).
- High-availability clustering; we target a single-instance server with backups.
