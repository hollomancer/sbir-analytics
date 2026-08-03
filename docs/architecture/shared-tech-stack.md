# Shared Technology Stack

**Type**: Reference

**Owner**: Engineering Team

**Last-Reviewed**: 2026-08-03

**Status**: Active

This repository is a Python monorepo for turning public SBIR and related federal data into an
analytical Neo4j graph. Shared ETL primitives live at the repository root; orchestration, graph
loading, and ML concerns live in focused workspace packages.

## Package boundaries

```text
sbir_etl/                         shared extraction, enrichment, transformation,
                                  validation, models, configuration, identity, utilities
packages/sbir-analytics/          Dagster assets, jobs, schedules, sensors, API
packages/sbir-graph/              Neo4j loaders and graph-specific utilities
packages/sbir-ml/                 CET, transition, and embedding/model code
```

Dependency direction is inward toward `sbir_etl`: the workspace packages may consume shared
primitives, but `sbir_etl` must not import from a workspace package. The graph and ML packages must
not depend on each other. These rules are enforced by
`scripts/ci/check_architecture_boundaries.py`.

See [Detailed Architecture Overview](detailed-overview.md) for component and data-flow diagrams.

## Runtime stack

| Concern | Technology | Where it belongs |
| --- | --- | --- |
| Language and packaging | Python 3.11 or 3.12, uv workspaces | Root and all packages |
| Tabular processing | pandas, DuckDB, PyArrow | `sbir_etl`, assets, studies |
| Configuration and models | Pydantic, YAML | `sbir_etl/config/`, `config/` |
| Orchestration | Dagster | `packages/sbir-analytics/` |
| Graph database | Neo4j 5 | `packages/sbir-graph/` and read-only API queries |
| Analytics API | FastAPI | `packages/sbir-analytics/sbir_analytics/api/` |
| Machine learning | scikit-learn, PyTorch/Transformers where required | `packages/sbir-ml/` |
| Local/live containers | Docker Compose | Root Compose files |
| Testing and quality | pytest, Ruff, MyPy | Root tool configuration and `tests/` |

## Installing dependencies

Install the complete local stack used by `make dev`:

```bash
make install
```

That runs `uv sync --extra stack-dev`, which installs the root project, developer tools, and all
three workspace packages. Smaller installations are explicit:

```bash
make install-core   # shared sbir_etl project only
make install-ml     # full stack plus heavyweight ML dependencies
```

## Shared patterns

### Configuration

Use `sbir_etl.config.loader.get_config()` instead of reading YAML directly. Configuration is merged
from `config/base.yaml`, an optional environment profile, and `SBIR_ETL__...` overrides, then
validated with Pydantic. See the [configuration reference](../configuration.md).

### Company identity

Canonical company normalization and matching live in `sbir_etl/identity/`. Consumers should reuse
those primitives rather than introducing independent RapidFuzz scorers or normalization rules. CI
enforces this boundary with `scripts/ci/check_identity_boundaries.py`.

### Logging and monitoring

Structured logging is configured in `sbir_etl/utils/logging_config.py`. Reusable execution metrics,
alerts, and decorators live in `sbir_etl/utils/monitoring/`. Dagster assets should emit orchestration
metadata while shared libraries remain usable outside Dagster.

### Dagster assets

Assets, jobs, schedules, and sensors live under
`packages/sbir-analytics/sbir_analytics/`. Keep extraction and transformation logic in `sbir_etl`
when it is independently reusable. Do not add `from __future__ import annotations` to Dagster asset
modules because it breaks runtime context type validation.

### Neo4j loading

Graph writes belong in `packages/sbir-graph/sbir_graph/loaders/neo4j/`. Loaders should be
idempotent and use `MERGE` for stable identities. The analytics API is read-only; its query policy
is documented in [Private Analytics API](private-analytics-api.md).

### Studies and research outputs

Question-driven analysis belongs under `studies/`. The canonical inventory of questions is
[`docs/research-questions.md`](../research-questions.md). Use the
[epistemic tiers](../steering/epistemic-tiers.md) to distinguish exploratory results from validated
evidence.

## Testing boundaries

Tests mirror the repository layers:

```text
tests/unit/          fast isolated behavior
tests/integration/   interactions between components or services
tests/functional/    pipeline-level behavior
tests/e2e/           end-to-end scenarios, commonly with Neo4j
tests/golden/        stable expected-output comparisons
```

Common commands:

```bash
make test-unit
make test-integration
make test
make check
```

The sole GitHub Actions workflow, `.github/workflows/ci.yml`, runs lint, type, security, repository
guards, tests, and targeted Docker/setup checks. It never extracts, enriches, materializes, or
publishes production data.

## Deployment boundary

The live data plane runs from `/Users/conradhollomon/projects/sbir-analytics-server` on the Mac mini.
Docker Compose manages Dagster, Neo4j, and related services; persistent data lives on
`/Volumes/SSDmini/sbir-analytics`; ingress remains Tailscale Serve only. GitHub Actions is CI only.

Before any server operation, read the
[Mac mini runbook](../deployment/mac-mini-server.md#live-instance-on-this-mac-mini). Never operate
the live stack from a development checkout or enable Tailscale Funnel.

## Adding a dependency or component

Before adding technology, identify the research or operational question it answers and place it in
the narrowest existing package. Then update the owning `pyproject.toml`, add tests at the matching
boundary, and run the architecture guards. A new cross-package abstraction is justified only when
multiple current consumers need the same behavior.
