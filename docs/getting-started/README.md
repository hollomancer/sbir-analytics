# Getting Started

This guide gets a new developer from a fresh clone to a tested local environment
and a successful Dagster materialization using generated sample data.

> **Data caveat:** No operational SBIR/STTR award data is committed to this
> repository. The sample-data path below is intentionally small and synthetic.
> Reproducing the research analyses requires source downloads, API credentials,
> and additional local services.

## Prerequisites

- Python 3.11 or 3.12
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/)
- `make`
- Docker with Compose V2 if you want Neo4j or the containerized stack

## Local Python Quick Start

From a fresh clone:

```bash
git clone https://github.com/hollomancer/sbir-analytics.git
cd sbir-analytics

# Install the ETL library, Dagster application, graph and ML packages, and dev tools.
make install

# Create and verify local configuration.
cp .env.example .env
make setup-local

# Verify imports and run a small, data-free test selection.
make doctor
make test-smoke

# Create ten synthetic awards plus small SAM.gov, USPTO, and USAspending inputs.
make sample-data

# Start Dagster and open http://localhost:3000.
make dev
```

In the Dagster UI, materialize `raw_sbir_awards`. A successful sample run reads
10 awards from `data/raw/sbir/award_data.csv` and reports them in the asset
materialization metadata. This asset does not require Neo4j.

`make install` is equivalent to `uv sync --extra stack-dev`. Consumers who only
need the reusable `sbir_etl` library can use `make install-core` instead.

## Neo4j

Start only Neo4j while running Dagster locally on the host:

```bash
make neo4j-up
```

- Browser: <http://localhost:7474>
- Bolt: `bolt://localhost:7687`
- Default local credentials: `neo4j` / `test`

The checked-in `.env.example` uses host-local addresses. Docker Compose
overrides those addresses inside containers so services connect to the `neo4j`
service hostname.

To run the complete development stack in containers instead:

```bash
make docker-check-prerequisites
make docker-up-dev
make docker-verify
```

See the [Docker guide](../development/docker.md) for service profiles, logs, and
troubleshooting.

## Everyday Development

```bash
make help          # list supported commands
make test-smoke    # fast local confidence check
make test-unit     # complete unit suite
make lint          # Ruff and MyPy
make docs-check    # repository documentation hygiene
make format        # apply Ruff formatting and safe lint fixes
```

The complete testing strategy, markers, and Docker workflows are documented in
the [testing index](../testing/README.md). Contribution expectations are in
[CONTRIBUTING.md](../../CONTRIBUTING.md).

## Optional Credentials and Real Data

The sample workflow needs no external API credentials. Add credentials to `.env`
only for the data sources you intend to use. `.env.example` documents the
supported variables and must remain safe to commit; never commit `.env`.

For real SBIR award ingestion, place the source CSV at the configured path or
override `extraction.sbir.csv_path`. See the [configuration reference](../configuration.md)
and [data documentation](../data/README.md) before running larger materializations.

## Common Problems

- **`dagster`, `pytest`, or a first-party package is missing:** run `make install`,
  not `make install-core`, then run `make doctor`.
- **Unsupported Python version:** use Python 3.11 or 3.12; the project currently
  excludes Python 3.13.
- **`raw_sbir_awards` cannot find its CSV:** run `make sample-data` and confirm
  `data/raw/sbir/award_data.csv` exists.
- **Neo4j connection fails from host Python:** use `bolt://localhost:7687`.
- **Neo4j connection fails in Compose:** inspect `make docker-logs SERVICE=neo4j`;
  containers use `bolt://neo4j:7687` automatically.
- **Memory pressure:** reduce `SBIR_ETL__ENRICHMENT__PERFORMANCE__CHUNK_SIZE` and
  confirm the setting in the [configuration reference](../configuration.md).

## Where to Go Next

- [Research questions](../research-questions.md) — why the repository exists
- [Architecture overview](../architecture/detailed-overview.md) — package and data flow
- [Development guides](../development/README.md) — code standards and workflows
- [Testing index](../testing/README.md) — local and CI validation
- [Configuration reference](../configuration.md) — YAML and environment overrides
- [Deployment guide](../deployment/README.md) — self-hosted server and local deployment
