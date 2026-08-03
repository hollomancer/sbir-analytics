---
Type: Architecture
Owner: engineering@project
Last-Reviewed: 2026-08-03
Status: active
---

# Architecture Overview

SBIR Analytics is a Python monorepo that turns public SBIR/STTR and related federal data into
reusable analytical datasets, a Neo4j graph, and reproducible research outputs. The architecture is
question-driven: new components must serve a question in the
[canonical inventory](../research-questions.md), not merely add a new data source or technology.

## Package boundaries

```text
sbir_etl/                         shared ETL, identity, models, configuration,
                                  validation, quality, and monitoring primitives
packages/sbir-analytics/          Dagster assets, jobs, schedules, sensors, and API
packages/sbir-graph/              Neo4j loaders, queries, and migrations
packages/sbir-ml/                 CET, transition, and model-specific code
studies/                           frozen analytical contracts and study outputs
scripts/                           operator and transitional entry points
```

Dependencies point inward toward `sbir_etl`. Workspace packages may consume shared primitives;
`sbir_etl` must not import workspace packages, and the graph and ML packages must not depend on one
another. `scripts/ci/check_architecture_boundaries.py` enforces these rules.

## Runtime stack

| Concern | Technology | Canonical location |
| --- | --- | --- |
| Language and packaging | Python 3.11 or 3.12, uv workspace | `pyproject.toml`, `uv.lock` |
| Tabular processing | pandas, DuckDB, PyArrow | `sbir_etl/`, assets, studies |
| Configuration | Pydantic and YAML | `sbir_etl/config/`, `config/` |
| Orchestration | Dagster | `packages/sbir-analytics/` |
| Graph | Neo4j 5 | `packages/sbir-graph/` |
| Read-only analytics API | FastAPI | `packages/sbir-analytics/sbir_analytics/api/` |
| Machine learning | scikit-learn; PyTorch/Transformers where required | `packages/sbir-ml/` |
| Containers | Docker Compose | root Compose files |
| Quality and tests | Ruff, MyPy, pytest | root configuration and `tests/` |

## Data flow

```text
public sources
    │
    ▼
extract and snapshot ──▶ validate and normalize ──▶ enrich and classify
    │                                                     │
    └──────────────▶ Parquet / DuckDB                     ▼
                                                   transform and link
                                                          │
                            ┌─────────────────────────────┴─────────────┐
                            ▼                                           ▼
                       Neo4j graph                              study datasets
                            │                                           │
                            ▼                                           ▼
                    read-only API                         manifests, reports, evidence
```

Operational source pipelines currently cover SBIR.gov, USAspending, SAM.gov, and USPTO data.
Research workflows also use SEC EDGAR/Form D, UCC filings, capital-event evidence, subawards, and
other bounded sources. A source appearing in a study does not imply a scheduled production
pipeline; [data documentation](../data/index.md) records that distinction.

Company identity is a shared contract. Normalization and matching live in `sbir_etl/identity/` and
must be reused by source-specific enrichers, graph loading, and studies. See the
[company identity contract](../steering/company-identity.md).

## Execution surfaces

- **Library execution:** reusable extraction, transformation, validation, and identity logic in
  `sbir_etl`.
- **Dagster:** assets compose that logic into observable jobs, schedules, and sensors. See
  [Dagster pipelines](dagster-pipelines.md).
- **Scripts:** bounded operator commands and transitional bridges. Scripts should call reusable
  modules instead of becoming a second implementation.
- **Studies:** frozen inputs, parameters, code references, and evidence status under `studies/`.
- **API:** authenticated, read-only graph access. It never owns mutation or migration behavior.

## Storage and graph boundary

Parquet and DuckDB are the primary analytical interchange formats. Neo4j represents linked
organizations, awards/financial transactions, patents, technology areas, and their evidence-backed
relationships. Graph writes belong in `packages/sbir-graph/sbir_graph/loaders/neo4j/`, use stable
identities, and remain idempotent. Schema changes use the [migration system](../migrations.md).

Research-only outputs such as a capital-event Parquet file do not become graph entities merely
because a future research question might use them. Add a graph representation only when an active
consumer and evidence contract require it.

## Evidence boundary

Pipeline completion is not evidence validation. The repository distinguishes reusable primitives,
operational pipelines, validated evidence, and exploratory analysis through
[epistemic tiers](../steering/epistemic-tiers.md). Study manifests record the data cut, method,
permitted claims, and evidence status. A result is not externally citable solely because code can
compute it.

## Deployment boundary

The only live data plane is the Mac mini checkout at
`/Users/conradhollomon/projects/sbir-analytics-server`. Docker Compose runs Dagster, Neo4j, and the
private API; persistent data lives under `/Volumes/SSDmini/sbir-analytics`; ingress is Tailscale
Serve only. GitHub Actions performs CI and never materializes live data.

Before any live operation, read the
[Mac mini runbook](../deployment/mac-mini-server.md#live-instance-on-this-mac-mini). AWS Batch,
Lambda, Step Functions, and S3 are not part of the current architecture.

## Sources of truth

| Question | Owner |
| --- | --- |
| Why the repository exists | [Research questions](../research-questions.md) |
| Package and dependency rules | This overview and architecture guards |
| Configuration keys and load order | [Configuration reference](../configuration.md) |
| Local commands and containers | [Getting started](../getting-started/README.md), [Docker](../development/docker.md) |
| CI and tests | [Testing index](../testing/index.md) |
| Live operations | [Mac mini runbook](../deployment/mac-mini-server.md) |
| Graph model | [Neo4j schema](../schemas/neo4j.md) and [migrations](../migrations.md) |
| Evidence and citability | [Epistemic tiers](../steering/epistemic-tiers.md), [study contracts](../../studies/README.md) |

Narrow references may explain one subsystem in depth, but they should link to these owners rather
than restating commands, thresholds, or deployment facts.
