# Requirements: Make `RESULTED_IN` resolve (CONTRACT FinancialTransaction nodes)

> **Revised after scope-guard (verdict: TRIM).** Original draft proposed a
> transformer + new `loaded_contracts` asset + RECIPIENT_OF/FUNDED_BY edges +
> sequencing. Scope-guard (verified) showed that's over-built for the goal and that
> the contract input is empty in the repo today. This revision trims to the minimal
> structural fix and records the precondition.

## Problem

The graph models awards and contracts under one label, `:FinancialTransaction`
(`transaction_type` = `"AWARD"` | `"CONTRACT"`). Awards are written; **no writer
creates CONTRACT nodes.** The transition loader MATCHes them —
`MATCH (ft:FinancialTransaction {contract_id: t.contract_id, transaction_type: "CONTRACT"})`
(`loaders/neo4j/transitions.py:235`) — and `pathway_queries.py` traverses
`(:Transition)-[:RESULTED_IN]->(:FinancialTransaction{CONTRACT})`. Both resolve to
nothing, so `RESULTED_IN` is structurally always 0 (a missing-writer split-brain).

## Goal

Make `RESULTED_IN` **structurally resolvable**: when a transition carries a
`contract_id`, the CONTRACT node it points to exists, so the edge is created and the
award→transition→contract pathway can return rows.

## Precondition (important — verified)

The transition contract input is **empty in the current repo**:
`data/processed/contracts_sample.parquet` is absent, and `validated_contracts_sample`
(`assets/transition/contracts.py:212-214`) falls back to a `generated_empty`
DataFrame. The whole transition chain short-circuits on `.empty`. So this change
makes the pathway *resolvable*, but it returns **0 rows until real contract sample
data is seeded**. This is a structural fix, not a newly-live pathway. The PR must
not claim otherwise.

## Why this matters (north star)

`RESULTED_IN` is the graph edge for M1's "SBIR award → follow-on federal contract"
linkage — the exact relationship the research plan says doesn't exist today. Closing
the structural gap now is cheap and on-mission; lighting it up requires seed data
(separate work).

## Scope (trimmed)

**Recommended (inline):** in `create_resulted_in_relationships`
(`loaders/neo4j/transitions.py:208-267`, which already UNWINDs `transitions_df`
carrying `contract_id`), `MERGE` the CONTRACT node on its PK
(`transaction_id = "txn_contract_" + contract_id`), set `contract_id` +
`transaction_type="CONTRACT"` in the same query, then `MERGE` the `RESULTED_IN` edge.
~10 lines in one existing function. No transformer, no new asset, no sequencing.

## Non-goals (cut or deferred)

- **RECIPIENT_OF / FUNDED_BY edges — CUT.** Not needed for the goal (the edge and
  pathway only need the node + `contract_id`). The award `FUNDED_BY` path *mints*
  agency orgs (`sbir_neo4j_loading.py:806-868`); a MATCH-only contract version would
  be silently empty. Add later, in `leverage-ratio-analysis`, if a consumer needs them.
- **Rich node props (psc_code, competition_type, parent_uei, …) — CUT** until a query
  reads them. Load only the load-bearing fields (`transaction_id`, `contract_id`,
  `transaction_type`, and a human-readable `recipient_name`/`amount`/`agency` if cheap).
- **Separate `loaded_contracts` asset + transformer — DEFERRED**, justified only if a
  downstream query needs rich, independently-loaded contract nodes.
- **Full USAspending contract ingestion / source reconciliation / migration** — out of
  scope (schema already has the `transaction_id` constraint + `contract_id` index).
- **Amount filtering as a "validator requirement" — REMOVED:** the loader builds raw
  dicts and never instantiates the Pydantic model, so `validate_amount`
  (`financial_transaction.py:95`) never fires. Any amount rule is a chosen business
  rule, not a gate; the inline path doesn't need one.

## Acceptance criteria

1. On a **seeded** graph (awards + transitions whose rows carry `contract_id`s),
   running the transition relationships step creates
   `:FinancialTransaction{transaction_type:"CONTRACT"}` nodes carrying `contract_id`,
   and `RESULTED_IN > 0` (was structurally 0).
2. `TransitionPathwayQueries.award_to_transition_to_contract` returns non-empty on the
   seeded graph.
3. Node creation is idempotent (MERGE on `transaction_id`; re-run does not duplicate).
4. The PR states the empty-input precondition (pathway returns 0 until contract sample
   data is seeded).
5. Lint, types, and unit tests pass.
