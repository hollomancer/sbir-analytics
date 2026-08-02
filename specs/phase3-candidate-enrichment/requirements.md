# Phase III Candidate-Text Enrichment — Requirements

> **Status:** Draft spec. No implementation. Follow-on to the ground-truth validation
> (#481), which measured *why* the fusion ranker underperforms.
> Supports inventory questions **B2 / E1** in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B2 (did SBIR research transition to a federal contract), E1 (Phase III identification)
**Answers for:** Whoever decides whether fusion can move from a top-3 aid toward ordering the packet
**Complexity tier:** Relational (Tier 2)

---

## Done when

> The fusion ranker is re-scored on the **frozen #481 independent ground-truth set**
> (`score_t6.py`, same 45-case headline + strata) after (a) candidate text is enriched
> from **leakage-safe, contract-intrinsic** sources only and (b) description-independent
> features are added. **Done when the
> sparse-description cells lift measurably** — the target is **DLA/logistics and
> thin-description p@1 rising toward the rich-text band (~0.6)** — **without regressing
> rich-text cells**, with the lift reported per-domain with bootstrap CIs and compared to
> the T6 baseline (0.467@1). If enrichment source coverage turns out to be as empty as
> the FPDS descriptions (T1 gate), the spec stops and says so — no building on absent data.

---

## Why

T6 (#481) established that the ranker's ceiling is **not the algorithm — it's empty
candidate text.** The model compares words; when a Phase III contract's entire FPDS
description is "SBIR PHASE III AWARD." there is nothing to compare. Measured effect:
rich-text domains (sensing) score **0.60**, near-empty ones (logistics/DLA) **0.21**,
thin descriptions **0.29**. The two highest-leverage fixes T7 identified are both about
**data, not the model**: give the matcher real words, and add signals that survive empty
text. This spec does exactly those two.

## The two traps this spec must not fall into

1. **The enrichment sources may be as empty as what they replace.** J&A documents,
   solicitation notices, and topic text only help if they *exist and are retrievable*
   for these specific contracts — and Phase III sole-source awards frequently have no
   competing solicitation at all. **Mitigation:** T1 is a cheap **source-coverage
   inventory** measuring, per source, what fraction of the 45 scored contracts (and the
   census) it can enrich *on the sparse cells specifically* — before any assembler is
   built. Mirrors the step-0 coverage check that saved effort in #481.

2. **Content leakage — the load-bearing trap.** The richest source (the firm's prior
   **SBIR topic description**) can only be attached to a contract by going *through the
   firm→contract link — the very thing the ranker predicts*. Enriching only the *true*
   contract with the firm's own topic text (while the decoys get nothing) plants the
   answer in the candidate and inflates precision for a fake reason. This is distinct
   from identity-token leakage (firm name / PIID) — it is **content** leakage, and the
   `_scrub_identity` scrub does **not** catch it. **Mitigation:** every source is
   classified **contract-intrinsic** (derivable from the contract alone — its own title,
   PSC/NAICS, its own *referenced* solicitation/topic number as recorded on the contract)
   vs **firm-linked** (pulled via the answer). **Only contract-intrinsic sources may feed
   the assembler.** Faithfulness test: in real packet use the ranker sees only
   `(firm abstract) × (open solicitation)` — any enrichment that would be unavailable at
   that moment is leakage, full stop.

## Scope

### In scope

1. **SHALL** inventory candidate-text enrichment sources and, per source, measure both
   **(a) coverage** — what fraction of the 45 scored contracts (and the census) it
   enriches, reported *on the sparse cells specifically* — and **(b) leakage-safety** —
   classify each as **contract-intrinsic** (title, PSC/NAICS, the contract's own
   *referenced* solicitation/topic number) or **firm-linked** (prior-award topic pulled
   through the firm→contract link). Sources evaluated: SBIR topic description, PSC/NAICS
   descriptions, contract Award Title, recovered solicitation/J&A notice text. No new
   external scraping unless a source is high-coverage, cheap, **and contract-intrinsic**.
2. **SHALL** build a deterministic **`enriched_text`** assembler from **only the
   contract-intrinsic, leakage-safe** high-coverage sources, with provenance flags
   (which sources contributed), feeding the existing fusion text-similarity path in place
   of the bare FPDS description. Firm-linked sources are **excluded from the assembler**
   regardless of how rich they are.
3. **SHALL** add **description-independent features** — firm prior-award lineage,
   agency/topic continuity, timing gap (SBIR→transition), NAICS ancestry — as additional
   fusion inputs that carry signal when text is empty.
4. **SHALL** re-score on the frozen #481 ground-truth set with `score_t6.py`, reporting
   p@1/@3/MRR **per domain and per agency with CIs**, as a **before/after lift** vs the
   0.467 baseline, plus the hard-decoy variant.
5. **SHALL** state plainly whether the lift justifies revisiting the deadline-primary
   verdict, and whether any new feature re-introduces leakage (re-run the scrub check).

### Out of scope

- **Verified negatives / a routing gate** — separate effort; needs non-transitions (#481 T7).
- **Forward / open-solicitation validation** — separate distribution-transfer effort.
- **New model architectures / embeddings bake-off** — a parallel option in T7, not this spec.
- **Re-collecting ground truth** — reuse #481's set frozen; this spec changes *inputs*, not labels.

## Prerequisites

- Merged #481 (or its branch): `score_t6.py`, `collected/*.csv`, `resolve_firm_awards.py`.
- Merged #467 (on main): frozen fusion, `text_similarity`, `fusion_scoring`.
- Access to SBIR award data (`Topic Code`, `Abstract`), PSC/NAICS reference tables, and
  the recovered notice corpus.

## Risks

| Risk | Mitigation |
|---|---|
| Enrichment sources as empty as FPDS descriptions | T1 coverage gate before building; stop if low |
| **Content leakage** — firm-linked text plants the answer in the candidate | T1 classifies every source contract-intrinsic vs firm-linked; **only intrinsic feeds the assembler**; the `_scrub_identity` scrub does NOT catch this |
| Identity-token leakage (firm name / PIID) in enriched text | re-run the `_scrub_identity` scrub; re-check the raw→scrubbed delta |
| A source looks safe but is only populated for already-rich cells | T1 reports coverage on the sparse cells specifically, not on average |
| Non-text features overfit the small 45-case set | held-out reporting; treat lift as directional, widen the set if promising |
| Lift in sparse cells regresses rich-text cells | report per-domain before/after; require no rich-text regression |

## Verification plan

1. Source-coverage inventory → verify: per-source % of the 45 scored contracts enrichable;
   go/stop decision recorded.
2. `enriched_text` assembler → verify: deterministic, provenance-flagged, unit-tested.
3. Non-text features → verify: computed for all scored cases; leakage scrub re-checked.
4. Re-score → verify: per-domain before/after p@1/@3 + CIs vs 0.467 baseline; hard-decoy too.
5. Decision → verify: explicit statement on whether the verdict changes, with the numbers.
