# Containerize SBIR ETL Runtime

## Why

The repository currently includes a single-stage `Dockerfile` and a simplified `docker-compose.yml` that runs `dagster dev` inside one container. This approach is useful for a quick demo but it is insufficient for real development or deployment:

- The image installs everything in one layer, bakes the development entrypoint, and lacks a pinned builder/runtime split, so rebuilding after dependency updates is slow and the resulting artifact cannot be promoted to staging or production without modifications (see `Dockerfile`).
- `docker-compose.yml` merges the Dagster webserver and the scheduler/daemon into the same container, hardcodes test credentials (`NEO4J_AUTH=neo4j/password123`), and does not provide health-checked dependencies or production-like networking.
- There is no `.env` contract for secrets, no container-specific configuration file, and no automation around building, testing, or publishing container images, leaving every teammate to improvise their own workflow.
- CI cannot exercise the pipeline inside a container today, so we have no signal that the image actually builds, bootstraps data directories, or connects to Neo4j before we attempt to deploy it.

To make the ETL reproducible across laptops, CI, and cloud environments we need a spec-backed change that designs proper images, entrypoints, compose profiles, and documentation.

## What Changes

- **Multi-stage Python image** that installs system packages (curl, build-essential, libpq-dev), runs `poetry install --only main --no-root` in a builder layer, and copies the venv + application code into a slim runtime layer with a non-root `sbir` user. Include `tini` and health-check scripts for graceful shutdowns.
- **Service-specific entrypoints** under `scripts/docker/` for `dagster-webserver`, `dagster-daemon`, and an ad-hoc `etl-runner` CLI container. Each script should load environment variables from mounted config, wait for Neo4j, and emit structured logs.
- **Compose stack refresh** with separate services for `neo4j`, `dagster-webserver`, `dagster-daemon`, `etl-runner`, and optional helpers (DuckDB shell, docs). Provide named volumes for Neo4j data/logs/import and bind mounts for `data/`, `config/`, `logs/`, and `metrics/` when running in the `dev` profile. Production profile should rely on image layers only.
- **Environment & configuration plumbing**: introduce `.env` + `.env.example`, add `config/docker.yaml` describing container defaults, and document how secrets flow through `SBIR_ETL__` variables. Compose files must never hardcode secrets.
- **Automation & CI hooks**: add Make targets / scripts for `docker-build`, `docker-compose up`, and `docker-test`. Update GitHub Actions to build the image, run unit tests inside it, and cache the build layers.
- **Operational documentation** in `docs/deployment/containerization.md` that covers local dev, CI usage, pushing images to a registry, and troubleshooting health checks.

## Impact

### Affected Specs
- **runtime-environment** *(new)*: defines deterministic container images, compose profiles, env/secrets handling, and health checks for Dagster + Neo4j.

### Affected Code
- Root `Dockerfile` (replace with multi-stage build) and new `.dockerignore`.
- `docker-compose.yml` plus per-profile overlays (`docker/docker-compose.dev.yml`, `docker/docker-compose.test.yml`).
- `scripts/docker/*.sh` entrypoints and wait-for utilities.
- `.env`, `.env.example`, `config/docker.yaml`, and updates to `config/README.md` + `.gitignore` for local secrets.
- `Makefile` (or `scripts/manage.py`) for container commands and GitHub Actions workflow steps under `.github/workflows/`.
- `docs/deployment/containerization.md` (new) and README container quick-start section.

### Dependencies
- **New system packages** inside the image: `build-essential`, `git`, `libpq-dev`, `tini`, and `gosu` (or equivalent) to drop privileges.
- **Optional Python dependency**: `watchfiles>=0.22` to support hot reload when running the dev compose profile.

### Risks / Mitigations
- *Image bloat*: multi-stage build keeps final image lean by copying only the necessary wheels/venv.
- *Secrets exposure*: `.env` stays local-only and Compose uses variable expansion; add docs and `.gitignore` safeguards.
- *Service orchestration complexity*: health checks and explicit `depends_on` ensure the Dagster daemon waits for Neo4j before starting schedules.

### Out of Scope
- Kubernetes manifests or Helm charts (we focus on Docker + Compose only in this change).
- Neo4j backup/restore automation (document manual volume management instead).
