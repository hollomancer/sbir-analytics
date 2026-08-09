---
Type: Overview
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-08-03
Status: active
---

# SBIR Analytics Documentation

SBIR Analytics is a personal research project for connecting public SBIR/STTR awards to
procurement, patents, strategic technologies, economic effects, and capital formation. No
operational award data is committed to the repository, and a working analysis is not automatically
validated or citable.

## Start here

| Need | Canonical document |
| --- | --- |
| Project context and local setup | [Repository README](../README.md) |
| What the repository exists to answer | [Research questions](research-questions.md) |
| Components and package boundaries | [Architecture overview](architecture/detailed-overview.md) |
| First local run | [Getting started](getting-started/README.md) |
| Configuration keys and load order | [Configuration](configuration.md) |

## Research governance

- [Epistemic tiers](steering/epistemic-tiers.md) - what weight an artifact may carry
- [Study contracts](../studies/README.md) - reproducibility, validation, and permitted claims
- [Specification status](../specs/status.md) - active, gated, deferred, and archive-candidate work
- [Specification workflow](development/spec-workflow-guide.md) - scope, tier, design, and lifecycle
- [Product scope](steering/product.md) - question-first inclusion and exclusion rules

Use these before quoting a result or starting a feature from an old spec.

## Develop and operate

| Area | Owner |
| --- | --- |
| Developer navigation | [Development index](development/README.md) |
| Containers | [Docker development](development/docker.md) |
| Tests and CI | [Testing index](testing/README.md) |
| Versioning and releases | [Versioning policy](steering/versioning.md) |
| Performance measurement | [Performance runbook](performance.md) |
| Deployment navigation | [Deployment index](deployment/README.md) |
| Live self-hosted server operations | [self-hosted server runbook](deployment/self-hosted-server.md) |
| Neo4j migrations | [Migration guide](migrations.md) |
| Decisions | [Architecture decision records](decisions/README.md) |

## Data and subsystems

- [Data sources](data/README.md)
- [Dagster pipelines](architecture/dagster-pipelines.md)
- [Asset naming](architecture/asset-naming-standards.md)
- [DuckDB CET analysis](architecture/duckdb-cet-analysis.md)
- [Transition detection](transition/README.md)
- [Machine learning](ml/README.md)
- [Fiscal pipeline](fiscal/sbir-fiscal-pipeline-guide.md)
- [Neo4j schema](schemas/neo4j.md)
- [Other Transaction consortium tiers](ot-consortium/tiers.md)
- [Statistical reporting utility](guides/statistical-reporting.md)
- [Enrichment](enrichment/README.md) — enricher catalogue and per-source integrations
- [Transition Cypher queries](queries/transition-queries.md)

There is no generated API reference. The package map and dependency rules live in the
[architecture overview](architecture/detailed-overview.md).

## Durable engineering contracts

- [Company identity](steering/company-identity.md)
- [Data quality](steering/data-quality.md)
- [Enrichment patterns](steering/enrichment-patterns.md)
- [Pipeline orchestration](steering/pipeline-orchestration.md)
- [Neo4j patterns](steering/neo4j-patterns.md)
- [Repository structure](steering/structure.md) and [technology choices](steering/tech.md)
- [Glossary](steering/glossary.md)
- [ML methodology review](steering/ml-methodology-review.md)

## Research outputs

Use the [research-output index](research/README.md) to map analyses to research questions,
evidence posture, and data cuts. Technology-area briefs pair an audience-facing summary with
technical findings:

- [Nanotechnology brief](research/nanotech_sbir_policy_brief.md) and
  [technical findings](research/nanotech_sbir_transition_findings.md)
- [Hypersonics brief](research/hypersonics_sbir_policy_brief.md) and
  [technical findings](research/hypersonics_sbir_transition_findings.md)
- [Quantum information science brief](research/quantum_information_science_sbir_policy_brief.md) and
  [technical findings](research/quantum_information_science_sbir_transition_findings.md)

These pairs intentionally remain separate for different audiences. “Provisional” is not a
substitute for a citable study manifest; check evidence status before external use.

## Documentation rules

- One document owns each command, threshold, architecture fact, or status; other pages link to it.
- Current guidance stays under `docs/`; completed plans and superseded narratives move to
  `docs/archive/` with a historical banner.
- Dated research reports retain their original data cut and conclusions rather than being rewritten
  to match new architecture.
- New maintained documents use `docs/_template.md` metadata and link to their owning research
  question or operational obligation.
