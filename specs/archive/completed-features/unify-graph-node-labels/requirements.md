# Requirements — Unify :Award onto :FinancialTransaction (Phase 1)

> **Status:** Implemented — PR #379 merged.
> Phase 1 of graph label unification. Supports inventory question **E2** (graph schema correctness) in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** E2 — graph label unification (Phase 1: :Award → :FinancialTransaction)
**Answers for:** pipeline engineers
**Complexity tier:** Foundational infrastructure (completed)

---

## Done when

> A pipeline engineer can state: "Zero `:Award` nodes remain in the graph. `APPLICABLE_TO` and `GENERATED_FROM` edges land on `:FinancialTransaction`. `pathway_queries.py` returns equivalent results against `:FinancialTransaction` as it previously did against `:Award`. Migration `006_*` is idempotent with a working `downgrade()`."

---

## Introduction

The Neo4j graph currently carries a **dual node-label model** for SBIR awards. The
authoritative SBIR loader (`packages/sbir-analytics/.../sbir_neo4j_loading.py`,
via `sbir-graph`'s `client.py`) writes `:FinancialTransaction` nodes (key
`transaction_id`, also storing `award_id`). Several enrichment loaders in the
`sbir-graph` package instead write/target a separate legacy `:Award` node
(key `award_id`):

- the CET loader (`cet.py`) upserts CET enrichment onto `:Award` and creates
  `(:Award)-[:APPLICABLE_TO]->(:CETArea)`;
- the patent loader (`patents.py`) creates `(:Patent)-[:GENERATED_FROM]->(:Award)`.

Because `:Award` and `:FinancialTransaction` are **disjoint node sets for the same
award**, every cross-model query — "what CET areas apply to this transaction",
"what patents were generated from this award" — silently traverses nothing. This
is a correctness bug on the critical path for the technology-transition and
CET-alignment analyses.

This spec covers **Phase 1: unify `:Award` onto `:FinancialTransaction`**. It is
deliberately scoped to the `:Award` split, which has a clean join key
(`FinancialTransaction.award_id == Award.award_id`) and a concrete, verifiable
failure mode. Other legacy labels are explicitly deferred (see Non-Goals).

## Glossary

- **Unified label**: `:FinancialTransaction` / `:Organization` / `:Individual` —
  the labels the authoritative SBIR loader writes.
- **Legacy label**: `:Award` (and, out of scope here, `:Company` / `:Contract` /
  `:PatentEntity`) — written/targeted by `sbir-graph` enrichment loaders.
- **`:FinancialTransaction`**: canonical award/contract node; key `transaction_id`
  (format `txn_award_<award_id>`); carries `award_id` as a property.
- **`:Award`**: legacy award node, key `award_id`; target of CET enrichment and
  patent `GENERATED_FROM`.
- **Label-retarget**: changing a loader so its existing upsert/relationship writes
  to `:FinancialTransaction` instead of `:Award`, without otherwise changing its
  ingestion semantics.
- **Reader**: code that issues Cypher `MATCH` against a label (e.g. the public
  `pathway_queries.py` API).

## Requirements

### Requirement 1 — CET enrichment and APPLICABLE_TO target FinancialTransaction

CET classification must attach to the same node the SBIR graph uses for an award.

- WHEN the CET loader upserts award-level CET enrichment, it SHALL set those
  properties on the `:FinancialTransaction` node whose `award_id` matches, not on a
  separate `:Award` node.
- WHEN the CET loader creates `APPLICABLE_TO`, the edge SHALL originate from the
  `:FinancialTransaction` for that award: `(:FinancialTransaction)-[:APPLICABLE_TO]->(:CETArea)`.
- The loader SHALL NOT create duplicate `:FinancialTransaction` nodes (see R3).

### Requirement 2 — Patent GENERATED_FROM targets FinancialTransaction

- WHEN the patent loader links a patent to its SBIR award, it SHALL create
  `(:Patent)-[:GENERATED_FROM]->(:FinancialTransaction)` matched on `award_id`,
  not `(:Patent)-[:GENERATED_FROM]->(:Award)`.

### Requirement 3 — No duplicate FinancialTransaction nodes

`:FinancialTransaction`'s real key is `transaction_id`; CET/patent rows only carry
`award_id`. A naive `MERGE` on `award_id` would create a second FT node.

- WHEN a loader resolves an award by `award_id`, it SHALL `MATCH` on the
  `award_id` property (not `MERGE` on it) for enrichment, and SHALL guard
  relationship creation so it never mints a duplicate `:FinancialTransaction`.
- WHEN no `:FinancialTransaction` exists for an `award_id` (orphan), the loader's
  behaviour SHALL be explicit and documented (skip + log, matching today's
  effective coverage), and SHALL NOT silently drop enrichment without a log line.

### Requirement 4 — Readers updated in lockstep

- WHEN `:Award` is unified, the public query API `pathway_queries.py` and any other
  reader of `:Award` SHALL be updated in the same change so no reader matches a
  label that is no longer written.
- The change SHALL NOT introduce a new silent-zero: queries that worked before
  (against `:Award`) SHALL return equivalent results against `:FinancialTransaction`.

### Requirement 5 — One-time migration of existing graph data

- The repo SHALL add a numbered migration (`006_*`) that, for every existing
  `:Award` node, re-homes its CET properties and its `APPLICABLE_TO` /
  `GENERATED_FROM` relationships onto the matching `:FinancialTransaction`
  (by `award_id`), then removes the orphaned `:Award` node and its legacy
  constraint/index.
- The migration SHALL NOT lose data: any property present on `:Award` but absent
  on the corresponding `:FinancialTransaction` SHALL be copied over (property
  inventory is a design step).
- The migration SHALL provide a `downgrade()` and SHALL be safe to run against a
  graph that has already been partially migrated (idempotent).

### Requirement 6 — Verification

- AFTER the migration, a single verification check SHALL confirm: zero `:Award`
  nodes remain, `APPLICABLE_TO` / `GENERATED_FROM` edge counts are preserved, and
  those edges now land on `:FinancialTransaction`. A one-off Cypher count query is
  sufficient; a standing asset-check is out of scope.

## Non-Goals (explicitly deferred)

- **`:Company` → `:Organization` unification.** No single clean join key
  (`uei`/`duns`, often null); this is an entity-resolution problem that overlaps
  the existing enrichment/dedup pipeline. Deferred to a separate spec.
- **`:Contract`.** It has no writer — it is a *missing writer* (follow-on-contract
  loading), not a relabel. The patent→transition→contract pathway will remain
  partial until that writer exists; this spec does not fix it.
- **`:PatentEntity`.** Still actively used as a relationship endpoint for
  individual assignors/assignees. Out of scope; do not remove its nodes. (The
  unused standalone constraint/index may be dropped in a later trivial PR after
  confirming nothing reads bare `:PatentEntity`.)
- **MERGE→MATCH conversion + Dagster job-ordering enforcement.** Rejected: it
  trades a labeling bug for a worse orphan-drop/coverage bug. See design.

## Acceptance Criteria (summary)

1. CET enrichment + `APPLICABLE_TO` and patent `GENERATED_FROM` land on
   `:FinancialTransaction`; no `:Award` nodes are written by any loader.
2. No duplicate `:FinancialTransaction` nodes are created (MATCH-on-`award_id`).
3. `pathway_queries.py` and all `:Award` readers updated; no new silent-zeros.
4. Migration `006_*` re-homes existing data with no property loss and a working
   `downgrade()`.
5. Post-migration verification passes (no `:Award`, edge counts preserved).
