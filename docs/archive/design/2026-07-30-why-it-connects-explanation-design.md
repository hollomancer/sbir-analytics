# "Why it connects" — Anchored Evidence Narrative (Phase 1)

**Date:** 2026-07-30
**Status:** Implemented; retained as the Phase 1/2 design record
**Original branch:** `feat/awardee-first-procurement-packet` (PR #466 and follow-up phases)

## Problem

The packet's "Why it connects" is bag-of-words output: "Both texts mention
autonomous, breach, and ground." Single-token overlap is word soup — it neither
maps the award's capability to the solicitation's requirement nor gives the
representative a claim they can evaluate.

## Goal (Phase 1 — explanation only)

Replace token soup with three deterministic, reader-verifiable pieces. No scoring,
pairing, threshold, or schema changes. Phase 2 (TF-IDF signal upgrade behind the
precision backtest) is explicitly deferred.

## Design

### 1. Connection sentences (`extract_connection_sentences`)

`sbir_etl/utils/procurement_text.py`. Split award abstract and opportunity
description into sentences; pick the cross-pair with the most shared technical
tokens (via existing `tokenize_technical_text`); require ≥3 shared tokens.
Tie-break: earliest opportunity sentence, then earliest award sentence.

**Emission rule:** only emit when the selected award sentence is NOT the
abstract's leading sentence. The leading sentence is already displayed as
"Built on", so a leading-sentence anchor adds nothing; on real multi-paragraph
abstracts this rule surfaces the buried connecting claim.

Rendered in `_path_detail` as a labeled line:
`**Connection:** The award describes “<award sentence>” — the solicitation asks
for “<opportunity sentence>.”` Direct quotes = verifiable by reading.

### 2. Shared technical phrases (`shared_technical_phrases`)

Same module. Order-preserving token streams from both texts; extract 3-grams
then 2-grams whose first and last tokens are non-stopwords; intersect across
texts; drop bigrams contained in a selected trigram; order by first appearance
in the opportunity text; cap at 6.

In `_public_field_facts`, when phrases exist the fact becomes
`Both describe “obstacle mapping”, “autonomous ground vehicles”, …` and replaces
the single-token sentence; the token sentence remains as fallback when no
multi-word phrase is shared. The transition-paths table cell (facts[:3])
improves automatically.

### 3. CET-area agreement (`cet_vocabulary.py`)

New small module `sbir_etl/reporting/procurement_transition/cet_vocabulary.py`:

- `load_cet_vocabulary(path)` — parse `config/cet/taxonomy.yaml`
  (21 NSTC areas, name + keyword phrases) into `{lowercased name: keywords}`;
  cached; returns `{}` on missing file or parse error (packet degrades
  gracefully, never fails).
- `cet_agreement_fact(award_cet, opportunity_text)` — resolve the award's CET
  label to an area by case-insensitive name; find that area's keyword phrases in
  the notice text (word-boundary regex via existing `find_lineage_phrases`
  machinery). If ≥1 hit:
  `Both fall in the <Area> critical-technology area — the notice mentions “<kw>”…`

The fact is verifiable (quoted keywords are in the notice) and the CET label is
already covered by the methodology caveat on screening annotations.

### Fact order in `_public_field_facts`

org match → lineage phrases → shared phrases/tokens → CET agreement → NAICS →
PSC. (UEI-named notices are already excluded upstream.)

### Fixtures / golden

Extend the Terrain Robotics abstract to 3 sentences (the connecting claim in a
non-leading sentence) and its breach-recon description to 2 sentences, so the
synthetic example demonstrates the Connection line. Align fixture CET labels to
canonical taxonomy names. Regenerate the golden example.

### AI seam

Unchanged: the optional summarizer ("Evidence-bounded comparison") remains the
polish layer; the three deterministic pieces stand alone without a key.

## Phase 2 — TF-IDF signal upgrade (approved 2026-07-30)

**Decision basis (measured, not assumed).** The transition-ranker benchmark
(commit `2bc346a6`, frozen pairs `phase3_match_benchmark_pairs.parquet`) settled
the "beyond word matching" question for this domain: sparse TF-IDF cosine 0.751
beat every neural method (ModernBERT-Embed 0.653, BM25 0.643, cross-encoder
0.669) — the connective signal is exact-lexical jargon, which dense embeddings
blur. Embeddings are therefore **rejected** for this task, with numbers.

**Validation run for this change (2026-07-30, repo venv):**

| Substrate | n | Jaccard AUC | word TF-IDF (1,2) | char_wb (3,5) | 0.6/0.4 blend |
|---|--:|--:|--:|--:|--:|
| All pairs (median desc 42 chars — terse-FPDS wall) | 723 | 0.555 | 0.571 | 0.565 | 0.574 |
| Rich descriptions ≥150 chars (proxy for SAM.gov notices) | 141 | 0.651 | **0.710** | 0.634 | 0.673 |
| Rich ≥300 | 133 | 0.644 | **0.708** | 0.646 | 0.684 |
| Rich ≥500 | 129 | 0.648 | **0.710** | 0.656 | 0.696 |

- Terse-text near-chance replicates the known M0a finding — the packet's S2/S3
  targets are rich notice descriptions, so the rich subsets are the honest proxy.
- **Word-only TF-IDF (1,2)-grams wins**; the char blend drags the text score.
  Char-n-grams belong as a separate fusion feature (as in the 0.844 ranker), not
  mixed into the text component.
- **Scale:** word TF-IDF sits on the same scale as Jaccard (pos p90 = 0.028 for
  both; neg p95 0.014 vs 0.023) — composite candidate scores shift ≲0.002, so
  `HIGH_THRESHOLD_DIRECTED` / `FOLLOWON` are **unchanged by measurement**, not
  neglect. S2/S3 precision remains governed by the human audit CSV (there is no
  automated S2/S3 ground truth).
- **RETROSPECTIVE (S1) is in this code path** — `score_candidate_pairs` →
  `_score_pair` → `compute_topical_similarity` scores all three classes, with
  S1 text weight 0.10. Measured shift bound on the terse-FPDS substrate
  (n=723): |tfidf−jaccard| median 0.000 / p95 0.021 → S1 composite shift
  median 0.000 / p95 0.001 / max 0.010 against the 0.85 HIGH threshold.
  Negligible and quantified; the release-time precision backtest remains the
  hard gate.

**Changes:**

1. `packages/sbir-ml/sbir_ml/transition/detection/text_similarity.py` — port of
   the ranker's `award_similarity` core: corpus-fitted word (1,2)-gram TF-IDF
   with English stopwords, exposing a full similarity matrix and a paired
   (row-aligned) diagonal. sklearn is already an sbir-ml dependency.
2. `similarity.py` — `compute_topical_similarity_batch(pairs_df)` computes the
   text component for the whole run at once (TF-IDF fitted over all prior-award
   texts + all notice texts in the frame); weights unchanged
   (NAICS .30 / PSC .20 / text .50). The per-pair
   `compute_topical_similarity` remains as a batch-of-one wrapper (degenerate
   idf; production uses the batch path).
3. `_with_pair_metadata` switches from per-row apply to the batch computation.
4. Explanation tie-in: shared phrases in "Why it connects" are re-ranked by
   corpus rarity (document frequency over the run's abstracts + notice
   descriptions, pure-Python in `procurement_text.rank_phrases_by_rarity`) so
   distinctive jargon leads the list. sbir_etl stays sklearn-free.

## Phase 3 — smarter candidate selection, minimal set (approved 2026-07-31)

Two features from the ranker's fusion ladder that are self-evidently right and
require no refit data:

1. **Identifier cross-ref** (`sbir_ml.transition.detection.ranking_features.id_xref`,
   ported from the ranker core; ladder gain 0.779 → 0.795). The notice text
   cites the firm's own SBIR contract/topic/tracking number.
   - Scored: new `id_xref_score` subscore — DIRECTED weight 0.10 (redistributed
     from agency 0.25→0.20 and competition 0.25→0.20), FOLLOWON 0.05 (from text
     0.45→0.40), **RETROSPECTIVE 0.0** so the ≥0.85 precision gate is
     bit-identical by construction (asserted in tests).
   - Evidence: leading "Why it connects" fact — *"The notice cites the
     awardee's SBIR award number (…)"* — and the strongest Validate branch,
     superseding the org-level guidance.
2. **Temporal sanity gate** (ranker `after_first` floor): a notice posted
   before the prior award began cannot be its follow-on — dropped in
   `_with_pair_metadata` (S2/S3 only). Null dates on either side stay neutral;
   `prior_award_date` added to the pair projection.

**Deferred, with reasons:**
- **Full LR fusion (0.844)** — blocked on the #442 recovered-notice dataset;
  the ported `evaluate()` harness can fit + freeze coefficients when it lands.
- **Char-n-gram channel** — measurably dragged on the in-tree substrate.
- **Notice-type ordinal** — the curation lesson (kitchen-sink 0.797 < curated
  0.844) argues against guessing its weight without refit data; the DIRECTED
  pair filter already restricts notice types.

## Out of scope

- ModernBERT embeddings (rejected on measurement — see table above).
- Weight/threshold retuning beyond the scale check (needs the human-audit
  precision loop, not an offline proxy).

## Testing

- Pure-function tests: sentence anchoring picks the non-leading connecting
  sentence; returns None for single-sentence abstracts and sub-threshold
  overlap; phrase extraction returns multiword phrases, drops sub-grams, falls
  back cleanly; CET vocabulary loads, matches by keyword, degrades to None on
  unknown label or missing file.
- Packet-level: Connection line renders; phrase fact replaces token fact; CET
  fact renders for fixture rows; golden regenerated and asserted.
