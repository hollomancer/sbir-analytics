---
Type: Steering
Owner: engineering@project
Last-Reviewed: 2026-08-03
Status: active
---

# Technology Decisions

This document records durable technology choices. It intentionally does not duplicate setup,
testing, configuration, or deployment commands; use the linked operational references for those.

## Supported stack

- Python 3.11 or 3.12, managed as a uv workspace.
- pandas, DuckDB, and PyArrow for tabular processing and interchange.
- Pydantic plus YAML for typed configuration.
- Dagster for assets, jobs, schedules, sensors, and run metadata.
- Neo4j 5 for the linked analytical graph.
- scikit-learn and, only where justified, PyTorch/Transformers for ML.
- Docker Compose for local development, tests, and the Mac mini data plane.
- pytest, Ruff, and MyPy for verification.

The [architecture overview](../architecture/detailed-overview.md) owns component placement and
dependency direction. Version constraints live in `pyproject.toml`, `uv.lock`, Compose files, and
CI—not in prose.

## Selection rules

1. Start from an active [research question](../research-questions.md) or a demonstrated operational
   need.
2. Prefer an existing dependency and package boundary over a parallel framework.
3. Put reusable logic in `sbir_etl`; keep orchestration, graph, and ML adapters in their workspace
   packages.
4. Require a current consumer before adding an abstraction, service, or persistence layer.
5. Record consequential or difficult-to-reverse choices as an [ADR](../decisions/README.md).

Managed cloud services are not part of the current runtime. A proposal for one must identify its
owner, credentials, cost boundary, durable rebuild source, failure behavior, and runbook before it
can be described as architecture.

## Operational references

- Installation and first run: [Getting started](../getting-started/README.md)
- Configuration: [Configuration reference](../configuration.md)
- Local containers: [Docker development](../development/docker.md)
- Testing and CI: [Testing index](../testing/index.md)
- Live deployment: [Mac mini runbook](../deployment/mac-mini-server.md)
