# Neo4j Retirement Design

## Decision

Remove Neo4j and `sbir-graph` from the supported repository and deployment stack. Keep governed
Parquet and DuckDB records as the analytical authority. Preserve historical graph code through
the annotated `v0.18.0` tag instead of copying it into an active source tree.

## Current flow

Several Dagster assets compute governed or exploratory tables and then write a second copy into
Neo4j. The graph package also contains migrations and fixed-hop queries. No active study or
operated output reads the graph as its required source. The service still adds credentials,
ports, volumes, startup waits, backups, and a dedicated CI lane.

## Resulting flow

```text
declared sources -> deterministic transforms -> Parquet/DuckDB tables -> studies and reports
                                             \-> content-addressed assertion snapshots
```

The resulting stack has no graph writer or graph reader. Existing table producers remain in
place. Graph-only projection assets and their checks are deleted.

## Code boundary

Delete the `packages/sbir-graph` workspace package. Delete graph-only analytics modules. Remove
graph sections from mixed analytics modules without changing their upstream table computation.
Remove the Neo4j configuration schema because no supported runtime reads it.

The retirement does not preserve `detect_award_progressions`. That heuristic has no named
research consumer. The existing `phase_ii_iii_pairs.parquet` product is not declared as its
replacement. A future continuity question must define its grain and rules in a separate spec.

## Deployment boundary

Remove the Neo4j service from both Compose files. Remove graph waits and graph routes from server
and container scripts. Keep the application-data directory outside this change. Before the first
retirement deployment, the operator creates and verifies one final dump with the `v0.18.0`
tooling. The deployment uses Compose orphan removal. It does not remove volumes or host files.

## Release boundary

PR #788 freezes the root `uv.lock` as part of the validated SBA study. The retirement must change
that lock. The moving repository therefore cannot keep validating the historical environment from
the live root path after `v0.18.0`.

The retirement registers the study's release tag and expected Git tree outside the packet.
Generic study validation extracts that immutable tree and validates the manifest, release
checksum inventory, and generated artifacts there. The immutable tag has one recorded checksum
erratum: its squash merge retained the Jev Make targets already on `main`, while the detached
inventory retained the reviewed branch's `Makefile` hash. The registry names that path and both
hashes exactly; every unrecorded or no-longer-observed mismatch fails validation. Active studies
continue to validate against the current checkout. The public renderer and reproduction command
remain tag-only tools.
Existing SBA study, release, and review files stay unchanged.

Generic validation also compares the current released-study subtree with the extracted tagged
subtree. A missing, added, or changed path fails validation. Repository files outside that study
subtree may continue to move.

The PR stays draft until PR #788 is merged and an annotated `v0.18.0` tag exists. The tag is the
citable checkout and the last supported graph implementation.

## Guard boundary

The retirement guard scans tracked active code, configuration, automation, and current
documentation. It rejects these reference families:

- `neo4j` and `sbir_graph` imports or dependencies;
- `packages/sbir-graph` and graph-only script paths;
- `NEO4J_*` and `SKIP_NEO4J_LOADING` environment keys;
- Bolt, `cypher-shell`, and retired ports 7474, 7687, and 17687.

The allowlist is path-exact. It covers the guard, its tests, this spec, the retirement ADR and
tombstone, release archives, historical archives, the changelog, and immutable study records.

## Verification

1. Validate both Compose files and confirm their service lists contain no Neo4j service.
2. Validate Dagster definitions with Neo4j and `sbir_graph` unavailable.
3. Run the active-reference guard and its mutation tests.
4. Run focused configuration, asset, server, and CI-contract tests.
5. Run all unit-test shards and service-free integration tests.
6. Run Ruff, formatting, MyPy, `make lint-boundaries`, and `make docs-check`.
7. Build the server image and validate its Dagster definitions.
8. Confirm no existing SBA study, release, or review file changed.

## Consequences

The stack loses interactive graph traversal and the old fixed-hop Cypher query surface. No active
research product depends on either surface. The supported install and deployment become smaller.
Historical graph recovery remains possible from `v0.18.0` and the final operator dump.
