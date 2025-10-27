# Containerization: SBIR ETL

This document explains how to run, build, and test the SBIR ETL project inside containers.
It includes a quick-start for local development, CI guidance, and references to the repository's
README and Makefile for convenient shortcuts.

Table of contents
- Overview
- Quick prerequisites
- Quick-start (recommended)
  - Local: build & dev
  - Local: run an ad-hoc ETL command
  - Local: run containerized tests
- Files you should know
- Build and publish (CI-friendly)
- Compose overlays and profiles
- Entrypoints & service startup behavior
- Health checks & volumes
- Troubleshooting checklist
- Links / README references

Overview
--------
We provide a multi-stage Dockerfile and a set of Compose overlays to support three primary workflows:

- Local development (fast iteration with bind mounts and auto-reload).
- Containerized testing (ephemeral Neo4j + running `pytest` inside the built image).
- Production-like runs (named volumes, deterministic images).

The goal is to make the runtime reproducible across laptops, CI, and staging while keeping developer
iteration fast and safe.

Quick prerequisites
-------------------
- Docker with the `docker compose` plugin (Docker Desktop or Docker Engine with Compose V2).
- GNU `make` for convenience (or use the `docker compose` commands directly).
- Optional but helpful: `jq`, `yq` (for reading config), `py-spy` for profiling Python processes.

Quick-start (recommended)
-------------------------
The repo contains helpful Makefile targets. The quick path below assumes you have copied `.env.example`
to `.env` and set at minimum Neo4j credentials for local testing.

1) Prepare environment (one-time)
```/dev/null/example.commands#L1-6
cp .env.example .env
# Edit .env and set NEO4J_USER / NEO4J_PASSWORD (local dev credentials only)
```

2) Build the image locally (multi-stage Dockerfile)
```/dev/null/example.commands#L7-12
# Build the runtime image locally (used by dev compose or direct docker run)
make docker-build
# Or (explicit):
docker build -t sbir-etl:local -f Dockerfile .
```

3) Start the development stack (recommended for iterative work)
```/dev/null/example.commands#L13-22
# Start dev compose (dev overlay bind-mounts src/config for live edit)
make docker-up-dev

# OR
docker compose --env-file .env --profile dev -f docker-compose.yml -f docker/docker-compose.dev.yml up --build
```

- The `dev` profile mounts local `src/`, `config/`, `data/`, `logs/`, and `reports/` folders into containers.
- The runtime entrypoint honors `ENABLE_WATCHFILES=1` (if present) to enable auto-reload for `dagster dev`.

4) Run an ad-hoc ETL command inside the image (etl-runner)
```/dev/null/example.commands#L23-30
# Run an ad-hoc command using the etl-runner service:
docker compose -f docker-compose.yml -f docker/docker-compose.dev.yml run --rm etl-runner -- python -m src.scripts.run_some_job --arg value

# Or use the Makefile helper if you prefer:
make docker-exec SERVICE=dagster-webserver CMD="python -m src.scripts.run_some_job --arg value"
```

5) Run containerized tests (CI-like local run)
```/dev/null/example.commands#L31-38
# Run ephemeral Neo4j + test service (the app image runs pytest)
make docker-test

# Or:
docker compose --env-file .env -f docker-compose.yml -f docker/docker-compose.test.yml up --abort-on-container-exit --build
```

Files you should know
---------------------
- `Dockerfile` — multi-stage image (builder + runtime). The runtime target is used by Compose services.
- `docker-compose.yml` — base compose file declaring core services and named volumes.
- `docker/docker-compose.dev.yml` — dev overlay: bind mounts, dev profile, watch/reload knobs.
- `docker/docker-compose.test.yml` — test overlay: ephemeral Neo4j + `app` service that runs `pytest`.
- `Makefile` — convenience commands: `docker-build`, `docker-up-dev`, `docker-test`, `docker-down`, `docker-logs`.
- `scripts/ci/build_container.sh` — CI-friendly build script (Buildx-supporting).
- `scripts/docker/entrypoint.sh` — container entrypoint used by runtime images.
- `scripts/docker/wait-for-service.sh` — robust wait-for utility used by entrypoint scripts.
- `config/docker.yaml` — container default settings and hints (do not put secrets here).
- `.env.example` — template for local environment variables; copy to `.env` for development.

Build and publish (CI-friendly)
-------------------------------
CI should:
1. Build the multi-stage image (using Buildx for caching when available).
2. Run containerized tests by bringing up `docker/docker-compose.test.yml`.
3. Optionally push the image to a registry if tests pass.

Example GH Actions / CI steps (high-level):
```/dev/null/example.ci#L1-14
# Checkout repo
# Prepare .env from .env.example (inject secrets from CI)
# Build image with Buildx or load locally:
scripts/ci/build_container.sh  # supports cache-from/cache-to and --push when PUBLISH=1
# Run compose test overlay:
docker compose -f docker-compose.yml -f docker/docker-compose.test.yml up --abort-on-container-exit --build
# Collect logs/artifacts on failure and teardown
```

