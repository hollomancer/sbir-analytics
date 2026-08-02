# Phase III Candidate-Text Enrichment — Tasks

> Sequenced so the cheap coverage gate (T1) runs before any assembler is built —
> if the enrichment sources are as empty as the FPDS descriptions, stop and say so.

## T1 — Source coverage + leakage-safety inventory (the gate)
Per enrichment source, measure **two** things, not one:
- **Coverage:** what fraction of the 45 T6-scored contracts (and the census) it enriches,
  reported **on the sparse cells specifically** (DLA/logistics, thin-desc) — not on
  average. A source that only enriches already-rich cells does not count.
- **Leakage-safety:** classify each source **contract-intrinsic** (title, PSC/NAICS, the
  contract's *own* referenced solicitation/topic number) vs **firm-linked** (prior-award
  topic reached through the firm→contract link = the answer). Firm-linked sources are
  **disqualified from the assembler** no matter how rich — plant the answer in the
  candidate and precision inflates for a fake reason (`_scrub_identity` will NOT catch it,
  it is content not identity-token leakage).
Sources evaluated: SBIR topic description, PSC description, NAICS description, contract
Award Title, recovered solicitation/J&A notice text.
→ verify: a table (source × sparse-cell coverage % × median added chars × intrinsic/
  firm-linked). **GO** only if ≥1 contract-intrinsic source meaningfully covers the sparse
  cells; else **STOP** and redirect to T3 (non-text features) / verified negatives.

## T2 — `enriched_text` assembler
Deterministic function: contract → enriched text field from **only the contract-intrinsic,
leakage-safe** sources T1 cleared, with provenance flags (which sources contributed).
Firm-linked sources are excluded by construction. Identity-scrubbed (reuse
`_scrub_identity`) on top. Unit-tested on fixtures — including a test that asserts no
firm-linked text can enter the assembler.
→ verify: fixture tests pass; provenance flags correct; scrub applied; leakage-guard test
  proves firm-linked sources are rejected.

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
