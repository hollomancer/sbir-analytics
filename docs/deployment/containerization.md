sbir-etl/docs/deployment/containerization.md
# Containerization: SBIR ETL

This document describes the containerized runtime for the SBIR ETL project:
how images are built, how to run the project in development and CI, environment
and secrets handling, and operational guidance for health checks, volumes, and
troubleshooting.

Table of contents
- Overview
- Key artifacts
- Prerequisites
- Environment files and secrets
- Build the image
- Dev: local compose (bind mounts)
- Test: ephemeral compose for CI
- Prod: production-like compose
- Entrypoints and wait-for semantics
- Health checks and readiness
- Volumes & persistency
- CI integration and testing
- Best practices & tips (macOS, caching)
- Troubleshooting checklist

Overview
--------
We use Docker + Compose to provide a reproducible runtime for local development,
CI, and production-like testing. The repository contains:
- A multi-stage Dockerfile that separates dependency installation (builder)
  from the runtime image.
- Service-specific entrypoint scripts (webserver, daemon, ad-hoc runner).
- Compose-based profiles for `dev`, `test`, and production-like runs.
- A `.env.example` documenting environment variables and an expectation that
  each developer will create their own `.env` locally (and keep it out of git).
- Make targets to simplify local workflows (build, up, test).

Key artifacts
-------------
Paths referenced in this document (examples):
- Docker Compose base: `docker-compose.yml`
- Dev overlay: `docker/docker-compose.dev.yml` (dev-only profile)
- Test overlay: `docker/docker-compose.test.yml` (CI)
- Entrypoint scripts: `sbir-etl/scripts/docker/entrypoint.sh`
- Wait-for helper: `sbir-etl/scripts/docker/wait-for-service.sh`
- Makefile: `Makefile`
- Env template: `.env.example`

Quick prerequisites
-------------------
- Docker CLI (with `docker compose` plugin) installed locally
- For macOS: recommend Docker Desktop 4.x or later
- Recommended: `make` to use Makefile helpers
- Optional (for faster local dev): `watchfiles` in dev image used only in the
  dev profile for automatic reloads

Environment & secrets
---------------------
Do NOT commit real secrets. The repo contains `.env.example` which documents the
variables Compose expects. Copy it and fill in values:

```/dev/null/example.env#L1-8
cp .env.example .env
# Edit .env and set NEO4J_PASSWORD and any other secrets.
```

Key rules:
- `.env` is for local, developer-side secrets and MUST be in `.gitignore`.
- Compose files must reference secrets and credentials via `${VAR_NAME}`.
- For CI or production, prefer secret injection from the platform (GitHub
  Actions secrets, cloud secret manager) instead of a file-based `.env`.

Build the image
---------------
We use a multi-stage build (builder → runtime). The builder installs system
packages and Python deps; the runtime image is lean and uses a non-root user.

Build locally:

```/dev/null/example.commands#L1-6
# Build locally using builder + runtime layers
make docker-build
# Or:
docker build -t sbir-etl:local -f Dockerfile .
```

Dev: local compose
------------------
The `dev` profile mounts local source and config directories into the container,
making iteration fast. It also enables auto-reload (`watchfiles`) in the
Dagster development entrypoint.

Start dev stack:

```/dev/null/example.commands#L10-18
cp .env.example .env   # one-time (fill secrets)
make docker-up-dev
# OR manually:
docker compose --env-file .env --profile dev -f docker-compose.yml -f docker/docker-compose.dev.yml up --build
```

Notes:
- The `dev` profile bind-mounts `./src`, `./config`, `./data`, `./logs` into the
  container so containers write artifacts to host directories for easy debugging.
- Use `make docker-logs SERVICE=app` to tail logs.

Test: containerized CI compose
------------------------------
The test compose overlay provisions ephemeral services and runs `pytest`
inside a container. It is used by CI to validate the image and runtime.

Run locally (ephemeral):

```/dev/null/example.commands#L20-26
make docker-test
# Or:
docker compose --env-file .env -f docker-compose.yml -f docker/docker-compose.test.yml up --abort-on-container-exit --build
```

The test overlay:
- Starts an ephemeral Neo4j instance with a small test dataset.
- Starts the app container configured to run tests (`pytest`) and then exits.
- If any container exits non-zero, the Compose run fails.

