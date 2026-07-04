---

Type: Overview
Owner: docs@project
Last-Reviewed: 2025-11-21
Status: active

---

# SBIR ETL Documentation

Welcome. This site collects the current documentation for the SBIR/STTR commercialization analytics research project. Like the README notes, this is a personal side project rather than production software, so the docs should be read as the current documented approach and working notes rather than polished, authoritative product documentation.

- **specifications** (`specs/`) capture design notes, tasks, and requirements as they evolved.
- User and developer documentation lives under `docs/` (this site).
- Steering documents live in `docs/steering/` (architectural patterns and guidance).

## What is this project?

See [README](../README.md) for project context, research questions, and setup. The docs here are the detailed reference: architecture, methodology, guides, and schemas.

## Quick links

### Getting Started

- Getting started: [`README.md`](../README.md)
- Architecture overview: [`architecture/detailed-overview.md`](architecture/detailed-overview.md)
- Shared tech stack: [`architecture/shared-tech-stack.md`](architecture/shared-tech-stack.md)

### Deployment (Optional Cloud Setup)

- **[Experimental deployment path](deployment/README.md)** - GitHub Actions orchestration notes
- **[AWS Infrastructure](deployment/aws-deployment.md)** - Optional Lambda + S3 + Step Functions setup
- [Docker guide](development/docker.md) - Containers for local development, CI, and testing

### Development Guides

- **Docker Setup:**
  - [Docker Development](development/docker.md) - Setup, configuration, and troubleshooting
- [Exception Handling](development/exception-handling.md)
- [Logging Standards](development/logging-standards.md)
- [Spec Workflow](development/spec-workflow-guide.md)

### Reference

- Government policy demo plan (incl. NSF/SBA worked example): [`guides/government-policy-demo-plan.md`](guides/government-policy-demo-plan.md)
- Statistical reporting guide: [`guides/statistical-reporting.md`](guides/statistical-reporting.md)
- Neo4j schema reference: [`schemas/neo4j.md`](schemas/neo4j.md)
- Data dictionaries: [`data/dictionaries/`](data/dictionaries/)
- Configuration: [`configuration.md`](configuration.md)
- Decisions (ADRs): [`decisions/`](decisions/)
- Specification System: [`specifications/README.md`](specifications/README.md)

## Conventions

All docs use Diátaxis types: Tutorials, How-to guides, Explanations, References. Each file includes front-matter with Type, Owner, Last-Reviewed, and Status.

## Governance

- Code changes that affect architecture, data contracts, or performance must update relevant docs/specs in the same PR.
- Each doc declares an owner and should be reviewed at least quarterly.
