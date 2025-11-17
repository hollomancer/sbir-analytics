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

Cloud-native, graph-based ETL pipeline that ingests SBIR/USAspending/USPTO data and loads a Neo4j graph database.

**Production Architecture**:
- **Orchestration**: Dagster Cloud Solo Plan, AWS Step Functions
- **Compute**: AWS Lambda (serverless)
- **Storage**: AWS S3 (data lake)
- **Database**: Neo4j Aura (cloud graph database)
- **Processing**: DuckDB/Pandas

**Development**: Docker Compose + local Dagster (secondary/failover option)

## Quick links

### Getting Started
- Getting started: `README.md`
- Quick start (local dev): `QUICK_START.md`
- Architecture overview: `docs/architecture/detailed-overview.md`
- Shared tech stack: `docs/architecture/shared-tech-stack.md`

### Deployment (Cloud-First)
- **[Production deployment](docs/deployment/dagster-cloud-migration.md)** - Dagster Cloud (Primary)
- **[AWS Infrastructure](docs/deployment/aws-infrastructure.md)** - Lambda + S3 + Step Functions
- **[Neo4j Aura Setup](docs/data/neo4j-aura-setup.md)** - Cloud graph database
- **[S3 Data Migration](docs/deployment/s3-data-migration.md)** - S3 data lake
- [Containerization guide](docs/deployment/containerization.md) - Docker (Development/Failover)

### Reference
- Statistical reporting guide: `docs/guides/statistical-reporting.md`
- Neo4j schema reference: `docs/references/schemas/neo4j.md`
- Configuration: `docs/configuration/paths.md`
- Decisions (ADRs): `docs/decisions/`

## Conventions

All docs use Diátaxis types: Tutorials, How-to guides, Explanations, References. Each file includes front-matter with Type, Owner, Last-Reviewed, and Status.

## Governance

- Code changes that affect architecture, data contracts, or performance must update relevant docs/specs in the same PR.
- Each doc declares an owner and should be reviewed at least quarterly.
