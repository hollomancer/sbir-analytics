# Design Document

## Overview

Phase 1 unifies the legacy `:Award` node onto `:FinancialTransaction` so that CET
classifications and patent linkages attach to the same node the SBIR graph already
uses for an award. The approach is a **label-retarget on the existing upsert** —
not a MERGE→MATCH rewrite and not a new ingestion pipeline. The change is small in
surface (two loaders, one query module) plus a one-time data migration.

## Current State (verified)

| Concern | Writer / Reader | Label | Key |
|---------|-----------------|-------|-----|
| SBIR award node (authoritative) | `sbir_neo4j_loading.py` / `client.py` | `:FinancialTransaction` | `transaction_id` (+ `award_id` prop) |
| CET enrichment + `APPLICABLE_TO` | `loaders/neo4j/cet.py` (~L300–420) | `:Award` | `award_id` |
| Patent `GENERATED_FROM` | `loaders/neo4j/patents.py` (~L679–733) | `:Award` (target) | `award_id` |
| Pathway query API (reader) | `queries/pathway_queries.py` (L118–122, 170–171, 312) | `:Award`, `:Contract` | — |
| Transitions (already unified) | `loaders/neo4j/transitions.py` (L168, 235) | `:FinancialTransaction` | — |
| Legacy constraint/index | `client.py`, `migrations/001`, `migrations/004` | `:Award` | `award_id`, `award_date`, `award_topic_code` |

`:Award` and `:FinancialTransaction{award_id}` are disjoint nodes for the same
award. `transitions.py` already attaches to `:FinancialTransaction`, so the public
pathway query is *internally inconsistent today*: it matches `:Award` for one hop
and the transition layer lives on `:FinancialTransaction`.

## Approach

### 1. Label-retarget the loaders (keep upsert semantics)

`cet.py`'s award upsert is already parameterized (`label=`, `key_property=`). The
core change is to point CET enrichment and `APPLICABLE_TO` at
`:FinancialTransaction`, and patent `GENERATED_FROM` likewise.

**The make-or-break decision — MATCH on `award_id`, never MERGE on it.**
`:FinancialTransaction`'s key is `transaction_id`; CET/patent rows only carry
`award_id`. `MERGE (ft:FinancialTransaction {award_id: $award_id})` would create a
*second* FT node when the real one (keyed by `transaction_id`) already exists.
Therefore:

- **Enrichment (CET properties):** `MATCH (ft:FinancialTransaction {award_id:$award_id}) SET ft += $props`.
  No node creation. If no match, skip and log (orphan handling, R3).
- **Relationship endpoints (`APPLICABLE_TO`, `GENERATED_FROM`):** resolve the FT
  with `MATCH ... {award_id}` and `MERGE` only the *relationship*; never `MERGE`
  the FT node. Guard with `ON CREATE` only on the edge.

This preserves today's effective behaviour (an award present in CET/patent data but
absent from the financial graph contributes nothing) **without** introducing a
job-ordering contract. Rejected alternative: switching the loaders to hard `MATCH`
+ enforcing Dagster ordering — it adds an orphan-drop failure mode worse than the
labeling bug, for no benefit here.

### 2. Update readers in lockstep

`pathway_queries.py` must change `:Award` → `:FinancialTransaction` in the same PR
(public API; otherwise the silent-zero just moves). Audit and update the other
readers found in the surface map: `scripts/data/run_neo4j_smoke_checks.py`,
`scripts/data/reset_neo4j_sbir.py`, `scripts/neo4j/apply_schema.py`,
`scripts/validation/validate_patent_etl_deployment.py`,
`sbir_etl/utils/enrichment/freshness.py`, and the relevant unit tests
(`test_neo4j_client.py`, `test_query_builder.py`).

> **Expectation to set:** `pathway_queries.py` also matches `:Contract`, which has
> no writer. Award unification fixes the CET and patent→award hops; the full
> patent→transition→**contract** pathway stays empty until a Contract writer exists
> (deferred, M1). Call this out in the PR so reviewers don't expect the whole
> pathway to light up.

