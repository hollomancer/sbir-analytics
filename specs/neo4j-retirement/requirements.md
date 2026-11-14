# Neo4j Retirement Requirements

> **Lifecycle status:** Maintenance
> **Spec-file progress:** Repository implementation complete; one-time operator cutover pending
> **Operational obligation:** repository maintenance and deployment safety.

**Target epistemic tier:** `pipelines`

**Research question anchor:** None. This change removes an unused persistence projection.

**Out of scope:** new analytical tables; replacement graph services; live data deletion;
changes to frozen SBA study, release, or review bytes; new research claims.

---

## Done when

A contributor can install, test, and run the supported stack without Neo4j, `sbir-graph`,
graph credentials, graph ports, or graph-specific CI services. Governed Parquet and DuckDB
artifacts remain authoritative. The retired implementation remains recoverable from the
annotated `v0.18.0` tag.

---

## Background

Neo4j is a derived projection with no active graph-native research consumer. Its package,
loaders, service, credentials, ports, CI lane, and documentation add operational cost and can
make the projection look authoritative. Existing governed tables already hold the analytical
records. Retirement makes the repository surface match that authority boundary.

## Requirements

### Requirement 1 — Remove the graph runtime

**User story:** As a pipeline engineer, I want one service-free analytical stack, so that I do
not maintain infrastructure with no active consumer.

#### Acceptance Criteria

1. THE Repository SHALL contain no active `sbir-graph` package or Neo4j client dependency.
2. THE Dagster definitions SHALL load without importing `neo4j` or `sbir_graph`.
3. THE Repository SHALL remove graph-only assets, jobs, migrations, queries, scripts, and tests.
4. THE Repository SHALL preserve upstream CET, USPTO, transition, categorization, and SEC tables.
5. THE Repository SHALL not create replacement tables for graph-only heuristics without a named
   consumer and separate specification.

### Requirement 2 — Remove the service boundary

**User story:** As an operator, I want the supported stack to run without a graph database, so
that deployment has fewer credentials, ports, volumes, and failure modes.

#### Acceptance Criteria

1. THE Compose files SHALL define no Neo4j service, dependency, volume, port, or environment key.
2. THE server scripts SHALL not wait for, expose, back up, or health-check Neo4j.
3. THE CI workflow SHALL start no graph service and SHALL contain no graph-specific test lane.
4. THE standard development and server profiles SHALL install no Neo4j or `sbir-graph` package.
5. THE retirement SHALL not delete host graph directories, Docker volumes, or backup files.

### Requirement 3 — Preserve the authority boundary

**User story:** As a researcher, I want relationship data to retain a declared authoritative
form, so that removal of a read projection does not change a claim or analytical result.

#### Acceptance Criteria

1. THE architecture documentation SHALL identify governed Parquet and DuckDB records as
   authoritative.
2. THE retirement SHALL not change frozen SBA study, release, or review bytes.
3. THE existing assertion snapshot contract SHALL remain a content-addressed Parquet contract.
4. A future graph SHALL require a named consumer, a separate specification, and a rebuildable
   projection contract.
5. THE moving repository SHALL validate the released SBA packet against the exact annotated
   `v0.18.0` commit and tree. It SHALL reject any path or byte difference between the current
   released-study subtree and the tagged subtree. Any immutable release-checksum erratum SHALL be
   named by exact path and expected/observed hashes and rejected when it is absent or changes.

### Requirement 4 — Make retirement enforceable

**User story:** As a maintainer, I want active Neo4j references to fail CI, so that the retired
service does not return by accident.

#### Acceptance Criteria

1. A CI guard SHALL reject active imports, dependencies, services, credentials, ports, and
   commands for Neo4j or `sbir-graph`.
2. THE guard SHALL allow exact retirement records, immutable release material, and archived
   history.
3. Guard tests SHALL cover Python imports, package dependencies, Compose services, workflows,
   live documentation, and allowed archive records.

### Requirement 5 — Define a recoverable cutover

**User story:** As an operator, I want an explicit offboarding procedure, so that retirement
does not destroy historical graph data.

#### Acceptance Criteria

1. THE runbook SHALL require a final verified dump before the retirement deployment.
2. THE runbook SHALL identify `v0.18.0` as the last supported graph implementation.
3. THE runbook SHALL require an operator to record the dump path, byte count, and SHA-256.
4. THE deployment step SHALL remove the old container as an orphan without deleting data.
5. THE repository SHALL keep no current command that starts or mutates Neo4j.

## Dependencies

- PR #788 merged — SATISFIED
- Annotated `v0.18.0` tag — SATISFIED
- Later-HEAD freeze handling for the SBA study's historical `uv.lock` — SATISFIED
- Governed Parquet and DuckDB outputs — EXISTS
