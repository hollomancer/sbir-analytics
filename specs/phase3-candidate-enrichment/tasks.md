# Phase III Candidate-Text Enrichment — Tasks

> Sequenced so the cheap coverage gate (T1) runs before any assembler is built —
> if the enrichment sources are as empty as the FPDS descriptions, stop and say so.

## T1 — Source-coverage inventory (the gate)
Measure, per enrichment source, what fraction of the 45 T6-scored contracts (and the
wider Phase III census) it can actually enrich: SBIR topic description (via prior-award
`Topic Code`), PSC description, NAICS description, contract Award Title, and any
solicitation/J&A notice text already in the recovered corpus.
→ verify: a coverage table (source × % enrichable, median added chars); an explicit
  go/stop decision. If no source clears meaningful coverage on the sparse cells, STOP.

## T2 — `enriched_text` assembler
Deterministic function: contract → enriched text field from the high-coverage sources,
with provenance flags (which sources contributed). Identity-scrubbed (reuse
`_scrub_identity`). Unit-tested on fixtures.
→ verify: fixture tests pass; provenance flags correct; scrub applied.

## T3 — Description-independent features
Add firm prior-award lineage, agency/topic continuity, timing gap, NAICS ancestry as
fusion inputs. Extend the feature vector; keep `fusion_coefficients.json` frozen unless
T4 justifies a re-fit (held-out fold).
→ verify: features computed for all scored cases; no NaNs; leakage scrub re-checked.

## T4 — Re-score on the frozen #481 set
Run `score_t6.py` with enriched text + new features. Report p@1/@3/MRR per domain and
per agency with bootstrap CIs, as before/after lift vs the 0.467 baseline; include the
hard-decoy variant.
→ verify: before/after table committed; per-domain lift stated; no rich-text regression.

## T5 — Decision memo
Does the lift justify revisiting the deadline-primary verdict? State the numbers, which
cells moved, and whether any feature re-introduced leakage.
→ verify: memo committed; a clear recommendation, not a hedge.

## Deferred (documented, not this PR)
- Verified negatives for a routing/threshold gate.
- Embeddings vs word-matching bake-off on the independent set.
- Forward / open-solicitation validation.
