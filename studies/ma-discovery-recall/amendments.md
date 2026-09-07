# M&A discovery recall — amendments

This note records measured-cut provenance for `studies/ma-discovery-recall`.
It does **not** replace the estimand, identity policy, C3 join, confidence
table, or the preregistered validation design in [design.md](design.md).
Those remain the frozen method at the design.md content hash in `study.yaml`.

Evidence-auditor 2026-09-02: **BLOCK** on `exploratory` → `validated`.
A post-run restatement of the cost/candidate envelope after the 200-pair
batch missed the recall floor is not a preregistered amendment.

## A1 — Measured 500-pair cut (exploratory record, 2026-09-01)

The frozen validation design still requires all three: recall ≥10 medium/high
C3 insert/promote pairs; medium-row FP ≤0.25 on ≤20 labels; search+LLM
≤$0.10/pair **and** `--max-candidates 200` **and** `--max-cost-usd 5`.
“A run that fails any of the three does not promote.”

What was actually run:

1. **200-pair first batch** (one query template per pair, Brave snippets,
   Grok via OpenRouter `x-ai/grok-4.6`): **9** C3 insert/promote medium/high
   pairs — recall floor **failed**.
2. **Enlarge to 500 pairs** on the same events file, same single template,
   appending to the snippet freeze, after that failure was known. That cut
   is recorded here as an exploratory measurement, not as a passed gate.

Observed on the 500-pair freeze (see `run-manifest.json`, `labels.jsonl`):

- 500 pairs, 1 query each; 745 frozen LLM replies.
- C3: 16 medium/high inserts + 1 medium promote = **17** pairs that did not
  already carry `discovery_confirmed`. Ten of those 17 already existed as
  EFTS medium at a later date (C3 inserts a second row outside ±30 days).
  One insert (GM/Opel 1929) is labeled **false**. One promote
  (Cellceutix/PolyMedix) is labeled **ambiguous** (snippet dropped on join).
- Medium queue: 16 rows, all labeled — **14 true / 1 false / 1 ambiguous**.
  FP = 1/15 = 6.7%.
- List Brave ($5/1k) + billed OpenRouter grok-4.6 ($2/$6 per 1M): about
  **$0.0178/pair**, **$8.89** for the 500-pair run (over the frozen $5 bound).

The frozen method also generates **four** query templates; this cut used one.

## A2 — Private snippet cut

Brave SERP snippets and Grok raw replies live under gitignored
`data/processed/ma_discovery/`. They are not redistributed. Content hashes
are in `run-manifest.json`. A machine without those files cannot rerun.

Inventory F2/A4 is not updated. Materialization into `capital_events` /
Neo4j is not authorized. `evidence_status` stays **exploratory**.

Narrative of this pilot: [pilot.md](pilot.md). Held-out confirmatory protocol
(hash before capture): [confirmatory-design.md](confirmatory-design.md).

## A3 — Held-out confirmatory cut (exploratory record, 2026-09-03)

`confirmatory-design.md` was hashed before Brave/LLM capture of pairs 501–1500.
The run used one query template, stop-until-dated, and strict recall.

Observed (see `confirmatory-run-manifest.json`):

- 1,000 pairs; 2,369 frozen Brave snippets; 1,831 LLM freeze rows.
- Strict medium/high C3 insert-or-promote: **8** (floor ≥10 **failed**).
- Cost ~$0.0126/pair (under $0.10). Precision labels were not started
  because recall already failed.
- LLM freeze is incomplete: 855 empty `raw_response` rows from index 976,
  covering 241 pairs with no non-empty reply. OpenRouter 402 cut the tail.
  Completing those pairs would be a live LLM call on the already-frozen
  snippets, not a new search cut and not a restated envelope.

A run that fails any confirmatory gate does not promote. Do not evaluate a
rewritten gate on this freeze. `evidence_status` stays **exploratory**.

## A4 — Confirmatory tail completed (exploratory record, 2026-09-07)

The held-out freeze was resumed on the same Brave snippets, same hashed
`confirmatory-design.md`, stop-until-dated, strict recall. Empty freeze
rows were retried; 402s were not written as freeze rows. LLM chats used
`max_tokens=2048`.

Observed (see `confirmatory-run-manifest.json`):

- Strict medium/high C3 insert-or-promote: **13** (floor ≥10 **met**).
- 140 discovered rows (84 low, 52 medium, 4 high). C3: 138 inserts, 2
  promotes.
- Compacted LLM freeze: 1,831 unique `(company, acquirer, source_url)`
  keys, 1,753 filled. 78 empty URL keys remain; every pair has a filled
  reply on another URL.
- Cost ~$0.0186/pair (Brave $5 + LLM ~$13.64, under $0.10).
- Precision labels **not started**. Review queue is the first 20 medium
  rows. The study does not promote until that review and the FP cap.

`evidence_status` stays **exploratory**. Do not edit
`docs/research-questions.md`.
