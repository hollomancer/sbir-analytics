# Architecture

How the monorepo is put together and why. Start with the overview; the rest are
subsystem depth or superseded plans.

| Document | What it covers |
|---|---|
| [Architecture overview](detailed-overview.md) | Package boundaries, data flow, storage, evidence and deployment boundaries. The entry point. |
| [Dagster pipelines](dagster-pipelines.md) | Assets, jobs, schedules, sensors |
| [Asset naming standards](asset-naming-standards.md) | Naming rules for Dagster assets |
| [DuckDB for CET classification](duckdb-cet-analysis.md) | Trade-off analysis behind the CET storage choice |

## Plans

Forward-looking designs, not descriptions of what exists today.

| Plan | Status |
|---|---|
| [Neo4j epistemic assertions](neo4j-epistemic-assertions-plan.md) | Proposed; see ADR-005 |
| [Dagster reorganization](dagster-reorganization-plan.md) | Proposed |
