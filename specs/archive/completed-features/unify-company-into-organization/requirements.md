# Requirements — Unify :Company onto :Organization (Phase 2)

> **Status:** Not yet started. Stacks on Phase 1 (PR #379).
> Phase 2 of graph label unification. Supports inventory question **E2** (graph schema correctness) in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** E2 — graph label unification (Phase 2: :Company → :Organization)
**Answers for:** pipeline engineers
**Complexity tier:** Foundational infrastructure

---

## Done when

> A pipeline engineer can state: "`grep ':Company' packages/sbir-graph/` returns zero hits in live loader source (migrations and tests excepted). Categorization and SEC EDGAR enrichment properties appear on `:Organization{uei}` nodes. Migration `007` ran with no property loss; orphaned `:Company` nodes without a matching `:Organization` are logged and left in place."

---

## Introduction

Phase 2 of the graph label-unification work (Phase 1 unified `:Award` onto
`:FinancialTransaction`, PR #379). The authoritative SBIR loader writes
`:Organization` nodes (key `organization_id`, format `org_company_<id>`) that
**also store `uei` and `duns` as properties** and are indexed on `uei`
(`organization_uei`). Two enrichment loaders still write/enrich a separate legacy
`:Company` node:

- `categorization.py` upserts business-categorization properties onto `:Company`,
  keyed on `uei` (rows without a `uei` are skipped);
- `sec_edgar.py` enriches `:Company` with SEC EDGAR fields, also keyed on `uei`
  (rows without a `uei` are skipped).

Because `:Company` and `:Organization` are disjoint nodes for the same firm, the
categorization and SEC-EDGAR enrichment never appears on the `:Organization` nodes
the rest of the graph uses — a split-brain identical in shape to the `:Award` one.

**Key finding (de-risks this phase):** every `:Company` writer keys on `uei` and
skips rows without it, and `:Organization` carries an indexed `uei` property. So
this is a clean `:Company{uei}` → `MATCH :Organization{uei}` retarget — the same
mechanical pattern as Phase 1, **not** the entity-resolution problem originally
feared. `cet.py`'s company CET enrichment already targets `:Organization{uei}`;
only its leftover `:Company` constraint remains. `:Company` nodes hold enrichment
**properties only** — no relationships have a `:Company` endpoint — so there is
nothing to re-home, making this strictly simpler than Phase 1.

**Dependency:** the implementation reuses the `batch_set_existing_node_properties`
(MATCH-and-SET, never creates) primitive added in Phase 1, so it stacks on PR #379
(must merge first, or this branch rebases onto it).

## Glossary

- **`:Organization`**: canonical firm/agency/institution node; key `organization_id`
  (`org_company_<uei>` or `org_company_DUNS:<duns>`); stores `uei`/`duns`; indexed
  on `uei`.
- **`:Company`**: legacy firm node enriched by `categorization.py` / `sec_edgar.py`;
  keyed on `uei`.
- **Label-retarget**: change a loader's `:Company{uei}` upsert to a MATCH-and-SET on
  `:Organization{uei}`, without changing its ingestion semantics otherwise.

## Requirements

### Requirement 1 — Categorization enrichment targets Organization

- WHEN `categorization.py` writes business-categorization properties, it SHALL
  `MATCH (o:Organization {uei:$uei}) SET o += $props` (via
  `batch_set_existing_node_properties`), not MERGE/SET a separate `:Company` node.
- It SHALL NOT create `:Organization` nodes (no MERGE on `uei`, a non-key property);
  rows whose `uei` matches no `:Organization` are orphans → log + skip.

### Requirement 2 — SEC EDGAR enrichment targets Organization

- WHEN `sec_edgar.py` enriches with SEC fields, it SHALL MATCH-and-SET onto
  `:Organization {uei}`; same orphan handling as R1.

### Requirement 3 — No duplicate Organization nodes

- `:Organization`'s key is `organization_id`; the `:Company` writers only carry
  `uei`. Resolution SHALL be MATCH-on-`uei` (indexed), never MERGE-on-`uei`.

### Requirement 4 — Readers updated in lockstep

- WHEN `:Company` is unified, all readers SHALL be updated so none MATCHes a label
  that is no longer written: `scripts/data/run_neo4j_smoke_checks.py`,
  `scripts/data/reset_neo4j_sbir.py`, `scripts/neo4j/apply_schema.py`,
  `scripts/validation/validate_patent_etl_deployment.py`. (No production query
  module reads `:Company`.)

### Requirement 5 — One-time migration of existing graph data

- A numbered migration (`007_*`) SHALL, for each `:Company c`,
  `MATCH (o:Organization {uei:c.uei}) SET o += properties(c)`, then `DETACH DELETE c`.
  `:Company` orphans (no matching `:Organization`) SHALL be logged and LEFT IN PLACE.
- It SHALL drop the legacy `:Company` constraint and its indexes
  (`categorization.py`, `sec_edgar.py`, `cet.py`, `client.py` constraint/index lists).
- Idempotent, batched; `downgrade()` recreates the legacy schema and documents that
  the node-merge is not perfectly reversible.

### Requirement 6 — Verification

- AFTER the migration, a single Cypher check SHALL confirm zero `:Company` nodes
  remain (excluding logged orphans) and that the categorization/SEC properties now
  live on `:Organization`. No standing asset-check.

## Non-Goals (deferred)

- **`:Contract`** — a missing *writer* (follow-on-contract loading), not a relabel;
  M1 feature work.
- **`:PatentEntity`** — still live (individual assignors/assignees). Out of scope;
  only its unused constraint may be dropped later after confirming no readers.

## Acceptance Criteria

1. `categorization.py` + `sec_edgar.py` write enrichment onto `:Organization{uei}`;
   no loader writes `:Company`.
2. No duplicate `:Organization` nodes (MATCH-on-`uei`).
3. All `:Company` readers updated; `grep ':Company'` clean in live source (migration
   + tests excepted).
4. Migration `007` merges existing `:Company` data with no property loss; orphans
   preserved; working `downgrade()`.
5. Verification passes; CI green.
