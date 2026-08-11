# Phase III Notice Corpus & Fusion Ranker — Requirements

**Target epistemic tier:** `evidence`

> **Status:** Implemented (T1–T7 done — see `tasks.md`). The implementation ships a production
> scoring path: coefficients are frozen at
> `packages/sbir-ml/sbir_ml/transition/detection/fusion_coefficients.json` and the monthly
> procurement packet consumes them, which **changes packet ordering** (strongest match
> first, deadline as tie-break). Two requirements were superseded rather than satisfied —
> see "Superseded by the award-grain pivot" below.
> Supports inventory questions **B2 / B3 / E1** in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** B2 (did SBIR research transition to a federal contract), B3 (transition latency), E1 (Phase III identification)
**Answers for:** Procurement-center packet consumers, transition-detection maintainers
**Complexity tier:** Relational (Tier 2)

---

## Done when

> The recovered-notice corpus is frozen in-tree as a provenance-stamped parquet
> ([N] notices, [F] firms, manifest hash recorded); the fusion ranker refit on it
> reproduces AUC within the published CI **[0.800, 0.886]** under GroupKFold-by-firm;
> the fitted coefficients are frozen as versioned constants with provenance; the
> monthly packet's DIRECTED/FOLLOWON scoring consumes them behind the benchmark
> harness gate; the RETROSPECTIVE ≥0.85 precision gate is demonstrably unchanged;
> and a precision@K hand-audit sample ([K] rows) is emitted for human adjudication.

---

## Superseded by the award-grain pivot

The firm-grain corpus these requirements were written against failed to reproduce the
study (text AUC 0.575). `findings.md` documents the pivot to **award grain** — attributing
each notice to the specific prior award its J&A cites — which reproduced it at 0.847,
within the published CI. Two requirements did not survive that pivot, and are recorded
here rather than quietly dropped:

- **Requirement 2 (stratum column).** The shipped corpus has no `stratum` column. Award-grain
  rows are formed by a single citation rule, so the firm-grain strata it was meant to carry
  no longer partition anything. Cost: none identified; the strata were a firm-grain construct.
- **Requirement 3 (two label channels).** The shipped corpus has **one** channel —
  `citation` (138 positives; `corpus.manifest.json`). The FPDS-coded (`SR3`/`ST3`) primary and
  the description-labeled replication set were both firm-grain constructions and neither was
  built. **Cost: the independent-replication check on the label is gone.** The reproduction
  therefore rests on a single labeling rule, and the 0.847 has no second-channel corroboration.
  Restoring it means labeling award-grain rows a second way — the natural candidate is
  description-matching on the notice text — and is not done here.

---

## Background

The transition-ranker study (commit `2bc346a6`; findings in
`specs/phase3-match-benchmark/transition-ranker.md`) produced the strongest
candidate-selection result in the repo: award-level retrieval
**AUC 0.844** (95% CI [0.800, 0.886]) from sparse word TF-IDF fused with orthogonal
structural features (char-n-gram, temporal soft-gap, identifier cross-ref, NAICS,
notice-type ordinal). Two of those features (id_xref, temporal floor) already shipped
into the monthly packet with hand-set weights; the full learned fusion did not,
because its **training substrate is not in the repo**:

- The corpus — ~273 recovered notices across ~165 firms, including sole-source
  **J&A documents** (~5,950-char median text, 88% useful) — was pulled during the
  July 2026 benchmark sessions from GSA's `falextracts` Contract-Opportunities
  archive (`aws s3 cp`) and linked firm↔notice via FPDS `VENDOR_UEI` and
  Sol#+PIID joins (33/849 solicitations recovered over a 10-year window).
- Only derived outputs were committed (the scoring core and findings; local
  benchmark parquets under `data/derived/` are gitignored
  per `/data/*`, so no notice text is in version control). The corpus and recovery
  scripts were not committed to `main`.
- The ranker findings parked productionization under **#442** ("external evidence
  and source adapters"), a generic framework epic that is unstarted. That coupling
  is soft: fitting frozen coefficients needs a **one-time, provenance-stamped
  frozen dataset** (precedent: `data/derived/phase3_match_benchmark_pairs.parquet`),
  not the adapter framework. This spec takes the narrow path; #442 remains the
  eventual home for *scheduled* re-recovery.