Prod: production-like compose
-----------------------------
The base `docker-compose.yml` targets production-like usage and uses named
volumes (no host source bind mounts). Deployments should inject secrets into
environment variables or use the deployment platform's secret management.

Example (production-like run):

```/dev/null/example.commands#L28-34
# Ensure .env has production values or the environment provides them
docker compose --env-file .env -f docker-compose.yml up -d --build
```

Entrypoints & waiting for dependencies
-------------------------------------
Entrypoints are provided under `sbir-etl/scripts/docker/entrypoint.sh`. Each
service uses the same image but different entrypoint arguments to start the
webserver, daemon, or run ad-hoc commands.

Important behavior:
- Entrypoint scripts attempt to source `.env` (and /run/secrets) before starting.
- Entrypoint uses `wait-for-service.sh` to wait for Neo4j (Bolt port) and the
  Dagster web API to be healthy before starting dependent services.
- Entrypoints will exit non-zero if dependencies do not become healthy in a
  configurable timeout.

Health checks and readiness
---------------------------
- Compose services declare health checks where applicable:
  - Neo4j: checks via `cypher-shell` with credentials.
  - Dagster webserver: polls `/server_info` expecting HTTP 200.
- Entrypoint `wait-for-service.sh` provides a robust TCP/HTTP probe with logs
  and configurable timeouts so you can see progress in container logs.
- CI uses health-check gating and `depends_on: condition: service_healthy` to
  reduce flakiness.

Volumes & data persistence
--------------------------
- Neo4j uses named volumes: `neo4j_data`, `neo4j_logs`, `neo4j_import`. These
  preserve the graph across container restarts.
- Dev profile uses host bind mounts for `./data`, `./logs`, `./config`, and
  `./metrics` so artifacts are accessible on the host.
- For very large data on macOS, be aware that bind mounts can be slow; prefer
  named volumes for heavy files.

CI integration
--------------
Recommended CI workflow (GitHub Actions):
1. Build the multi-stage image (cache layers).
2. Run the test compose overlay to start ephemeral Neo4j and execute `pytest`.
3. If tests pass, optionally push the image to the registry.

High-level example (CI job steps):

```/dev/null/example.ci#L1-12
- name: Build image
  run: make docker-build
- name: Run containerized tests
  run: make docker-test
```

Best practices & tips
--------------------
- Keep secrets out of version control — use `.env.example` and platform secrets.
- Use the Makefile targets rather than raw docker compose commands for
  consistent behavior across environments.
- MacOS performance:
  - Avoid mounting extremely large directories into containers.
  - Mount only `src/` and `config/` for dev, or use a named volume for data.
- Use multi-stage builds to minimize final image size and speed up CI rebuilds.
- Use `tini` or equivalent as PID 1 in the final image to handle signals.

Troubleshooting checklist
-------------------------
If something fails to start:
1. Check container logs: `make docker-logs SERVICE=app`
2. Inspect progress file for profiler or service health (if applicable):
   The profiler and entrypoints emit clear startup logging and progress messages.
3. Verify `.env` contains `NEO4J_USER/NEO4J_PASSWORD` and `SBIR_ETL__NEO4J__...`
4. For webserver failures, curl the health endpoint from host:
```/dev/null/example.commands#L40-46
curl http://localhost:3000/server_info
```
5. If Neo4j fails to start, check `neo4j_logs` volume and container logs for
   JVM or plugin errors.
6. If containerized tests fail, run `docker compose -f docker-compose.yml -f docker/docker-compose.test.yml up` and inspect the test container logs.

Next steps & recommended milestones
----------------------------------
- Milestone 1 (done): `.env.example`, Compose secrets replaced, wait-for script.
- Milestone 2: Add multi-stage Dockerfile + entrypoint integration (if not yet present).
- Milestone 3: Add `docker/docker-compose.dev.yml` and `docker/docker-compose.test.yml`.
- Milestone 4: Add CI job to build and test image in container.

If you want, I can:
- Create the Compose overlays and CI workflow skeleton.
- Add the multi-stage `Dockerfile` and finalize entrypoint integration.
- Add a short troubleshooting checklist specific to Neo4j plugin/version issues.

Contact / reference
-------------------
- Entrypoint: `sbir-etl/scripts/docker/entrypoint.sh`
- Health wait helper: `sbir-etl/scripts/docker/wait-for-service.sh`
- Make helpers: `Makefile`
- Compose file: `docker-compose.yml` (base)

End of containerization guide.