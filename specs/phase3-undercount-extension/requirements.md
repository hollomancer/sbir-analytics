# Phase III Undercount Extension — Requirements

> **Status:** Draft spec. Builds on existing undercount work (M0a + 3-source
> capture-recapture) and the coverage-expansion sources (#485). Answers the north-star
> question **B3**: *"How much undercount exists in Phase III coding?"* — the transition
> **classifier/measurement** use case (recall), not ranking.

**Research question anchor:** B3 (Phase III undercount, transition rate), B2 (did-it-transition), A2/A3 (rate / multiplier)
**Answers for:** SBA / agency program managers, GAO — how complete is Phase III coding
**Complexity tier:** Inferential (Tier 3)

---

## Done when

> The Phase III coding undercount is re-estimated with the **new capture lists** the
> coverage work produced, reported as **two clearly separated layers**:
> **(1) contract-coding undercount** — comparable to the existing ~19–28% capture-recapture,
> now with §638 self-labeled notices added as an independent capture list; and
> **(2) a separate non-contract vehicle layer** — subaward and grant transitions that FPDS
> contract coding cannot see at all, reported as a *bounded, provisional* count (relevance-
> filtered), NOT folded into the contract number. Both are broken out **by agency** and
> **by vehicle**, with capture-recapture independence assumptions stated and the ≥85%
> classifier-precision benchmark reported against the pooled ground truth.

---

## Why

`docs/research-questions.md` **B3** asks how much undercount exists in Phase III coding — a
**recall** question, the north-star use case (see #481 T7 superseding note). Existing work:
- **M0a** (`m0a_undercount_summary.json`): DoD FY16–25, **14.7% uncoded** — a narrow lower
  bound (only contracts whose *description* says "SBIR PHASE III").
- **3-source capture-recapture** (`nano_capture_recapture.py`, commit 52b005a1): dark ~1,543
  [915–2,745], coding misses **~19–28%** (contract universe).

The coverage-expansion work (#485) produced **new independent detection sources** that the
existing estimate never used — and two of them lie *outside* the FPDS contract universe. Adding
them (a) tightens the contract-coding estimate and (b) exposes a non-contract layer the current
undercount does not count at all.

## The layers (keep them separate — do not conflate)

1. **Contract-coding undercount** — the existing question: of Phase III *contracts*, what share
   is uncoded? Capture lists: M0a coded/dark pools + **§638 self-labeled notices (new)**. Метric:
   dark estimate + miss-rate %, by agency. Comparable to the 19–28% baseline.
2. **Non-contract vehicle layer (new, separate denominator)** — transitions via **subaward**
   (firm as sub to a prime) and **grant** (civilian assistance), which FPDS contract coding
   cannot represent. These are not "miscoded contracts"; they are a different population.
   Reported as a **bounded, provisional** count with the relevance caveat, explicitly *not*
   added to the contract-coding %.

## Scope

### In scope
1. **SHALL** reuse M0a's coded/grey/dark pools and generalize `nano_capture_recapture` from the
   nanotech cohort to the full DoD (and, where data allows, civilian) Phase III frame.
2. **SHALL** add the **§638 self-labeled** notices (from #485 `extract_phase3_selflabeled`) as an
   independent capture list; re-run capture-recapture; report the tightened contract-coding
   undercount by agency vs the 19–28% baseline.
3. **SHALL** quantify the **non-contract vehicle layer** — subaward and grant transitions
   (#485), relevance-filtered (SBIR-derivation gate), reported as a separate bounded count by
   vehicle and agency, with the provisional caveat.
4. **SHALL** report **classifier precision/recall** of the coded Phase III set against the
   **pooled ground truth** (293 hand-collected + 66 self-labeled + MDA-35 + component harvest),
   at the ≥85% precision operating point — the B2 companion metric.
5. **SHALL** state capture-recapture independence assumptions and where they are weak.

### Out of scope
- The firm-ranking / PCR-packet product (separate; #484).
- Production ingestion / scheduling.
- A full civilian-contract undercount (data-limited); civilian appears in the grant vehicle layer.
- Claiming subaward/grant counts are verified transitions — they are bounded, provisional, caveated.

## Risks
| Risk | Mitigation |
|---|---|
| Capture lists not independent (self-labeled ⊂ description-coded) | test overlap; use lists whose detection mechanism differs from FPDS coding; report dependence |
| Subaward/grant "transitions" include non-transitions | SBIR-derivation relevance gate (tech + timing); report as bounded/provisional, separate layer |
| Conflating vehicle layer with contract undercount inflates the headline | two separate denominators, never summed into one % |
| Small ground-truth N → wide recall CI | pool all sources; report CI; don't over-claim |

## Verification plan
1. Capture-recapture generalized + re-run with §638 list → verify: contract-coding undercount by
   agency, with the new list's marginal effect vs the 19–28% baseline; independence stated.
2. Non-contract layer → verify: bounded subaward + grant transition counts by vehicle/agency,
   relevance-filtered, reported separately with caveats.
3. Classifier recall → verify: precision/recall of coded set vs pooled ground truth at ≥85%
   precision; recall (undercount) stated.
4. Memo → verify: one-page B3 answer — contract-coding undercount (updated) + the separate
   vehicle layer, with what's solid vs provisional.
