# Notice-corpus recovery & fusion refit — findings

**Status: REPRODUCED.** Award-grain linkage lands at leakage-scrubbed AUC
**0.847 [0.792, 0.898]**, within the published CI **[0.800, 0.886]** — the CI
gate passed and coefficients are frozen
(`packages/sbir-ml/.../fusion_coefficients.json`, hash-validated loader in
`fusion_model.py`). The firm-grain corpus (below) did **not** reproduce it; the
difference is exactly the documented lever.

## Update — award-grain reproduces the study (2026-08-01)

Attributing each notice to the **specific prior award its J&A cites** (dispositive
PIID, `award_grain.py`) and querying with **that award's** abstract fixed all
three firm-grain problems at once (rich text + clean attribution + award grain).
Recovery: **138 award-grain positives across 101 firms**, median J&A ~2k chars,
44/53 J&As cite a resolvable PIID.

| Corpus | text AUC | final AUC | vs CI [0.800, 0.886] |
|---|--:|--:|:--|
| Firm-grain (longest abstract, name attribution) | 0.575 | 0.699–0.784 | below — failed |
| Award-grain, **raw** | 0.882 | 0.920 | *above* — suspicious |
| Award-grain, **identity-scrubbed** | 0.802 | **0.847** | within — reproduced ✓ |

**Leakage control (kept skeptical of the too-good raw 0.920):** the raw number
was inflated ~0.07 by firm-name/PIID identity tokens shared between abstract and
J&A. Scrubbing them (the study's own robustness step, applied in `build_features`)
gives 0.847 — matching the study's 0.844. The J&A does not copy the abstract
(median 19% content-word overlap), so the residual signal is genuine technical
matching.

**precision@1 — read the held-out number, not the in-sample one.** `freeze_coefficients`
fits the scaler and logistic on 100% of the corpus (the right choice for a deployment
artifact), and `emit_audit_sample.build_audit` then scores that same corpus, so the
**0.681** it reports (rank-1 is the true transition for 94 of 138 award-grain positives;
audit sample in `reports/phase_iii/audit/`) is **in-sample** and not comparable to the
cross-validated AUC beside it. The honest held-out analogue is the ladder's final-stage
out-of-fold **top1 = 0.674** (`refit_ladder.json`, GroupKFold by firm) — quote that when
precision@1 is compared to anything. The two are close, which is itself reassuring, but
only 0.674 carries a generalization claim.

The ladder shape matches the study: text dominates, char adds ~0.03, NAICS/
notice-type the final lift; temporal and id_xref are degenerate on this corpus
(no award years; award-grain rows use the `citation` rule, so `id_cited` is 0)
and documented as such.

### Artifacts as shipped

- Recovery + refit scripts: `scripts/phase3_benchmark/{notice_matching,make_join_seed,
  pull_gsa_archive,build_notice_corpus,award_grain,recover_award_grain,transition_ranker,
  refit_fusion,emit_audit_sample}.py`
- **Coefficients frozen and committed:**
  `packages/sbir-ml/sbir_ml/transition/detection/fusion_coefficients.json`, carrying corpus
  frame hash `4c4064f0…` — the award-grain corpus (828 rows, 138 positives, 101 firms;
  `corpus.manifest.json`). The superseded firm-grain frame hash `6388d446…` appears only in
  the section below.
- Committed alongside: `corpus.manifest.json`, `refit_ladder.json`, this findings doc.
- Corpus parquet itself stays local (`data/*` gitignored); regenerable from the scripts.

---

## Superseded — firm-grain attempt (why 0.844 first failed)

## What was built and verified

- **Recovery works.** Streaming the public `falextracts` archive over HTTPS (no
  AWS creds), SBIR-gating, and firm-attributing notices recovered **413
  attributed notices across FY2016–2025** from a **409-firm seed** (384 with a
  usable key). Yield exceeds the study's 273.
- **The rich text is in the archive CSV** — no attachment fetch needed. Full
  attributed set median notice text **6,009 chars** (study: ~5,950), in
  Solicitation / Presolicitation / Special Notice / **J&A** types.
- **Attribution precision matters, and the spot-check caught contamination.**
  The `name_in_desc` rule on non-J&A notices is polluted by firms whose name is
  a common word ("Throughput, Inc.") or SBIR boilerplate — **REI Systems
  operates the DoD submission portal**, so its name is in every BAA. J&A and
  `name_in_awardee` attributions are clean.

## The refit result (honest)

GroupKFold-by-firm, cumulative fusion ladder:

| Corpus | positives | notice median chars | final AUC | vs CI [0.800, 0.886] |
|---|--:|--:|--:|:--|
| Full (all attributions) | 408 | 6,009 | **0.784** [0.726, 0.836] | CI overlaps, point below |
| High-precision (J&A + awardee/PIID) | 111 | 413 | **0.699** [0.614, 0.777] | below |
| High-precision + *full-corpus* negatives | 111 | — | 0.821 [0.761, 0.88] | within (but easy negatives) |

The ladder *shape* reproduces the study (char is the big jump; NAICS/notice-type
the final lift), but no configuration clears the CI honestly.

## Diagnosis — why 0.844 was not reproduced

1. **Firm-grain, not award-grain.** The study's headline was *award-level
   matching (0.844) beats firm-level aggregation (0.809)*. This corpus is
   firm-level: the query is each firm's **longest** abstract, not the **specific**
   prior award the J&A continues. A firm has ~10 SBIR awards; the longest is
   usually off-topic for a given notice.
2. **Rich text and clean attribution are in different subsets.** The rich
   J&A/solicitation text is attributed by `name_in_desc` (contaminated); the
   clean `name_in_awardee` attributions are terse **award notices** (median 413
   chars — the M0a terse-text wall again). Filtering for precision throws out the
   rich text; keeping the rich text admits contamination.
3. **The 0.821 was an artifact** of scoring high-precision positives against the
   *full corpus's* easy (generic-BAA) negatives; with honest same-type J&A hard
   negatives it is 0.699.

## The remaining lever (next increment)

**Award-grain J&A linkage.** The J&As cite the prior SBIR award number in-text
(observed: *"SBIR Phase I contract number HQ085022C0009"*). Extract that number,
attribute the notice to **that specific award** (high precision, no name
ambiguity), and use **that award's abstract** as the query. This simultaneously
(a) recovers the rich J&A text, (b) attributes precisely, and (c) matches the
study's award grain — the three things the current firm-grain corpus cannot get
at once. Expected to move the refit toward the published 0.844.

Secondary: max-cosine over *all* the firm's abstracts (the study's
"max abstract↔notice") rather than the single longest.

### Artifacts of the superseded firm-grain attempt

- Scripts: `scripts/phase3_benchmark/{notice_matching,make_join_seed,
  pull_gsa_archive,build_notice_corpus,transition_ranker,refit_fusion}.py`
- Corpus (local, `/data/*` gitignored): `data/derived/phase3_notice_corpus.parquet`
  + manifest (frame hash `6388d446…`); regenerable from the committed scripts.
- **No coefficients were frozen from this attempt** — the CI gate held.

*(Scoped to the firm-grain attempt above. For what the branch actually ships, see
"Artifacts as shipped" at the top of this document.)*
