# Phase III match benchmark: design

## Boundary

The implementation lives under `scripts/phase3_benchmark/`. It is an
auditable research harness, not a reusable FPDS adapter. Once the query and
source-lifecycle behavior are stable, issue #442 can promote that boundary
behind an API without importing benchmark policy into production ingestion.

## Data flow

```text
bounded FPDS ATOM pull
  -> XML parser + run manifest
  -> transaction rows
  -> award identity + latest-transaction representative (PR #449)
  -> as-of same-firm P1 proxy pairs
  -> same-office/different-firm N1 pairs
  -> deterministic lexical score + AUC/CI
```

The raw page hash and manifest make two runs comparable even when the public
feed changes. Cached pages are optional and supplied by an explicit path.

## Identity and grain

An order PIID such as `0001` is not globally unique. A complete precomputed
award key is preferred; otherwise the benchmark requires awarding agency,
nested parent-IDV PIID, and order PIID. `contract_id` is never promoted to a
unique key by assumption. The shared collapse helper chooses the latest dated
transaction and does not aggregate financial amounts.

## Labels and time

P1 means only “the coded Phase III firm also had an eligible earlier Phase II.”
It is useful as a noisy proxy positive, but it does not prove derivation. N1
holds office context constant while changing the firm. The as-of join rejects
future Phase II awards; a year-only award is treated as available at year end.

## Metrics

The first baseline is token-set Jaccard similarity. ROC-AUC uses average ranks
for ties and a seeded nonparametric bootstrap for its interval. Embeddings are
deferred until this baseline can be reproduced and until they can use the
repository's existing model boundary without adding an ad hoc dependency.

## Failure policy

Missing identity components, missing target dates, missing required columns,
or one-class metric inputs fail loudly. A bounded pull that does not exhaust
the feed is valid research input only when its manifest says it is incomplete.
