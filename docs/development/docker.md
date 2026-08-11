# Docker Development Guide

**Audience**: Developers and operators

**Prerequisites**: Docker Desktop or Docker Engine with Compose V2

**Last-Reviewed**: 2026-08-03

Docker Compose is the standard local service environment and the live self-hosted server deployment
mechanism. GitHub Actions builds an image only as a conditional CI smoke test; it does not deploy
or run the data plane.

This guide covers the root `docker-compose.yml` development and test profiles. For the separate
live compose file and server-only targets, use the [self-hosted server runbook](../deployment/self-hosted-server.md).

## Quick start

```bash
make docker-check-prerequisites
cp .env.example .env
make docker-up-dev
make docker-verify
```

At minimum, set local Neo4j credentials in `.env`:

```dotenv
NEO4J_USER=neo4j
NEO4J_PASSWORD=test
```

Local services expose:

- Dagster UI: <http://localhost:3000>
- Neo4j Browser: <http://localhost:7474>
- Neo4j Bolt: `bolt://localhost:7687`

## Compose profiles

The root compose file has two profiles:

| Profile | Purpose | Primary command |
| --- | --- | --- |
| `dev` | Dagster, Neo4j, and tools for interactive development | `make docker-up-dev` |
| `ci` | Ephemeral Neo4j and application test runner | `make docker-test` |

The live deployment does not use a root `prod` profile. It uses
`docker-compose.server.yml --profile server` from the dedicated deployment checkout.

## Make targets

Prefer these targets over hand-written Compose commands:

| Target | Purpose |
| --- | --- |
| `make docker-build` | Build the application image |
| `make docker-buildx` | Build through Buildx |
| `make docker-up-dev` | Start development services |
| `make docker-up-tools` | Start the utility container |
| `make docker-down` | Stop local services and remove local volumes |
| `make docker-rebuild` | Rebuild and restart the development stack |
| `make docker-logs SERVICE=neo4j` | Follow service logs |
| `make docker-exec SERVICE=dagster-webserver CMD=sh` | Run a command in a service |
| `make docker-test` | Run containerized tests through the `ci` profile |
| `make docker-e2e-minimal` | Run the minimal E2E scenario |
| `make docker-e2e-clean` | Remove the E2E environment and volumes |
| `make neo4j-up` / `make neo4j-down` | Start or stop local Neo4j |
| `make validate-config` | Validate the root compose and environment files |

`make docker-down` and `make docker-e2e-clean` remove local Compose volumes. They are development
commands, not live-server shutdown commands.

## Common workflows

View logs and service state:

```bash
docker compose --profile dev ps
make docker-logs
make docker-logs SERVICE=neo4j
```

List or execute Dagster jobs:

```bash
docker compose --profile dev exec dagster-webserver \
  dagster job list -m sbir_analytics.definitions

docker compose --profile dev exec dagster-webserver \
  dagster job execute -m sbir_analytics.definitions -j sbir_weekly_refresh_job
```

Open a Neo4j shell:

```bash
make db-shell
```

Run tests inside the app image:

```bash
make docker-test
E2E_TEST_SCENARIO=standard make docker-e2e
make docker-e2e-clean
```

See [End-to-End Testing](../testing/e2e-testing.md) for scenario and environment details.

## Environment and configuration

Compose passes normal process variables into the containers. Common values include:

| Variable | Purpose |
| --- | --- |
| `NEO4J_URI` | Bolt connection URI |
| `NEO4J_USER` / `NEO4J_PASSWORD` | Graph credentials |
| `NEO4J_DATABASE` | Graph database name |
| `SBIR_ETL__PIPELINE__ENVIRONMENT` | Select `dev`, `test`, or `prod` YAML profile |
| `SBIR_ETL__PATHS__DATA_ROOT` | Data root visible inside the process |
| `E2E_TEST_SCENARIO` / `E2E_TEST_TIMEOUT` | E2E runner selection and timeout |

Use `SBIR_ETL__SECTION__KEY` variables only for keys accepted by the Pydantic schemas. See the
[configuration reference](../configuration.md). `.env` is for local development and must remain
uncommitted; `.env.server` belongs only to the deployment checkout.

## Images

| Dockerfile | Purpose |
| --- | --- |
| `Dockerfile` | Locked ETL, Dagster, graph, ML/NLP, fiscal, and browser-automation image |

Build locally:

```bash
make docker-build
```

The image uses the multi-architecture Python 3.11.9 manifest pinned by digest in
`Dockerfile`, then installs the `server` extra with `uv sync --locked`. The flag
rejects drift between workspace manifests and `uv.lock` and does not update the
lock during the build. The committed lock controls the image's application
environment; the separately pinned uv bootstrap and isolated wheel-build tools
are outside that contract. Updating the Python base or uv installer is an
explicit reviewed Dockerfile change.

The server extra includes the locked `en_core_web_sm` 3.8.0 pipeline used by
`EvidenceExtractor`; heavy-asset runs do not silently lose sentence extraction
because the model is absent. Introducing the webserver runtime also moved the
locked Dagster family from 1.13.1 to 1.13.17 and added its webserver transitive
dependencies. Treat that as a deployment dependency change during release
classification, not as a Docker-only refactor.

The development ETL runner mounts live source directories individually. It does
not bind the repository over `/app`, because doing so would hide the Linux
virtual environment baked into `/app/.venv`. The CI profile likewise runs from
a locked test-image stage; it does not install packages when the container
starts.
GitHub Actions builds and smoke-tests this image but does not publish it.

## Data and volumes

Local development uses named volumes and bind mounts declared in `docker-compose.yml`. The live
server uses the bind mounts configured by `SERVER_*_DIR` plus the Docker
`dagster_home` volume. Never point a development compose command at those live paths.

Back up data before intentionally resetting a local graph. `make neo4j-reset` is destructive to the
local Neo4j volume.

## Troubleshooting

Validate the resolved configuration:

```bash
docker compose --profile dev config -q
make validate-config
```

If a service is unhealthy:

```bash
docker compose --profile dev ps
make docker-logs SERVICE=dagster-webserver
make docker-logs SERVICE=neo4j
```

If ports 3000, 7474, or 7687 are occupied, stop the conflicting local service or change the
published port in `.env`. If a bind mount is empty, verify the host path and Docker Desktop file
sharing permissions.

For live failures, stop here and switch to the
[server runbook](../deployment/self-hosted-server.md#live-instance-on-the-server-host); do not improvise
against the development checkout.
