# Implementation Plan

## Task Overview

Phase 1: unify the legacy `:Award` node onto `:FinancialTransaction`. Tasks are
ordered so the graph is never left in a broken state: inventory → loaders →
readers → migration → verification → docs. Each task lists how to verify it.

## Status

Phase 1 implemented (Tasks 1–8). Task 9 (PR) is handled at review time.

## Tasks

### 1. Inventory `:Award` properties and edges → verify: documented list
- [x] Enumerate every property written onto `:Award` (across `cet.py`, `patents.py`,
      migrations `001`/`004`) and every relationship type with an `:Award` endpoint.
- [x] Confirm which `:Award` properties are absent from `:FinancialTransaction` (so
      the migration copies them).
- **Verify:** a short inventory table committed in the PR description / design note;
      `grep`-backed, no guesses.

### 2. Confirm `FinancialTransaction(award_id)` index (already exists) → verify: index present
- [x] No new index needed — `:FinancialTransaction(award_id)` is already created as
      `financial_transaction_award_id` in `migrations/versions/001_initial_schema.py`.
      Just confirm the MATCH-on-`award_id` upserts use it.
- **Verify:** `SHOW INDEXES` lists `financial_transaction_award_id`; loader queries
      hit it (PROFILE shows NodeIndexSeek, not NodeByLabelScan).

### 3. Retarget CET loader to `:FinancialTransaction` → verify: unit tests + no `:Award` written
- [x] In `cet.py`, change the award CET upsert to `MATCH (ft:FinancialTransaction
      {award_id:$award_id}) SET ft += $props` (no node creation).
- [x] Change `APPLICABLE_TO` creation to resolve FT by `award_id` and `MERGE` only
      the edge: `(:FinancialTransaction)-[:APPLICABLE_TO]->(:CETArea)`.
- [x] Orphan handling: skip + log when no FT matches (R3).
- **Verify:** existing CET-loader unit tests updated and green; a test asserts the
      loader writes zero `:Award` nodes and creates `APPLICABLE_TO` off
      `:FinancialTransaction`.

### 4. Retarget patent `GENERATED_FROM` to `:FinancialTransaction` → verify: unit tests
- [x] In `patents.py`, change `GENERATED_FROM` to target the FT matched on
      `award_id`; `MERGE` only the edge, never the FT node.
- **Verify:** patent-loader unit test asserts `(:Patent)-[:GENERATED_FROM]->(:FinancialTransaction)`
      and no new FT/`:Award` nodes.

### 5. Update readers in lockstep → verify: zero `:Award` matches in live code
- [x] `pathway_queries.py`: `:Award` → `:FinancialTransaction` (public API).
- [x] Update `scripts/data/run_neo4j_smoke_checks.py`,
      `scripts/data/reset_neo4j_sbir.py`, `scripts/neo4j/apply_schema.py`,
      `scripts/validation/validate_patent_etl_deployment.py`,
      `sbir_etl/utils/enrichment/freshness.py`, and tests
      (`test_neo4j_client.py`, `test_query_builder.py`).
- **Verify:** `grep -rn ':Award' packages/ sbir_etl/ scripts/ tests/` returns only
      the migration file (and archived specs); pathway query tests green.

### 6. Write migration `006_unify_award_into_financial_transaction.py` → verify: dry-run on a seeded graph
- [x] Subclass `migrations.base.Migration`; `upgrade()` copies `:Award` props onto
      the matched FT, re-homes `APPLICABLE_TO` / `GENERATED_FROM`, `DETACH DELETE`s
      matched `:Award`, drops legacy `:Award` constraint + `award_date` /
      `award_topic_code` indexes. Batched + idempotent.
- [x] Orphan `:Award` (no FT match): log + leave (do not delete). 
- [x] `downgrade()`: recreate constraint/indexes; document that node-split is not
      perfectly reversible.
- **Verify:** seed a small graph with `:Award` + `:FinancialTransaction`, run
      `upgrade()`, confirm edges re-homed and `:Award` gone; run twice (idempotent).

### 7. Post-migration verification → verify: counts preserved
- [x] One Cypher check: `count(:Award)==0`; `APPLICABLE_TO` / `GENERATED_FROM`
      counts equal pre-migration; edges now land on `:FinancialTransaction`.
- **Verify:** the check passes on the seeded graph; capture before/after counts.

### 8. Update schema docs → verify: docs match the new graph
- [x] `docs/schemas/neo4j.md`: drop `:Award` from the legacy-labels note; move
      `APPLICABLE_TO` / `GENERATED_FROM` to standard `:FinancialTransaction` edges.
- [x] `docs/schemas/financial-transaction-schema.md`: fold `GENERATED_FROM` /
      `APPLICABLE_TO` back in as real FT relationships; remove the "separate `:Award`
      label" note.
- **Verify:** no remaining doc claim that `:Award` is written; links resolve.

### 9. PR + expectations → verify: reviewer-ready
- [ ] PR notes: scope is `:Award` only; `:Company`/`:Contract`/`:PatentEntity`
      deferred; the patent→transition→**contract** pathway stays partial until a
      Contract writer lands (M1).
- [ ] Back-up + dry-run note for operators before applying the migration to a live graph.

## Out of Scope (tracked elsewhere)

- `:Company` → `:Organization` (entity-resolution; separate spec).
- `:Contract` writer (M1 follow-on-contract loading).
- `:PatentEntity` constraint cleanup (trivial later PR, after confirming no readers).
- Standing validation asset-check (revisit only if M5 monitoring requires it).
