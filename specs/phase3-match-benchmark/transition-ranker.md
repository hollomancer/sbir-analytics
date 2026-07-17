# Transition ranker: findings

Status: **research result; scoring core ported + fixture-tested. Data-recovery pipeline is a documented
dependency (production lifecycle → #442). Deployment metric (precision@K) pending a human audit.**

Extends the benchmark's scope decision ("text similarity alone is not a standalone product; structural
signals must remain primary") with a concrete, validated ranker. `scripts/phase3_benchmark/transition_ranker.py`.

## Reframe

Attribute-detection ("is this contract a Phase III?") is exhausted. The productive framing is
**retrieval**: given a firm's Phase I/II award, rank its candidate follow-on funding events (notices).
Output is **ranked leads with measured precision**, not a universe-wide flag.

## What works — sparse lexical + structural fusion

On recovered notices (GSA archived Contract-Opportunity descriptions incl. sole-source **J&A** documents;
firm↔notice linked by PIID/Sol#), the retrieval AUC ladder (GroupKFold **by firm**, hard negatives =
other firms' Phase III notices):

| Method | AUC |
|---|--:|
| **TF-IDF cosine (word)** | **0.751** |
| ModernBERT-Embed (dense) | 0.653 |
| BM25 (best b) | 0.643 |
| cross-encoder (bge-reranker, fair short-query) | 0.669 |
| terse-text baseline | 0.577 |

**Every neural / reweighting method underperforms plain TF-IDF cosine** — the signal is exact-lexical
jargon overlap (tech terms, program/part numbers) that dense pooling blurs and BM25's bag-of-terms query
discards. Consistent with BEIR findings for entity-heavy out-of-domain retrieval; a larger embedder would
blur the same jargon. So the lever is **not a better text model** but **orthogonal structural signal**:

| Fusion step (award-level) | AUC |
|---|--:|
| word TF-IDF | 0.751 |
| + char n-gram | 0.773 |
| + temporal (soft gap, floor `after_first`, no window) | 0.779 |
| + identifier cross-ref | 0.795 |
| + NAICS + notice-type (curated) | **0.844** (95% CI [0.800, 0.886]) |

Feature curation matters: dumping all candidate features (0.797) lost to the curated set — `agency_match`
and `sole_source` were noise in the retrieval framing. Matching at **award grain** (best Phase I/II
abstract → notice) beat firm-level aggregation (0.809→0.844) and yields inherently verifiable
award→event claims.

## Transition latency (feeds B3)

Measured from the *originating* award (not the firm's earliest — that conflates firm longevity), lag is
**median ~6 years, p75 11y, 50% >6y, tail to 15–20y**. Long-horizon transitions (emerging/deep tech) are
common, and 52% occur while the firm is still winning SBIR — hence the temporal feature uses an unbounded
`gap` and a first-award floor, never a short window.

## Validation

- **Robustness:** the text signal survives scrubbing firm names/PI/IDs (0.751→0.715 — genuine technical
  overlap, not the J&A naming the firm) and same-agency (0.734) / same-NAICS (0.728) hard negatives
  (transition-specific, not domain identity); stable across seeds. Honest ceiling: with the *hardest*
  negatives it is a **top-K triage ranker** (top-3 ~0.51), not a top-1 oracle.
- **Operating point:** at the realistic ~0.8% base rate a *global* threshold gives ~0.31 precision
  (base-rate wall) — a lower bound (scored vs undercounting labels) and the wrong framing. Deploy as a
  **per-firm lead ranker**, not a universe auto-flag.
- **Independent-label replication:** on positives labeled by *description* (not the `SR3` code), AUC 0.859
  (n=22) ≈ the coded 0.844 — not a coding artifact, though underpowered (that population is largely
  uncoded → text-starved, the recurring coverage wall).

## Scope / limits

- The **data-recovery pipeline** (GSA `falextracts` archive via `aws s3 cp`; FPDS `VENDOR_UEI`/PIID→Sol#)
  is a documented dependency, not re-homed here — it belongs with the production source lifecycle (#442),
  with manifested provenance. This module ports the **scoring core** only.
- The result lives on the **recoverable segment** (coded + J&A-posted); the broader uncoded Phase III is
  structurally text-starved. The ranker is a **candidate generator with measured precision**, not a count.
- **precision@K** (the deployment metric) requires a human-adjudicated sample; pending.
