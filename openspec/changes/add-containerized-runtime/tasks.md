# Implementation Tasks

## 1. Container Image Architecture
code
- [x] 1.1 Replace the root Dockerfile with a multi-stage (builder + runtime) image based on `python:3.11-slim` that installs system packages (`curl`, `build-essential`, `git`, `libpq-dev`, `tini`).
  - Notes: Implemented multi-stage `Dockerfile` that builds wheels in a builder stage (Poetry export -> wheel build) and installs wheels offline into the runtime stage. Runtime includes `tini`, `gosu`, and a non-root `sbir` user. See `Dockerfile` (root).
- [x] 1.2 Run `poetry install --only main --no-root` in the builder, cache `.venv`, and copy the environment + source into the runtime layer.
  - Notes: Builder stage uses `poetry export` to produce `requirements.txt` and builds wheels into `/wheels`. Wheels are copied into the runtime image and installed via `pip --no-index --find-links=/wheels`.
- [x] 1.3 Add a non-root `sbir` user, fix ownership of `/app`, and wire `tini` as the container entrypoint.
  - Notes: Runtime stage creates `sbir` user, chowns `/app`, installs `tini` as PID 1, and sets entrypoint to `/app/sbir-etl/scripts/docker/entrypoint.sh`.
- [x] 1.4 Create `.dockerignore` and prune large local directories (`data/raw`, `.venv`, `htmlcov`, etc.) from build context.
  - Notes: `.dockerignore` created/updated to exclude `data/`, `.venv/`, `htmlcov/`, `tests/fixtures` (as appropriate), and other large or local-only paths.
- [x] 1.5 Add `scripts/docker/healthcheck.sh` that exercises `python -m sbir_etl --help` and returns non-zero on failure; wire it into the Dockerfile `HEALTHCHECK`.
  - Notes: `sbir-etl/scripts/docker/healthcheck.sh` implements `app|web|neo4j` modes and is referenced by Dockerfile `HEALTHCHECK`.

## 2. Runtime Entrypoints & Utilities

- [x] 2.1 Create `scripts/docker/wait-for-service.sh` that blocks until `tcp://host:port` is reachable and use it before starting Dagster services.
  - Notes: Implemented `sbir-etl/scripts/docker/wait-for-service.sh` with TCP and HTTP probes, timeout and interval options, and verbose timestamped logging.
- [x] 2.2 Add `scripts/docker/dagster-webserver.sh` that sources environment, waits for Neo4j, and runs `dagster-webserver -h 0.0.0.0 -p 3000` with structured logging.
  - Notes: Implemented `sbir-etl/scripts/docker/dagster-webserver.sh`. It supports `start` and `healthcheck` modes, waits for dependencies, and drops privileges where possible.
- [x] 2.3 Add `scripts/docker/dagster-daemon.sh` that waits for both Neo4j and the webserver health endpoints, then launches `dagster-daemon run` with graceful signal handling.
  - Notes: Implemented `sbir-etl/scripts/docker/dagster-daemon.sh` with `start`, `etl-runner` and `healthcheck` modes and dependency gating.
- [x] 2.4 Add `scripts/docker/etl-runner.sh` to execute ad-hoc CLI commands (e.g., `python -m sbir_etl materialize ...`) within the same image.
  - Notes: Implemented `sbir-etl/scripts/docker/etl-runner.sh`. It waits for Neo4j (and optionally Dagster web) then executes the provided command, preferring to run as `sbir` when possible.
- [x] 2.5 Ensure every script uses `set -euo pipefail`, logs start/stop messages, and respects `SBIR_ETL_LOG_LEVEL`.
  - Notes: All new scripts follow POSIX-sh conventions, use `set -eu`, provide timestamped logs, and read `.env` or `/run/secrets`. They are written to be compatible with the runtime image; `SBIR_ETL_LOG_LEVEL` is observed by entrypoint wrappers (environment-driven).

## 3. Compose Stack & Profiles

- [x] 3.1 Redesign `docker-compose.yml` to declare services: `neo4j`, `dagster-webserver`, `dagster-daemon`, `etl-runner`, and `duckdb` (tools profile).
  - Notes: Implemented base `docker-compose.yml` that defines core services and a pattern for overlays. The base compose centralizes service definitions and exposes ports/envs used by dev and test overlays.
- [x] 3.2 Add named volumes for Neo4j data/logs/import and for persisted metrics/log directories.
  - Notes: Added named volumes (`neo4j_data`, `neo4j_logs`, `neo4j_import`, `reports`, `logs`, `data`, `config`, `metrics`) in the base compose to provide persistent storage; dev overlays may override these with bind mounts for local iteration.
