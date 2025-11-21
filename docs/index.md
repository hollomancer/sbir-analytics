---

Type: Overview
Owner: docs@project
Last-Reviewed: 2025-11-21
Status: active

---

# SBIR ETL Documentation

Welcome. This site is the canonical documentation for the SBIR ETL pipeline.

-   **Kiro specifications** (`.kiro/specs/`) are the source of truth for designs, tasks, and requirements.
-   User and developer documentation lives under `docs/` (this site).
-   Agent steering documents live in `.kiro/steering/` (architectural patterns and guidance for AI agents).
-   Historical OpenSpec content is archived in `archive/openspec/` for reference.

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
- Getting started: [`README.md`](../README.md)
- Architecture overview: [`architecture/detailed-overview.md`](architecture/detailed-overview.md)
- Shared tech stack: [`architecture/shared-tech-stack.md`](architecture/shared-tech-stack.md)

### Deployment (Cloud-First)
- **[Production deployment](deployment/dagster-cloud-deployment-guide.md)** - Dagster Cloud (Primary)
- **[AWS Infrastructure](deployment/aws-serverless-deployment-guide.md)** - Lambda + S3 + Step Functions
- [Containerization guide](deployment/containerization.md) - Docker (Development/Failover)

### Development Guides
- **Docker Setup:**
  - [Docker Quick Start](development/docker-quickstart.md) - Step-by-step setup guide
  - [Docker Troubleshooting](development/docker-troubleshooting.md) - Common issues and solutions
  - [Docker Environment Setup](development/docker-env-setup.md) - Configuration guide
- [Exception Handling](development/exception-handling.md)
- [Logging Standards](development/logging-standards.md)
- [Optimization Summary](development/optimization-cleanup-summary.md)
- [Kiro Workflow](development/kiro-workflow-guide.md)

### Reference
- Statistical reporting guide: [`guides/statistical-reporting.md`](guides/statistical-reporting.md)
- Neo4j schema reference: [`schemas/neo4j.md`](schemas/neo4j.md)
- Data dictionaries: [`data/dictionaries/`](data/dictionaries/)
- Configuration: [`configuration/paths.md`](configuration/paths.md)
- Decisions (ADRs): [`decisions/`](decisions/)
- Specification System: [`specifications/README.md`](specifications/README.md)

## Conventions

All docs use Diátaxis types: Tutorials, How-to guides, Explanations, References. Each file includes front-matter with Type, Owner, Last-Reviewed, and Status.

## Governance

- Code changes that affect architecture, data contracts, or performance must update relevant docs/specs in the same PR.
- Each doc declares an owner and should be reviewed at least quarterly.
