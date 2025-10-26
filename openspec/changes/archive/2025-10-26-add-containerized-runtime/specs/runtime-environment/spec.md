# runtime-environment - Containerized Runtime Delta

## ADDED Requirements

### Requirement: Multi-Stage SBIR ETL Image Build
The project SHALL provide a deterministic multi-stage Docker build that separates dependency resolution from the runtime image and enforces non-root execution.

#### Scenario: Build deterministic runtime layer
- **WHEN** `docker build -t sbir-etl:latest .` runs
- **THEN** the builder stage installs Poetry + project dependencies with `poetry install --only main --no-root`
- **AND** the runtime stage copies only the installed site-packages, application code, and entrypoint scripts into `/app`
- **AND** the final image includes `tini` as PID 1 and sets the default user to `sbir` (non-root)

#### Scenario: Cache-friendly dependency install
- **WHEN** only `src/` files change
- **THEN** Docker leverages cached layers up to the Poetry install step
- **AND** rebuild time remains under 30 seconds on a warm cache

### Requirement: Dagster Service Containers
The system SHALL run Dagster components (webserver, daemon, ad-hoc runner) as separate containers that share the same image but have service-specific entrypoints.

#### Scenario: Dedicated webserver container
- **WHEN** `docker compose up dagster-webserver` executes
- **THEN** the container runs `scripts/docker/dagster-webserver.sh`
- **AND** exposes the UI on port 3000 bound to `0.0.0.0`
- **AND** reads configuration from `/app/config/docker.yaml`

#### Scenario: Scheduler waits for dependencies
- **WHEN** `docker compose up dagster-daemon` executes
- **THEN** the entrypoint waits for the Neo4j Bolt port and the webserver health endpoint to be healthy
- **AND** only then starts `dagster-daemon run`
- **AND** exits non-zero if dependencies never become healthy within the configured timeout

#### Scenario: Ad-hoc runner for CLI work
- **WHEN** an engineer runs `docker compose run --rm etl-runner python -m sbir_etl materialize raw_sbir_awards`
- **THEN** the runner shares the same image layers as the services
- **AND** streams logs to stdout so the command can be scripted in CI

### Requirement: Compose Profiles for Dev, Test, and Prod
The Compose configuration SHALL define profiles that tailor mounts, commands, and optional services to local development, CI testing, and production-like deployments.

#### Scenario: Development profile with bind mounts
- **WHEN** `docker compose --profile dev up` runs
- **THEN** source code, config, logs, metrics, and data directories are bind-mounted from the host
- **AND** file changes trigger Dagster code reloads via `watchfiles`
- **AND** developers can inspect artifacts directly from the host filesystem

#### Scenario: Test profile for CI
- **WHEN** `docker compose -f docker/docker-compose.test.yml up --abort-on-container-exit` runs in CI
- **THEN** it provisions ephemeral Neo4j + Dagster containers, executes `pytest`, and tears everything down when tests finish
- **AND** the job fails if any container exits non-zero

#### Scenario: Production profile without bind mounts
- **WHEN** the base compose file runs without the `dev` overlay
- **THEN** containers rely solely on baked image contents and named volumes (no host mounts)
- **AND** secrets come from `.env` or the deployment environment

### Requirement: Environment & Secret Management
Containerized runs SHALL externalize all credentials and runtime configuration via environment variables and `.env` files without hardcoding secrets in Compose files or images.

#### Scenario: `.env` contract for Compose
- **WHEN** a developer copies `.env.example` to `.env`
- **THEN** variables like `NEO4J_PASSWORD`, `NEO4J_URI`, and `SBIR_ETL__NEO4J__BOLT_URL` are defined in one place
- **AND** `docker compose` automatically injects them into services via `${VARIABLE}` placeholders
- **AND** `.env` remains gitignored

#### Scenario: Container configuration override
- **WHEN** the container starts with `ENVIRONMENT=docker`
- **THEN** the application loads `config/docker.yaml`
- **AND** environment variables with the `SBIR_ETL__` prefix override any YAML value per the configuration spec

### Requirement: Health Checks & Dependency Gating
Each container SHALL declare health checks and wait conditions so that interdependent services only start after prerequisites are healthy.

#### Scenario: Neo4j readiness gating
- **WHEN** `neo4j` service starts
- **THEN** it exposes TCP health on ports 7474/7687
- **AND** `docker compose` marks it healthy only after `cypher-shell` succeeds
- **AND** Dagster services declare `depends_on` with `condition: service_healthy`

#### Scenario: Dagster health endpoint
- **WHEN** `dagster-webserver` is healthy
- **THEN** `GET /server_info` returns HTTP 200
- **AND** the health check script polls this endpoint every 10 seconds with 3 retries before marking the service unhealthy

### Requirement: Data Persistence & Volume Layout
The container stack SHALL mount consistent volumes for data inputs/outputs, logs, metrics, and Neo4j state so that restarts do not lose work products.

#### Scenario: Named volumes for Neo4j state
- **WHEN** `docker compose up neo4j` runs
- **THEN** volumes `neo4j_data`, `neo4j_logs`, and `neo4j_import` are attached
- **AND** subsequent restarts reuse the same volumes to keep the graph database intact

#### Scenario: Shared host directories for artifacts
- **WHEN** running in the `dev` profile
- **THEN** host directories `./data`, `./logs`, `./metrics`, and `./config` are mounted into `/app/...`
- **AND** artifacts generated inside containers are immediately available on the host for debugging or commits