- [x] 3.3 Introduce `docker/docker-compose.dev.yml` that bind-mounts `src/`, `config/`, `data/`, `logs/`, and `metrics/`, enables the `dev` profile, and injects `watchfiles` reloader when running `dagster dev` locally.
  - Notes: Implemented `docker/docker-compose.dev.yml` which provides developer-friendly bind-mounts for `src`, `config`, `data`, `logs`, and `reports`. The compose file supports a `dev` profile and the runtime entrypoint honors an `ENABLE_WATCHFILES` environment flag to enable hot-reload behavior for local development.
- [x] 3.4 Add `docker/docker-compose.test.yml` that runs `pytest` inside the container with an ephemeral Neo4j instance for CI.
  - Notes: Implemented `docker/docker-compose.test.yml` which defines an ephemeral Neo4j service and an `app` test service that runs `pytest` using the built image. The compose file is intended for CI usage and references the `sbir-etl:ci-${GITHUB_SHA}` image produced by the CI build script. Verified basic behavior via the Makefile `docker-test` target.
- [ ] 3.5 Configure `depends_on` with `condition: service_healthy` and add HTTP/Bolt health checks for each service.
- [x] 3.6 Document compose targets via `Makefile` (`make docker-up`, `make docker-down`, `make docker-test`).
  - Notes: Added Makefile targets to support building, bringing up the dev stack, running containerized tests, tearing down stacks, and tailing logs. See top-level `Makefile` for `docker-build`, `docker-up-dev`, `docker-test`, `docker-down`, and helper targets.

## 4. Configuration & Secrets Management

- [x] 4.1 Create `.env.example` describing required variables (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `SBIR_ETL__...`) and add `.env` to `.gitignore`.
  - Notes: `.env.example` added; developers should copy to `.env` and supply safe values. `.env` is in `.gitignore`.
- [ ] 4.2 Add `config/docker.yaml` with container-specific defaults (service hostnames, volume paths, Dagster UI URL) and document how to select it via `ENVIRONMENT=docker`.
- [ ] 4.3 Update `config/README.md` with a “Containerized environments” section covering override order and secret injection guidelines.
- [x] 4.4 Ensure compose files and entrypoints only reference `${VARIABLE}` sourced from `.env` or exported environment (no hardcoded credentials).
  - Notes: `docker-compose.yml` updated to use environment variables (no hardcoded passwords). Entrypoints read `.env` and `/run/secrets`.

## 5. CI, Testing, and Publish Workflow

- [x] 5.1 Add `scripts/ci/build_container.sh` that builds the image with BuildKit cache and pushes to the local registry when `PUBLISH=1`.
  - Notes: Implemented `scripts/ci/build_container.sh`. The script builds with Docker Buildx, supports cache-from/cache-to flags, allows single-platform `--load` for local testing, and can `--push` to a registry when `PUBLISH=1`. It is intended for use in CI to produce `sbir-etl:<tag>` artifacts.
- [x] 5.2 Update `.github/workflows/ci.yml` (or create `container.yml`) to run: `docker build`, `docker compose -f docker/docker-compose.test.yml up --abort-on-container-exit`, and upload logs on failure.
  - Notes: Implemented `.github/workflows/container-ci.yml`. The workflow builds the image (loads it into the runner), brings up an ephemeral Neo4j and the `app` test service via `docker compose -f docker-compose.yml -f docker/docker-compose.test.yml up --abort-on-container-exit --build`, tears down the stack on completion, and uploads logs/artifacts on failure. The job uses Buildx and supports caching.
- [x] 5.3 Add a smoke test step that runs `docker run sbir-etl:ci dagster --version` to validate the entrypoint.
  - Notes: Implemented smoke test in `.github/workflows/container-ci.yml` that runs `docker run ${IMAGE_NAME}:ci-${{ github.sha }} dagster --version` immediately after building the image and before running the compose-based tests.
- [ ] 5.4 Document how to tag and push images (e.g., `ghcr.io/org/sbir-etl:<sha>`) and where credentials live.

## 6. Documentation & Developer Experience

- [x] 6.1 Create `docs/deployment/containerization.md` covering architecture diagrams, compose profiles, data volume expectations, troubleshooting, and registry workflow.
  - Notes: Documentation added with quick-start, troubleshooting checklist, and recommended workflows for dev/test/prod.
- [ ] 6.2 Update `README.md` with a concise “Container quick start” referencing the new docs and Make targets.
- [ ] 6.3 Provide onboarding notes in `CONTRIBUTING.md` explaining when to use the container vs. local Python install.
- [ ] 6.4 Include screenshots or CLI snippets showing `docker compose ps` / `dagster` UI access to ensure new contributors know how to verify their setup.