### 3. One-time migration (`006_unify_award_into_financial_transaction.py`)

Subclass `migrations.base.Migration` (same pattern as `004`/`005`).

**`upgrade()`** (idempotent, batched):
1. **Property inventory first** (design-time, not runtime): enumerate properties
   that exist on `:Award` to ensure none are dropped. Copy `:Award`-only props onto
   the matched FT.
2. For each `:Award a`: `MATCH (ft:FinancialTransaction {award_id: a.award_id})`,
   `SET ft += properties(a)` (excluding the redundant key), then re-home edges:
   - `(a)-[r:APPLICABLE_TO]->(c)` ⇒ `MERGE (ft)-[:APPLICABLE_TO]->(c)`
   - `(p)-[r:GENERATED_FROM]->(a)` ⇒ `MERGE (p)-[:GENERATED_FROM]->(ft)`
   - copy any other edge types discovered on `:Award` during inventory
3. `DETACH DELETE` the `:Award` node once its edges are re-homed.
4. Drop the legacy `:Award` constraint and the `award_date` / `award_topic_code`
   indexes.
- **Orphan `:Award`** (no matching FT): do **not** delete blindly — log and leave,
  or relabel to a quarantine label, so data isn't lost. Decide in tasks; default to
  log + leave so the migration is safe.

**`downgrade()`**: recreate the `:Award` constraint/indexes and (best-effort)
re-split — note that a perfect inverse may not be possible once nodes are merged;
document the limitation rather than pretend.

Back up the graph and dry-run before applying (the migration `DETACH DELETE`s).

### 4. Verification

A single Cypher check (run in the migration's validation step or a one-off script),
asserting:
- `MATCH (a:Award) RETURN count(a)` == 0
- `APPLICABLE_TO` / `GENERATED_FROM` counts equal pre-migration counts
- those edges now have a `:FinancialTransaction` endpoint

No standing asset-check framework (gold-plating for a one-time migration; revisit
only if M5 monitoring needs it).

## Files Touched

- `packages/sbir-graph/sbir_graph/loaders/neo4j/cet.py` — retarget award upsert +
  `APPLICABLE_TO` to `:FinancialTransaction` (MATCH-on-`award_id`).
- `packages/sbir-graph/sbir_graph/loaders/neo4j/patents.py` — `GENERATED_FROM`
  target → `:FinancialTransaction` (MATCH-on-`award_id`).
- `packages/sbir-graph/sbir_graph/queries/pathway_queries.py` — readers.
- `migrations/versions/006_unify_award_into_financial_transaction.py` — new.
- Readers/scripts/tests enumerated above.
- Docs: `docs/schemas/neo4j.md` (drop `:Award` from the legacy-labels note once
  done), `docs/schemas/financial-transaction-schema.md` (fold `GENERATED_FROM` /
  `APPLICABLE_TO` back in as real FT edges).

## Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Duplicate `:FinancialTransaction` from MERGE-on-`award_id` | High | MATCH-on-`award_id` for enrichment; MERGE only the edge, never the FT node |
| Reader left matching `:Award` → new silent-zero | High | Update all readers (esp. `pathway_queries.py`) in the same PR; grep `:Award` to zero in non-archived code |
| Property loss during merge | Medium | Property inventory before writing the migration; `SET ft += properties(a)` |
| `award_id` not unique / missing on some FT | Medium | Index `FinancialTransaction(award_id)`; handle multi/zero match explicitly |
| Orphan `:Award` deleted, data lost | Medium | Log + leave (or quarantine label); never blind `DETACH DELETE` of unmatched awards |
| Expectation that the whole pathway lights up | Low | Document the `:Contract`-writer gap in the PR |

## Deferred (separate specs)

- `:Company` → `:Organization` (entity-resolution; no clean key).
- `:Contract` writer (follow-on-contract loading; M1).
- `:PatentEntity` constraint cleanup (only after confirming no readers).
