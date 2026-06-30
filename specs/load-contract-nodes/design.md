# Design: Make `RESULTED_IN` resolve (CONTRACT FinancialTransaction nodes)

> **Revised after scope-guard (TRIM).** Default approach is now the inline MERGE in
> the existing relationship writer. The separate-asset/transformer design is kept
> below only as a documented alternative.

## Current state (verified)

| Piece | Status | Location |
|-------|--------|----------|
| `RESULTED_IN` writer — UNWINDs `transitions_df` (has `contract_id`), MATCHes CONTRACT node | exists, traverses nothing | `loaders/neo4j/transitions.py:208-267` (MATCH at `:235`) |
| `RESULTED_IN` read pathway | exists, empty | `queries/pathway_queries.py` |
| `transition_relationships_check` counts `RESULTED_IN` (always 0) | exists | `assets/transition/loading.py:324-327` |
| FT `transaction_id` constraint + `contract_id` index | exists | `migrations/versions/001_initial_schema.py:27,58` |
| Award writer builds **raw dicts**, never instantiates the model | exists (so validator never fires) | `assets/sbir_neo4j_loading.py:395,621` |
| Contract sample input | **empty** (`generated_empty` fallback; parquet absent) | `assets/transition/contracts.py:212-214` |
| CONTRACT node writer | **MISSING** | — |

`RESULTED_IN` MATCHes on the non-key `contract_id`; FT's PK is `transaction_id`. A
CONTRACT node must carry `contract_id` (the PIID) and a stable PK.

## Recommended approach — inline MERGE (default)

`create_resulted_in_relationships` already iterates `transitions_df` rows with
`transition_id`, `contract_id`, `confidence`. Change its Cypher to create the CONTRACT
node by its PK in the same statement, then MERGE the edge:

```cypher
UNWIND $transitions AS t
MATCH (trans:Transition {transition_id: t.transition_id})
MERGE (ft:FinancialTransaction {transaction_id: "txn_contract_" + t.contract_id})
  ON CREATE SET ft.transaction_type = "CONTRACT", ft.contract_id = t.contract_id
  ON MATCH  SET ft.transaction_type = coalesce(ft.transaction_type, "CONTRACT"),
                ft.contract_id      = t.contract_id
MERGE (trans)-[r:RESULTED_IN]->(ft)
SET r.confidence = t.confidence, r.creation_date = datetime()
RETURN count(r) AS created
```

- MERGE on the **PK** `transaction_id` (`txn_contract_<contract_id>`) — never on the
  non-key `contract_id` — so no duplicate FT nodes.
- If the sample DataFrame carries cheap human-readable columns (`recipient_name`,
  `obligated_amount`, agency), set them `ON CREATE` too; otherwise leave the node
  minimal (the goal needs only `contract_id` + `transaction_type`).
- **Eliminates** the transformer, the new asset, and all cross-asset sequencing (the
  node is guaranteed to exist before the edge — same statement).

**Trade-off:** nodes are sparse (no rich contract props) and are minted from transition
rows. That's acceptable because no query reads rich contract props today. If/when one
does, promote to the alternative below.

## Alternative — separate `loaded_contracts` asset (deferred; only if a consumer needs rich nodes)

A transformer `_contract_transaction_props(contract)` symmetric to
`_transaction_props(award)` + a `loaded_contracts` Dagster asset
(`batch_upsert_nodes`, key `transaction_id`), sequenced before
`loaded_transition_relationships`. Richer nodes + idempotent PK, but materially more
surface area (asset wiring, ordering) for node detail nothing currently consumes.
**Do not build unless a named query needs the extra props.** RECIPIENT_OF / FUNDED_BY
are out of scope either way (see requirements non-goals).

## Files touched (inline approach)

- `loaders/neo4j/transitions.py` — modify `create_resulted_in_relationships` Cypher
  (the ~10-line change above) + docstring.
- `docs/schemas/neo4j.md:53-57` — replace the "federal-contract node ingestion is not
  yet built / pathways stay empty" caveat with: CONTRACT nodes are now created by the
  `RESULTED_IN` writer when transitions carry a `contract_id`; pathway returns rows
  once contract sample data is seeded.
- Tests: extend `tests/unit/loaders/neo4j/test_transitions*.py` — assert the writer
  MERGEs a `FinancialTransaction{transaction_id:"txn_contract_…", transaction_type:
  "CONTRACT", contract_id:…}` and the `RESULTED_IN` edge; idempotent on re-run; MERGE
  is keyed on `transaction_id` (not `contract_id`).

## Risks & mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| Duplicate FT nodes | High | MERGE on PK `transaction_id`, never on `contract_id` |
| Minting a CONTRACT node that collides with an AWARD's `transaction_id` | Low | Disjoint prefixes: `txn_award_*` vs `txn_contract_*` |
| Sparse nodes mislead a future rich query | Low | Documented; promote to the separate-asset alternative when a consumer exists |
| Pathway still returns 0 | Expected | Input is empty today; criterion 1 tests on a seeded graph; precondition stated in the PR |
| `contract_id` PIID non-unique → coalesced nodes | Low | PK is `transaction_id`; same-PIID rows coalesce (acceptable; revisit if real) |

## Deferred

- Rich contract node props + separate loader/asset (until a consumer exists).
- RECIPIENT_OF / FUNDED_BY contract edges (→ `follow-on-multiplier-analysis` if needed).
- Full USAspending contract ingestion; seeding `contracts_sample.parquet`; source
  reconciliation.
