# Implementation Plan

## Task Overview

Phase 2: unify the legacy `:Company` node onto `:Organization`, matched by `uei`.
Stacks on Phase 1 (PR #379) — reuses `batch_set_existing_node_properties`. Ordered
so the graph is never left broken: inventory → writers → readers → migration →
verification → docs.

## Status

Implemented. Phase 1 (PR #379) merged; both writers now retarget to
`:Organization{uei}` via `batch_set_existing_node_properties`, the legacy
`:Company` constraint/indexes are dropped, migration `007` merges any existing
`:Company` nodes, readers/tests/docs are updated.

## Tasks

### 1. Inventory `:Company` properties → verify: documented, no collisions
- [x] Enumerate every property written onto `:Company` by `categorization.py` and
      `sec_edgar.py`; confirm none collide with meaningful `:Organization` props
      (categorization: `classification`, `categorization_confidence`, …; SEC:
      `sec_cik`, `sec_ticker`, `sec_is_publicly_traded`, …).
- [x] Confirm (grep) no relationship type has a `:Company` endpoint (so the
      migration needs no edge re-homing).
- **Verify:** inventory table in the PR; grep-backed.

### 2. Retarget `categorization.py` → verify: writes to Organization, no :Company
- [x] Replace the `:Company{uei}` upsert with
      `batch_set_existing_node_properties(label="Organization", key_property="uei")`.
      Orphans log + skip. Remove the `:Company` constraint/index from its helpers.
- **Verify:** unit test asserts categorization props land on `:Organization{uei}`
      and zero `:Company` nodes are written.

### 3. Retarget `sec_edgar.py` → verify: writes to Organization
- [x] Same retarget to `:Organization{uei}`. Decide + implement whether `sec_cik`/
      `sec_ticker` indexes move to `:Organization` (likely yes).
- **Verify:** unit test asserts SEC props land on `:Organization{uei}`; no `:Company`.

### 4. Drop leftover `:Company` constraint in `cet.py`/`client.py` → verify: removed
- [x] Remove the `:Company company_id` constraint (cet.py:77) and any `:Company`
      index from `client.py`'s deprecated helpers.
- **Verify:** integration test `TestNeo4jConstraintsAndIndexes` updated (no
      `:Company` constraint asserted) — mirror the Phase 1 fix.

### 5. Update readers in lockstep → verify: zero `:Company` in live code
- [x] `run_neo4j_smoke_checks.py`, `reset_neo4j_sbir.py`, `apply_schema.py`,
      `validate_patent_etl_deployment.py`: `:Company` → `:Organization` (or drop the
      empty `:Company` cleanup blocks).
- **Verify:** `grep -rn ':Company' packages/ sbir_etl/ scripts/` returns only the
      migration + tests.

### 6. Migration `007_unify_company_into_organization.py` → verify: dry-run on seed
- [x] `upgrade()`: batched `MATCH (c:Company) MATCH (o:Organization {uei:c.uei})
      SET o += properties(c) DETACH DELETE c`; orphans logged + left. Drop legacy
      `:Company` constraint + indexes (create `:Organization` SEC indexes if kept).
      Idempotent. `downgrade()`: recreate legacy schema; document partial.
- **Verify:** seed `:Company` + `:Organization` sharing a `uei`; run `upgrade()`;
      props merged, `:Company` gone, orphan left; run twice (idempotent).

### 7. Post-migration verification → verify: counts
- [x] One Cypher check: `count(:Company)` == orphan count; sampled `:Organization`
      carries `classification` / `sec_*`.
- **Verify:** passes on the seeded graph.

### 8. Update schema docs → verify: docs match
- [x] `docs/schemas/neo4j.md`: drop `:Company` from the legacy-labels note (only
      `:Contract`/`:PatentEntity` remain). `organization-schema.md`: note
      categorization + SEC props now live on `:Organization`.
- **Verify:** no doc claim that `:Company` is written.

### 9. PR + expectations → verify: reviewer-ready
- [x] Note: stacks on #379; `:Contract`/`:PatentEntity` still deferred. Back-up +
      dry-run note for the `DETACH DELETE` migration.

## Out of Scope

- `:Contract` writer (M1). `:PatentEntity` constraint cleanup (after confirming no
  readers). Standing validation asset-check.
