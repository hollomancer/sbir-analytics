# Notice-corpus recovery & fusion refit — findings

**Status:** Pipeline reproduced end-to-end against the live GSA archive. The
published fusion AUC **0.844 [0.800, 0.886] was NOT reproduced within CI**; the
CI gate correctly refused to freeze coefficients. The gap is diagnosed and the
remaining lever is identified (award-grain linkage). No coefficients frozen.

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

## Artifacts

- Scripts: `scripts/phase3_benchmark/{notice_matching,make_join_seed,
  pull_gsa_archive,build_notice_corpus,transition_ranker,refit_fusion}.py`
- Corpus (local, `/data/*` gitignored): `data/derived/phase3_notice_corpus.parquet`
  + manifest (frame hash `6388d446…`); regenerable from the committed scripts.
- Committed: `corpus.manifest.json`, `refit_ladder.json`, this findings doc.
- **No coefficients frozen** — the CI gate held.