Compose overlays and profiles
----------------------------
- The base `docker-compose.yml` defines services and named volumes that are suitable for production-like runs.
- `docker/docker-compose.dev.yml` overlays bind mounts for local dev and enables a `dev` profile. It intentionally mounts `src` and `config` so code edits are visible without rebuilding the image.
- `docker/docker-compose.test.yml` overlays an ephemeral Neo4j service and an `app` service that executes `pytest` inside the built image. It's used by CI to validate the built artifact.

Entrypoints & service startup behavior
-------------------------------------
All services in the runtime image share a common entrypoint script which:

- Loads environment variables from `/app/.env` (if present), `/app/config/.env`, and `/run/secrets/*` (if secret files are mounted).
- Uses `wait-for-service.sh` to wait for required dependencies (Neo4j Bolt port, Dagster web API) before starting.
- Drops privileges to a non-root `sbir` user when possible (using `gosu` or similar).
- Executes the service-specific command (e.g., `dagster dev`, `dagster-daemon run`, or ad-hoc CLI commands).

Important: the entrypoint returns non-zero when dependencies do not become healthy within the configured timeout so CI and orchestrators can detect failures quickly.

Health checks & volumes
-----------------------
Health checks:
- Neo4j: `cypher-shell` check using credentials (configured in `.env`) and repeated with retries to allow DB warm-up.
- Dagster webserver: HTTP probe for `/server_info` expecting an HTTP 2xx response.

Volumes:
- Named volumes are defined in the base compose: `neo4j_data`, `neo4j_logs`, `neo4j_import`, `reports`, `logs`, `data`, `config`, `metrics`.
- Dev overlay replaces the named volumes with host bind mounts for `src`, `config`, `data`, `logs` to make development easier.
- On macOS, heavy bind mounts for very large data may be slow; prefer a named volume for large datasets.

Troubleshooting checklist
-------------------------
If a service fails to start or tests are flaky:

1. Check container logs:
```/dev/null/example.commands#L39-46
# Tail logs for a service (example service: dagster-webserver)
make docker-logs SERVICE=dagster-webserver
# or
docker compose -f docker-compose.yml -f docker/docker-compose.dev.yml logs -f dagster-webserver
```

2. Check health & progress files:
- The profiler scripts and entrypoints write progress/diagnostic messages to `reports/` and `logs/`. Inspect `reports/progress/` for in-progress profiling state when streaming large dumps.

3. Ensure `.env` is present and contains expected credentials:
```/dev/null/example.commands#L47-52
cp .env.example .env
# Edit .env and set NEO4J_PASSWORD and other secrets for local dev
```

4. If Neo4j fails to respond:
- Inspect the Neo4j container logs and the `neo4j_logs` volume for JVM errors or plugin problems.
- Ensure the `NEO4J_AUTH` environment is set correctly (or `NEO4J_USER`/`NEO4J_PASSWORD` are provided).

5. If tests inside the container fail:
- Run the test compose locally (`make docker-test`) and inspect the `app` container logs produced during the test run.
- Ensure the `app` image used by the test overlay contains the repository code/artifacts (CI build must produce the image with the source studied by tests).

6. Profiling / performance:
- Use `py-spy` against the running Python PID to collect a flamegraph if CPU is tied up (install locally).
- Use `tracemalloc` or the repository's `performance_monitor` utilities to export metrics to `reports/performance_metrics.json`.

Links / README references
------------------------
- Top-level README: reference instructions for local dev and for working with code.
- Makefile: use `make docker-build`, `make docker-up-dev`, `make docker-test`, `make docker-down`.
- Config reference: `config/docker.yaml` (defaults & notes).
- Entrypoint & scripts: `sbir-etl/scripts/docker/entrypoint.sh` and `sbir-etl/scripts/docker/wait-for-service.sh`.
- CI helpers: `scripts/ci/build_container.sh` and `.github/workflows/container-ci.yml`.

Recommended next steps for teams
-------------------------------
- Keep `.env.example` up-to-date with any new required environment variables and document their purpose.
- Use the `docker/docker-compose.test.yml` overlay in CI so the same image that passes tests is what is promoted for publishing.
- Run containerized tests regularly in CI and upload container logs/artifacts if failures occur to aid debugging.
- Consider adding a scheduled performance job (nightly) that runs slow benchmarks in an isolated environment rather than blocking the main CI pipeline.

If you want, I can:
- Add sample debug commands to this doc that target a specific failing service.
- Produce a short runbook that automates log collection and packaging for sharing with teammates.
- Add a small checklist for onboarding new contributors to use the container workflow.

End of document.
