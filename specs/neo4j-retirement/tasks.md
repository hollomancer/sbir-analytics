# Neo4j Retirement Tasks

- [x] 0. Close the release prerequisites
  - Merge PR #788 under separate owner authorization.
  - Create and verify annotated tag `v0.18.0` under separate owner authorization.
  - Register tag-aware validation without changing frozen SBA packet bytes.
  - Verify: the retirement PR remains draft until all three conditions hold.
  - Requirements: 3, 5

- [x] 1. Remove the graph package and analytical projections
  - Delete `packages/sbir-graph` and graph-only scripts.
  - Delete graph-only Dagster assets and checks.
  - Remove graph sections from mixed assets and jobs.
  - Preserve upstream table producers and assertion snapshots.
  - Verify: Dagster definitions load with graph modules blocked.
  - Requirements: 1, 3

- [x] 2. Remove configuration and dependencies
  - Delete the Neo4j configuration models and defaults.
  - Remove `sbir-graph`, `neo4j`, and Neo4j testcontainer dependencies.
  - Update synchronized release metadata for version `0.19.0`.
  - Regenerate the lock.
  - Verify: lock and clean-profile import checks pass.
  - Requirements: 1, 2

- [x] 3. Remove deployment and CI services
  - Remove Neo4j from Compose, Docker, server scripts, GitHub Actions, and Make targets.
  - Retain generic application and Dagster health behavior.
  - Delete graph-only tests and update surviving server tests.
  - Verify: Compose, workflow, server, and service-free integration checks pass.
  - Requirements: 2, 5

- [x] 4. Add retirement controls and records
  - Add the active-reference guard and mutation tests.
  - Add ADR-006 and the retirement tombstone.
  - Update current architecture, setup, deployment, and status documents.
  - Add the final-backup and orphan-removal cutover steps.
  - Verify: `make lint-boundaries` and `make docs-check` pass.
  - Requirements: 3, 4, 5

- [x] 5. Complete release verification
  - Run the unit shards, service-free integration tests, Ruff, formatting, and MyPy.
  - Build the server image and validate Dagster definitions.
  - Confirm no frozen SBA study, release, or review file changed.
  - Run the test-fixer and quality-sweep reviews.
  - Verify: all required checks pass.
  - Requirements: 1, 2, 3, 4, 5
