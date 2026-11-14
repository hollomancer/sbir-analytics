# Architecture

How the monorepo is put together and why. Start with the overview; the rest are
subsystem depth or superseded plans.

| Document | What it covers |
|---|---|
| [Architecture overview](detailed-overview.md) | Package boundaries, data flow, storage, evidence and deployment boundaries. The entry point. |
| [Dagster pipelines](dagster-pipelines.md) | Assets, jobs, schedules, sensors |
| [Asset naming standards](asset-naming-standards.md) | Naming rules for Dagster assets |

## Plans

Forward-looking designs, not descriptions of what exists today.

| Plan | Status |
|---|---|
| [Dagster reorganization](dagster-reorganization-plan.md) | Proposed |
| [Neo4j retirement](../decisions/ADR-006-retire-neo4j.md) | Accepted; retires Neo4j and its proposed assertion projection |
