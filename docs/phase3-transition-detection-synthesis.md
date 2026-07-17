# SBIR Phase III & Transition Detection — Synthesis Memo

> **Status:** Synthesis of the Phase III investigation (PR #423, branch `claude/phase3-detection-phase0`).
> Answers **B2** (did SBIR research transition to a federal contract), **B3** (Phase II→III latency),
> and quantifies the **FPDS Phase III undercount [L14]** that bounds confidence across **A-CP5 /
> A-CP10** (transition-thinness / composite fragility). Detailed workings:
> [`specs/product-1-status-denial-flags/`](../specs/product-1-status-denial-flags/) —
> `dark-undercount-analysis.md`, `transition-ranker-fusion.md`, `transition-ranker-audit.md`.

## Executive summary

The recurring caveat in this repo — *"FPDS Phase III tagging is historically incomplete"* — is now
**measured, not assumed**, and we have a working detector for the missing transitions. Two deliverables:

1. **The undercount (a citable count).** DoD+NASA, FY2016–2025: **191 verified** undercoded Phase III
   contracts (**~$365M**), plus a modeled **~1,000 "dark"** that are *provably unenumerable* from public
   data. Undercount rates: **DoD 14.7%, NASA 7.9%**. The verified figure is the number to cite; the dark
   layer is estimable, never enumerable.
2. **The transition ranker (a lead tool).** An award-level retrieval model that, given a firm's SBIR
   award, ranks its likely follow-on funding events: **held-out AUC 0.844** (top-3 = 63%). It is a
   **per-firm lead ranker** (analyst reviews each firm's top candidates), *not* a universe-wide
   auto-flagger — the ~1% base rate forbids the latter.

Bottom line: the undercount is **real and large** (true Phase III is ~7× the coded count), **most of it
is structurally invisible** to public data, and the recoverable share is **findable as ranked leads**.

## The question & why it matters

SBIR **Phase III** = a firm's Phase I/II research continuing into a follow-on government funding
agreement. It is the statutory point of the program (commercialization), and FPDS is supposed to flag it
(Element 10Q codes `SR3`/`ST3`). It doesn't, reliably — which quietly undermines every downstream
transition-rate metric (B2, B3, A-CP5). This memo establishes *how* incomplete, *why*, and *what is
recoverable*.

## Part 1 — The undercount (measurement)

**Two-signal framing.** A contract can carry the **code** (`SR3`/`ST3`) and/or the **description**
("SBIR PHASE III"). Crossing them exposes contracts that self-describe as Phase III but aren't coded:

| | DoD | NASA | Combined |
|---|--:|--:|--:|
| Verified undercoded (text-evidenced) | 175 | 16 | **191 (~$365M)** |
| Undercount rate | 14.7% | 7.9% | — |
| Modeled dark (unenumerable) | ~1,000 | ~73 | **~1,073** |

Frozen, spot-verified frame `frame_hash=c8769d3d6ad4` (141 exact-phrase + 11 text-scan + 23 grey-variant
+ 16 NASA). Scope: NIH/NSF/DOE excluded — their Phase III is grant/commercial, outside FPDS.

**The dark layer is unenumerable, and we proved why.** Dark Phase III are **sole-source** (FAR
6.302-5), so they are **textless everywhere** — no code, no descriptive text, no public solicitation.
Every recovery signal was tested and ruled out (USAspending competition field null; description-matching
lossy; per-firm FPDS infeasible; topic-lineage 0 hits; text-similarity near-chance on terse text).

**The base-rate wall — no automated *count* is possible.** Dark transitions are ~1% of the dark contract
universe; at that prevalence, 85% precision needs an **AUC ≳0.95**, unreachable by any text signal. So
**text matching can never produce a citable automated count** of the dark layer. The 191 verified stays
the number; the ~1,000 is a stratified estimate.

## Part 2 — Transition detection (the ranker)

Attribute-detection ("is this contract a Phase III?") is exhausted. The productive reframe is
**retrieval**: given a firm's SBIR award, rank its candidate follow-on events. The build, in the order
the evidence forced it:

1. **Substrate lesson.** The early "semantic matching doesn't work" verdict (ModernBERT AUC 0.56) was an
   artifact of **terse** contract text. Using the **rich Phase I/II abstract** as the query lifts it to
   0.74–0.79.
2. **The award-notice breakthrough** (the key unlock). Sole-source posts no solicitation, but *does* post
   an **Award Notice** and a **Justification & Approval (J&A)** — and the J&A *explicitly describes the
   prior-SBIR continuation*. Joining on **PIID** (not just Sol#) recovered these: **273 notices / 165
   firms**; J&A text is **88% useful, ~5,950-char median** — the richest query-target found. The
   sole-source cases first written off as unrecoverable carry the *strongest* signal.
3. **Sparse beats dense.** TF-IDF cosine **0.751** beat *every* neural method — ModernBERT-Embed 0.653,
   BM25 0.643, cross-encoder 0.640/0.669 (even fairly tested). The signal is **exact-lexical jargon
   overlap** (tech terms, program/part numbers); dense mean-pooling blurs it. A bigger embedder (Qwen3)
   would fail the same way — consistent with BEIR findings on entity-heavy out-of-domain retrieval.
4. **Fusion with orthogonal signals** is what beat the text ceiling — not a fancier text model.
   Award-level matching + char-n-gram + temporal (soft, no window) + identifier-cross-ref + NAICS →
   **AUC 0.844** (95% CI [0.800, 0.886], top-1 52%, top-3 63%). Feature curation mattered: dumping all
   features (0.797) lost to the curated set — `agency_match` and `sole_source` were noise.

## Part 3 — Transition latency (B3)

Measured on the coded Phase III, lag depends on the reference award: from the firm's *earliest* SBIR
award, median 18y (a misleading artifact of firm longevity); **from the *originating* award (ID-cited,
most reliable): median ~6 years, p75 11y, 50% >6y, with a long tail into 15–20y.** Long-horizon
transitions are common — emerging/deep tech (materials, sensors, photonics, biotech) matures over
10–20 years. Implication: any transition metric with a short lookback window **systematically misses the
hardest, highest-value transitions**, and 52% of transitions occur *while the firm is still winning SBIR*.

## Part 4 — Validation

- **Robustness (real, not leakage).** The 0.751 text signal survives scrubbing firm names/PI/IDs (→0.715
  — genuine technical overlap, not the J&A naming the firm), survives same-agency (0.734) and same-NAICS
  (0.728) hard negatives (transition-specific, not domain identity), and is stable (seed SD 0.005). Its
  honest ceiling: with the *hardest* negatives it's a **top-K triage ranker** (top-3 51%), not a top-1
  oracle — genuine content confusability.
- **Operating point (A).** At the realistic 0.8% base rate, a *global* threshold gives ~0.31 precision
  (base-rate wall) — but that is a **pessimistic lower bound** (scored against the undercounting labels)
  and the wrong framing: the tool deploys as a **per-firm lead ranker**, not a universe flag.
- **Independent-label replication (B).** On positives labeled by *description* rather than the SR3 code,
  AUC **0.859** (n=22) ≈ the coded 0.844 — **not an SR3-coding artifact**. Underpowered and NASA-blocked,
  because the independent-label set is largely *uncoded* — the very population that lacks recoverable rich
  text (the dark-layer wall, reconfirmed).
- **Precision@K hand-audit** — in progress; the definitive deployment metric. Already surfacing
  **label-missed wins** (genuine transitions the SR3 coding attributed elsewhere).

## What this answers, and how to use it

- **B2** ("did SBIR research transition to a federal contract"): a ranked, precision-measured lead per
  firm — the intended use of the `phase_iii_retrospective_candidates` asset + transition scorer.
- **B3** ("Phase II→III latency"): **median ~6 years from the originating award, long tail to 20y.**
- **A-CP5 / A-CP10** ("transition-thinness / fragility"): the FPDS Phase III count must be **corrected
  ~7× upward** before reading transition rates; the verified 191 (+modeled dark) is that correction.
- **Reusable method:** the **GSA `falextracts` archive** (public S3, `aws s3 cp` ~12× faster than curl)
  is the retrospective solicitation/J&A source; FPDS `VENDOR_UEI` / PIID→Sol# for linkage; **sparse
  lexical beats dense** for this jargon-heavy retrieval.

## Limitations & the frontier

- **The recoverable segment is narrow** — coded + J&A-posted. The broader (uncoded, sole-source) Phase III
  is structurally text-starved; the ranker and the count both live on the recoverable share.
- **Retrospective enumeration is capped** (sole-source textlessness + base rate). The natural home for the
  retrieval signal is **prospective alerting** — matching firm abstracts against *active* solicitations,
  where text is fully available and the firm↔opportunity link exists by construction.
- **The payoff frontier:** point the ranker at firms' *uncoded* contracts to surface candidate
  transitions the coding missed — turning the tool from "attribute the coded ones" into "find the dark
  ones." Coverage-limited, but it's the actual goal.

## Provenance

PR #423 (`claude/phase3-detection-phase0`). Frozen undercount frame `c8769d3d6ad4`. Scripts under
`scripts/phase3_benchmark/`. Benchmarks: GAO-24-106398 [L14] (undercount, Phase II HHI ~11);
NASEM [L1–L6]; Link & Scott ~50% commercialization [L12].
