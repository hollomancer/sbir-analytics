# Tasks: Make `RESULTED_IN` resolve (CONTRACT nodes)

> **Revised after scope-guard (TRIM).** Collapsed from 7 tasks (transformer + asset +
> edges + sequencing) to the inline-MERGE change. Original task list preserved in git
> history.

## Status

Implemented (inline approach). The `RESULTED_IN` writer now creates the CONTRACT
node inline; unit tests + docs updated. **Value remains gated on seed data** — the
transition contract input is empty today (`data/processed/contracts_sample.parquet`
absent), so the pathway returns 0 rows until contract sample data is seeded (separate
effort).

## Tasks (inline approach)

### 1. Inline-MERGE the CONTRACT node in the RESULTED_IN writer → verify: unit test
- [x] In `create_resulted_in_relationships` (`loaders/neo4j/transitions.py:208-267`),
      change the Cypher to `MERGE (ft:FinancialTransaction {transaction_id:
      "txn_contract_" + t.contract_id}) ON CREATE SET ft.transaction_type="CONTRACT",
      ft.contract_id=t.contract_id` before the `MERGE (trans)-[:RESULTED_IN]->(ft)`.
      MERGE on the PK only (never `contract_id`). Update the docstring.
- **Verify:** unit test asserts the writer MERGEs the CONTRACT node keyed on
      `transaction_id` (`txn_contract_…`) carrying `contract_id` + `transaction_type`,
      then the edge; idempotent on re-run.

### 2. Docs → verify: caveat replaced
- [x] `docs/schemas/neo4j.md:53-57`: replace the "contract ingestion not built /
      pathways stay empty" caveat — CONTRACT nodes are created by the `RESULTED_IN`
      writer when a transition carries `contract_id`; pathway returns rows once contract
      sample data is seeded. Note the seed-data precondition.
- **Verify:** no doc claims a separate writer is missing; precondition is stated.

### 3. PR + expectations → verify: reviewer-ready
- [x] State plainly: structural fix; pathway returns 0 until `contracts_sample.parquet`
      is seeded; rich nodes / RECIPIENT_OF / FUNDED_BY / full ingestion deferred; no
      migration; the amount-validator does not fire on this path.

## Deferred (do not build without a named consumer)

- Separate `loaded_contracts` asset + `_contract_transaction_props` transformer (rich
  node props).
- RECIPIENT_OF / FUNDED_BY contract edges (→ `leverage-ratio-analysis`).
- Full USAspending contract ingestion; seeding `contracts_sample.parquet`; FPDS-dump
  vs DuckDB source reconciliation.
