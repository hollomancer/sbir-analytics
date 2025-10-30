---
Type: Overview
Owner: docs@project
Last-Reviewed: 2025-10-30
Status: active
---

# SBIR ETL Documentation

Welcome. This site is the canonical documentation for the SBIR ETL pipeline.

- Specs and requirements live in `.kiro/specs/` (Kiro is the source of truth for designs, tasks, and requirements).
- User and developer docs live under `docs/` (this site).
- Agent steering documents live in `.kiro/steering/` (architectural patterns and guidance for AI agents).
- Historical OpenSpec content is archived in `archive/openspec/`.

## What is this project?
Graph-based ETL that ingests SBIR/USAspending/USPTO data and loads a Neo4j graph. Orchestrated by Dagster, processed with DuckDB/Pandas, deployed via Docker.

## Quick links
- Getting started: `README.md`
- Architecture overview: `docs/architecture/overview.md`
- Containerization guide: `docs/guides/containerization.md`
- Neo4j schema reference: `docs/references/schemas/neo4j.md`
- How-to guides: `docs/how-to/`
- Decisions (ADRs): `docs/decisions/`

## Conventions
All docs use Diátaxis types: Tutorials, How-to guides, Explanations, References. Each file includes front-matter with Type, Owner, Last-Reviewed, and Status.

## Governance
- Code changes that affect architecture, data contracts, or performance must update relevant docs/specs in the same PR.
- Each doc declares an owner and should be reviewed at least quarterly.
