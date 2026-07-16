# Phase III match benchmark: requirements

Status: **research protocol / draft implementation**. Parent issue: #448.
Foundation: PR #449 and issue #447. Production source lifecycle: issue #442.

## Objective

Determine whether award-to-contract text similarity adds useful information
after identity, time, firm, and acquisition-office constraints are applied.
The benchmark must not treat FPDS transactions as independent awards or treat
same-firm history as verified technical lineage.

## Functional requirements

1. Pull FPDS Element 10Q records through a bounded, parameterized command.
2. Parse the nested parent-IDV identifier and retain the order PIID separately.
3. Record query, source vintage, retrieval time, counts, hashes, parameters,
   field completeness, and feed-exhaustion status in a run manifest.
4. Apply the shared award-identity contract and collapse transaction rows to
   one explicitly selected representative row per award.
5. Create P1 same-firm **proxy positives** using only Phase II awards dated on
   or before the Phase III action.
6. Create N1 hard negatives from a different firm in the same contracting
   office using a deterministic seed.
7. Emit the pair table and explicit metrics, including lexical ROC-AUC and a
   bootstrapped confidence interval.
8. Run parser and pairing tests entirely from committed synthetic fixtures;
   tests must not contact FPDS.

## Non-goals

- production ingestion, scheduling, retries, or monitoring;
- claiming P1 pairs are verified derivative relationships;
- estimating the full “dark” universe of uncoded Phase III awards;
- adding a new embedding dependency before the lexical and structural baseline
  is reproducible.

## Acceptance gates

- a repeated order PIID under different parent IDVs cannot collide;
- modifications of one award yield one benchmark target;
- a post-target Phase II can never be selected;
- identical inputs and seed yield identical pairs and metrics;
- research and production boundaries are stated in code and documentation.
