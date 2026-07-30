# "Why it connects" — Anchored Evidence Narrative (Phase 1)

**Date:** 2026-07-30
**Status:** Approved (design), Phase 1 only
**Branch:** `feat/awardee-first-procurement-packet` (PR #466)

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

## Out of scope (Phase 2, deferred)

- TF-IDF cosine replacing Jaccard in `compute_topical_similarity` /
  `score_text_similarity`, gated on the ≥85% retrospective precision backtest.
- ModernBERT embeddings (stays behind the existing spec rule).
- Any threshold or pairing change.

## Testing

- Pure-function tests: sentence anchoring picks the non-leading connecting
  sentence; returns None for single-sentence abstracts and sub-threshold
  overlap; phrase extraction returns multiword phrases, drops sub-grams, falls
  back cleanly; CET vocabulary loads, matches by keyword, degrades to None on
  unknown label or missing file.
- Packet-level: Connection line renders; phrase fact replaces token fact; CET
  fact renders for fixture rows; golden regenerated and asserted.
