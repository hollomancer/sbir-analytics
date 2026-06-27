# Design Document

## Overview

Phase 2 unifies the legacy `:Company` node onto `:Organization`, matched by the
indexed `uei` property. It is mechanically the same as Phase 1's `:Award` →
`:FinancialTransaction` retarget, and **simpler**: `:Company` holds enrichment
properties only (no relationships), so there are no edges to re-home — just merge
properties and delete. It reuses Phase 1's MATCH-and-SET primitive.

## Current State (verified)

| Concern | Writer / Reader | Label | Key |
|---------|-----------------|-------|-----|
| Firm node (authoritative) | `sbir_neo4j_loading.py` | `:Organization` | `organization_id` (+ indexed `uei`, `duns` props) |
| Business categorization | `loaders/neo4j/categorization.py` (~L106-220) | `:Company` | `uei` (rows w/o uei skipped) |
| SEC EDGAR enrichment | `loaders/neo4j/sec_edgar.py` (~L76-160) | `:Company` | `uei` (rows w/o uei skipped) |
| CET company enrichment | `loaders/neo4j/cet.py` (~L160-230) | **`:Organization`** (already unified) | `uei` |
| Legacy `:Company` constraint/index | `categorization.py:92-98`, `sec_edgar.py:68-72`, `cet.py:77`, `client.py` | `:Company` | `company_id` (constraint), `classification`, `sec_cik`, `sec_ticker`, … |
| Readers | 4 scripts (smoke/reset/apply_schema/validate) | `:Company` | — |

No relationship type has a `:Company` endpoint (`OWNS`/`SPECIALIZES_IN`/`ACHIEVED`
already use `:Organization`). `:Company` is a property-only enrichment node.

## Approach

### 1. Retarget the two writers (reuse Phase 1's primitive)

- `categorization.py`: replace its `:Company` `MERGE`/upsert with
  `client.batch_set_existing_node_properties(label="Organization",
  key_property="uei", nodes=...)`. Orphans (uei absent from `:Organization`) log +
  skip. Remove the `:Company` constraint/index from its `create_constraints`/
  `create_indexes`.
- `sec_edgar.py`: same retarget to `:Organization{uei}`; remove its `:Company`
  index list. Note `sec_cik`/`sec_ticker`/`sec_is_publicly_traded` indexes move to
  `:Organization` if we want them indexed there — decide in tasks (likely yes, since
  SEC lookups now hit `:Organization`).

**MATCH-not-MERGE** (same rule as Phase 1): `uei` is a non-key property of
`:Organization` (key is `organization_id`); MERGE-on-`uei` would mint duplicates.
The `batch_set_existing_node_properties` primitive already MATCHes only.

### 2. Update readers in lockstep

The 4 scripts that MATCH `:Company` → `:Organization`. Where a script counts or
deletes `:Company` (reset/smoke), point it at `:Organization` (or drop the now-empty
`:Company` cleanup). `apply_schema.py` / `validate_patent_etl_deployment.py`: update
label references. No production query module reads `:Company`, so blast radius is
scripts only.

### 3. Migration `007_unify_company_into_organization.py`

Subclass `migrations.base.Migration` (pattern from 006). `upgrade()`:
1. Report `:Company` orphans (no `:Organization{uei}`); leave in place.
2. Batched: `MATCH (c:Company) MATCH (o:Organization {uei:c.uei}) WITH c,o LIMIT $n
   SET o += properties(c) DETACH DELETE c` (no edges to re-home — simpler than 006).
3. Drop legacy `:Company` constraint (`company_id`) and the categorization/SEC
   indexes (`classification`, `categorization_confidence`, `sec_cik`, `sec_ticker`,
   `sec_is_publicly_traded`). If we keep SEC lookups on `:Organization`, create the
   equivalent `:Organization` indexes here.
- **Property-collision check (design step):** `:Company` and `:Organization` share
  no property names that would clobber meaningful data (categorization/SEC props are
  distinct namespaces: `classification`, `sec_*`). Confirm during task 1 inventory;
  exclude any `__hash`/internal flags from the copy.

`downgrade()`: recreate the `:Company` constraint/indexes; document that the merge
is not perfectly reversible (restore from backup for a true rollback).

### 4. Verification

One Cypher check: `count(:Company)` == orphan count (ideally 0); a sampled
`:Organization` carries the expected `classification` / `sec_*` props.

## Files Touched

- `loaders/neo4j/categorization.py`, `loaders/neo4j/sec_edgar.py` — retarget writers.
- `loaders/neo4j/cet.py`, `client.py` — drop leftover `:Company` constraint/index.
- `migrations/versions/007_unify_company_into_organization.py` — new.
- 4 reader scripts; tests; `docs/schemas/neo4j.md` (drop `:Company` from legacy note),
  `docs/schemas/organization-schema.md` (note categorization/SEC props now here).

## Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Duplicate `:Organization` from MERGE-on-`uei` | High | MATCH-on-`uei` only (Phase 1 primitive); never MERGE the node |
| Reader left matching `:Company` | Med | Update all 4 scripts; `grep ':Company'` to zero in live code |
| Orphan `:Company` deleted | Med | Log + leave unmatched `:Company` (no blind delete) |
| Property name collision on merge | Low | Inventory in task 1; distinct namespaces; exclude `__`-prefixed |
| Coverage drop (categorization for a firm not yet an `:Organization`) | Low | Same as Phase 1 award reasoning — categorization is keyed on SBIR-recipient UEIs, which the SBIR loader writes as `:Organization`; orphans logged |
| Depends on PR #379 (Phase 1 primitive) | — | Stack on `claude/unify-graph-node-labels`; rebase onto main once #379 merges |

## Deferred

- `:Contract` writer (M1 feature). `:PatentEntity` constraint cleanup (after
  confirming no readers). After Phase 2, no property-only legacy node remains.
