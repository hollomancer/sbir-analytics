---
Type: Decision
Maintainer: Conrad Hollomon
Last-Reviewed: 2026-09-23
Status: accepted
---

# ADR-006: Retire Neo4j and Keep Governed Tables Authoritative

## Context

Neo4j is a derived read projection in this repository. No active study, report, or operated
research product requires graph-native traversal. Current graph queries are fixed-hop joins and
aggregations. Governed Parquet and DuckDB tables already hold the analytical records.

The projection still adds a workspace package, client dependency, database service, credentials,
ports, volumes, startup waits, backup tooling, CI services, Dagster writers, and graph-specific
documentation. This surface can also imply that graph state is authoritative even though the
existing architecture says that a projection cannot strengthen a claim.

ADR-005 created a content-addressed Parquet contract for transition candidate assertions. That
contract is useful without a graph. Its proposed graph projection has no current consumer.

## Decision

Retire Neo4j and the `sbir-graph` package from the supported repository and deployment stack.

1. Governed Parquet and DuckDB records remain authoritative.
2. Content-addressed assertion snapshots remain Parquet artifacts.
3. Delete graph-only loaders, migrations, queries, Dagster assets, checks, scripts, and tests.
4. Remove the database service, dependency, credentials, ports, volumes, and CI lane.
5. Do not create replacement tables for graph-only heuristics without a named consumer.
6. Preserve the retired implementation in the annotated `v0.18.0` tag.
7. Require a verified final database dump before the first retirement deployment.
8. Do not delete host graph directories, Docker volumes, or historical dumps in this change.
9. Require a new specification and named consumer before adding any future graph projection.

The moving repository validates the released SBA study against the exact `v0.18.0` commit and
tree. The release registry records the tag's one immutable checksum erratum exactly: the tagged
`Makefile` includes the deterministic Jev targets already merged to `main`, while the detached
inventory contains the reviewed PR-branch hash. Validation permits only that path and hash pair,
requires the erratum to be observed, and fails on every other mismatch.

This decision supersedes the Neo4j projection and legacy-edge clauses in ADR-005. It does not
supersede ADR-005's assertion identity, typed absence, candidate semantics, Parquet snapshot, or
study-boundary decisions.

## Alternatives considered

### Keep Neo4j as an optional service

Rejected. Optional code still carries dependency, test, security, documentation, and semantic
maintenance costs. No active consumer justifies those costs.

### Keep the package and remove only the service

Rejected. This leaves a production-looking projection API with no supported runtime and invites
new code to depend on it.

### Replace Neo4j with another graph database

Rejected. The problem is the absence of a graph-native consumer, not the selected database.

### Copy the retired graph source into an archive directory

Rejected. The annotated tag preserves exact source and dependency history without leaving active
Python code in a path that tools or contributors can mistake for supported capability.

## Consequences

### Positive

- Development, CI, and deployment no longer require a graph database.
- New users see the actual authority boundary.
- The supported dependency and service surface is smaller.
- Analytical tables and study contracts remain independent of a mutable projection.

### Negative

- Interactive graph traversal and the old Cypher query surface are no longer supported.
- An operator who needs historical graph state must use the `v0.18.0` tooling and a preserved
  dump.

### Neutral

- No frozen study input, estimand, result, or permitted claim changes.
- Graph-only heuristics with no named consumer are removed without replacement.
- Existing host graph data remains in place until an operator makes a separate deletion decision.

## Implementation notes

Follow [the retirement cutover](../deployment/neo4j-retirement-cutover.md) before the first
deployment. See the [retirement tombstone](../../archive/neo4j/README.md) for old paths and
recovery boundaries.
