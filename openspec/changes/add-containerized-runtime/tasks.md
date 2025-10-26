# Implementation Tasks

## 1. Container Image Architecture
code
- [ ] 1.1 Replace the root Dockerfile with a multi-stage (builder + runtime) image based on `python:3.11-slim` that installs system packages (`curl`, `build-essential`, `git`, `libpq-dev`, `tini`).
- [ ] 1.2 Run `poetry install --only main --no-root` in the builder, cache `.venv`, and copy the environment + source into the runtime layer.
- [ ] 1.3 Add a non-root `sbir` user, fix ownership of `/app`, and wire `tini` as the container entrypoint.
- [ ] 1.4 Create `.dockerignore` and prune large local directories (`data/raw`, `.venv`, `htmlcov`, etc.) from build context.
- [ ] 1.5 Add `scripts/docker/healthcheck.sh` that exercises `python -m sbir_etl --help` and returns non-zero on failure; wire it into the Dockerfile `HEALTHCHECK`.

## 2. Runtime Entrypoints & Utilities

- [x] 2.1 Create `scripts/docker/wait-for-service.sh` that blocks until `tcp://host:port` is reachable and use it before starting Dagster services.
  - Notes: Implemented `sbir-etl/scripts/docker/wait-for-service.sh` (TCP and HTTP probes, configurable timeout & interval). This script emits timestamped logs and returns non-zero on timeout. It is used by the entrypoint to gate service startup.
- [ ] 2.2 Add `scripts/docker/dagster-webserver.sh` that sources environment, waits for Neo4j, and runs `dagster-webserver -h 0.0.0.0 -p 3000` with structured logging.
- [ ] 2.3 Add `scripts/docker/dagster-daemon.sh` that waits for both Neo4j and the webserver health endpoints, then launches `dagster-daemon run` with graceful signal handling.
- [ ] 2.4 Add `scripts/docker/etl-runner.sh` to execute ad-hoc CLI commands (e.g., `python -m sbir_etl materialize ...`) within the same image.
- [ ] 2.5 Ensure every script uses `set -euo pipefail`, logs start/stop messages, and respects `SBIR_ETL_LOG_LEVEL`.

## 3. Compose Stack & Profiles

- [ ] 3.1 Redesign `docker-compose.yml` to declare services: `neo4j`, `dagster-webserver`, `dagster-daemon`, `etl-runner`, and `duckdb` (tools profile).
- [ ] 3.2 Add named volumes for Neo4j data/logs/import and for persisted metrics/log directories.
- [ ] 3.3 Introduce `docker/docker-compose.dev.yml` that bind-mounts `src/`, `config/`, `data/`, `logs/`, and `metrics/`, enables the `dev` profile, and injects `watchfiles` reloader when running `dagster dev` locally.
- [ ] 3.4 Add `docker/docker-compose.test.yml` that runs `pytest` inside the container with an ephemeral Neo4j instance for CI.
- [ ] 3.5 Configure `depends_on` with `condition: service_healthy` and add HTTP/Bolt health checks for each service.
- [ ] 3.6 Document compose targets via `Makefile` (`make docker-up`, `make docker-down`, `make docker-test`).

## 4. Configuration & Secrets Management

- [x] 4.1 Create `.env.example` describing required variables (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `SBIR_ETL__...`) and add `.env` to `.gitignore`.
  - Notes: `.env.example` has been added and documents variables and conventions. Developers should copy `.env.example` -> `.env` and populate secrets locally.
- [ ] 4.2 Add `config/docker.yaml` with container-specific defaults (service hostnames, volume paths, Dagster UI URL) and document how to select it via `ENVIRONMENT=docker`.
- [ ] 4.3 Update `config/README.md` with a “Containerized environments” section covering override order and secret injection guidelines.
- [x] 4.4 Ensure compose files and entrypoints only reference `${VARIABLE}` sourced from `.env` or exported environment (no hardcoded credentials).
  - Notes: `docker-compose.yml` has been updated to reference env vars instead of hardcoded credentials; entrypoint and wait scripts source `.env` and `/run/secrets` where appropriate.

## 5. CI, Testing, and Publish Workflow

- [ ] 5.1 Add `scripts/ci/build_container.sh` that builds the image with BuildKit cache and pushes to the local registry when `PUBLISH=1`.
- [ ] 5.2 Update `.github/workflows/ci.yml` (or create `container.yml`) to run: `docker build`, `docker compose -f docker/docker-compose.test.yml up --abort-on-container-exit`, and upload logs on failure.
- [ ] 5.3 Add a smoke test step that runs `docker run sbir-etl:ci dagster --version` to validate the entrypoint.
- [ ] 5.4 Document how to tag and push images (e.g., `ghcr.io/org/sbir-etl:<sha>`) and where credentials live.

## 6. Documentation & Developer Experience

- [x] 6.1 Create `docs/deployment/containerization.md` covering architecture diagrams, compose profiles, data volume expectations, troubleshooting, and registry workflow.
  - Notes: Initial doc added with quick-start instructions, Make targets, health check guidance, and troubleshooting checklist.
- [ ] 6.2 Update `README.md` with a concise “Container quick start” referencing the new docs and Make targets.
- [ ] 6.3 Provide onboarding notes in `CONTRIBUTING.md` explaining when to use the container vs. local Python install.
- [ ] 6.4 Include screenshots or CLI snippets showing `docker compose ps` / `dagster` UI access to ensure new contributors know how to verify their setup.