## Scope

### In scope

1. **SHALL** re-run the notice recovery reproducibly: GSA `falextracts` archive
   pulls + FPDS `VENDOR_UEI` / Sol#+PIID joins, committed as scripts under
   `scripts/phase3_benchmark/` (research-grade, manifested — not a Dagster asset).
2. **SHALL** freeze the corpus at `data/derived/phase3_notice_corpus.parquet`:
   one row per (firm award, notice) with award text, notice text, notice type,
   dates, identifiers, label, and stratum; plus a JSON manifest recording source
   URIs, pull dates, join rules, row counts, and a frame hash.
3. ~~**SHALL** carry two label channels, mirroring the study: FPDS-coded positives
   (`SR3`/`ST3`) as the primary, and description-labeled positives as the
   independent replication set.~~ **Superseded** — see below.
4. **SHALL** refit the fusion with the already-ported harness
   (`evaluate` in `scripts/phase3_benchmark/transition_ranker.py`, GroupKFold **by firm**),
   reporting the ladder
   (text-only → +each feature) against the published 0.844 [0.800, 0.886].
   A refit outside the CI blocks coefficient freezing and triggers investigation
   (archive drift is the expected cause — see risks).
5. **SHALL** freeze the fitted coefficients (logistic weights + scaler
   parameters + feature order + corpus manifest hash) as a versioned artifact
   in `sbir-ml`, loaded — never fit — at scoring time.
6. **SHALL** integrate fused scoring into DIRECTED/FOLLOWON candidate selection
   behind the existing weight-validation and threshold conventions, with a
   scale-shift measurement before any threshold change. **RETROSPECTIVE scoring
   SHALL be bit-identical** (asserted in tests, as with `id_xref` weight 0.0).
7. **SHALL** emit a precision@K hand-audit sample (top-K per firm) to
   `reports/phase_iii/audit/` — the study's pending deployment metric.
8. **SHOULD** re-test the char-n-gram channel during refit: it earned +0.022 on
   this substrate as a learned feature and may re-enter here (unlike the packet's
   fixed-weight text score, where it measurably dragged).

### Out of scope

- **#442 adapter framework** — scheduled/managed re-recovery lives there later;
  this is a one-time research freeze.
- **Embeddings** — rejected on measurement (0.653 vs 0.751); do not relitigate.
- **Universe-wide auto-flagging** — the base-rate wall stands; deployment stays
  a per-firm lead ranker.
- **Automated Phase III counts from the dark layer** — structurally impossible
  per the synthesis memo; the ranker generates leads, not counts.

## Prerequisites

- AWS CLI access to the GSA `falextracts` public archive.
- FPDS ATOM feed access for `VENDOR_UEI`/PIID pulls.
- (Optional) `SAM_GOV_API_KEY` to extend the corpus with current notices.

## Risks

| Risk | Mitigation |
|---|---|
| Archive drift — the July recovery yield (33/849 sols) may not reproduce | Freeze raw pulls alongside the derived parquet; manifest records what was retrievable when |
| Refit lands outside the published CI | Blocks coefficient freeze; investigate composition drift before shipping anything |
| Small corpus (~273 notices) → wide CIs, overfitting risk | GroupKFold by firm (no firm in train+test), curated feature set only (kitchen-sink measured worse: 0.797 < 0.844) |
| Coefficients silently drift from corpus | Artifact embeds the corpus manifest hash; loader refuses a mismatch |

## Verification plan

1. Recovery scripts re-run end-to-end → verify: manifest counts + frame hash recorded.
2. Refit ladder computed → verify: within [0.800, 0.886] under GroupKFold-by-firm.
3. Coefficients frozen → verify: loader round-trips; scoring uses load-only path.
4. Packet integration → verify: RETROSPECTIVE composite bit-identical (test),
   DIRECTED/FOLLOWON scale shift measured and documented before any threshold move.
5. Audit sample emitted → verify: file in `reports/phase_iii/audit/`, K rows per firm.
