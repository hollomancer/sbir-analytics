---

Type: Overview
Owner: docs@project
Last-Reviewed: 2026-07-16
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
- Pipelines, schedules & sensors: [`architecture/dagster-pipelines.md`](architecture/dagster-pipelines.md)

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

### Subsystems & Domains

- Transition detection: [`transition/README.md`](transition/README.md) — scoring, vendor matching, evidence bundles
- ML / CET classification: [`ml/README.md`](ml/README.md) — incl. [rule-engine tuning](ml/cet-rule-engine.md)
- Enrichment sources: [`enrichment/`](enrichment/) — SAM.gov, USASpending, and the full [enricher catalog](enrichment/enricher-catalog.md) (credentials)
- Data pipeline & refreshes: [`data/index.md`](data/index.md) — incl. [weekly awards report](data/weekly-awards-report.md), [capital events & UCC1](data/capital-events.md)
- Fiscal analysis: [`fiscal/sbir-fiscal-pipeline-guide.md`](fiscal/sbir-fiscal-pipeline-guide.md)
- OT consortium: [`ot-consortium/tiers.md`](ot-consortium/tiers.md)
- Analytics API: [`api/README.md`](api/README.md) and [`architecture/private-analytics-api.md`](architecture/private-analytics-api.md)
- Query cookbook: [`queries/transition-queries.md`](queries/transition-queries.md)
- Testing: [`testing/index.md`](testing/index.md)
- Research notes: [`research/`](research/)
- Getting started: [`getting-started/README.md`](getting-started/README.md)

### Tech-area reports (provisional)

Policy-leader deliverables produced by the [tech-area transition report](../specs/tech-area-transition-report/) workflow. All are marked provisional — figures are bounded estimates, not final program rates.

- Nanotechnology: [policy brief](nanotech_sbir_policy_brief.md) · [findings](nanotech_sbir_transition_findings.md) · [methodology](nano_phase3_methodology.md)
- Hypersonics: [policy brief](hypersonics_sbir_policy_brief.md) · [findings](hypersonics_sbir_transition_findings.md)
- Quantum information science: [policy brief](quantum_information_science_sbir_policy_brief.md) · [findings](quantum_information_science_sbir_transition_findings.md)

## Conventions

Docs follow the Diátaxis model (Tutorials, How-to guides, Explanations, References). Curated reference docs carry front-matter with Type, Owner, Last-Reviewed, and Status; many working notes and research docs do not yet. New reference docs should include front-matter, and backfilling it on existing docs is tracked as ongoing cleanup.

## Governance

- Code changes that affect architecture, data contracts, or performance must update relevant docs/specs in the same PR.
- Each doc declares an owner and should be reviewed at least quarterly.
