# Product 2 — Bypass Leads — Design

> **Status:** Spec / design. Gated on A3. Extension of existing scoring, not a parallel system.

## Approach
Wrap the existing embedder + pairing in a **blocking → scoring → false-positive kill chain**.
Reuse `pair_filter_s1` (blocking), `ModernBertClient.compute_similarity` (Tier 2), and the
transition scorer's `score_text_similarity` hook (currently fed Jaccard — swap in cosine for
well-described candidates). New: cross-firm (not same-UEI) ranking, the kill chain, lead schema.

## Data flow
```
Phase II abstracts ─┐
                    ├─ pair_filter_s1 (office/PSC/NAICS/time) ─► candidate pairs
FPDS records ───────┘        │ drop desc_len < ~100 chars (A3 hard gate)
                             ▼
        kill chain:  (1) resolve_entities successor check  → drop if awardee == developer
                     (2) FSRS subaward check               → mark "subaward unknown" (data gap)
                     (3) hot-area discount                 → down-weight crowded blocking cells
                             ▼
        two-tier score:  Tier 1 string evidence (name/ref) ; Tier 2 ModernBERT cosine
                             ▼
        ranked leads ─► data/derived/product2_bypass_leads.parquet  (nullable `disposition`)
```

## Components
1. **Blocking** — `pair_filter_s1` + description-length gate (A3 finding: below ~100 chars AUC ≈
   chance, embeddings actively harmful at Q1=0.29).
2. **Kill chain** — successor check (`resolve_entities`), FSRS stub (blocked), hot-area discount
   (count of similar Phase IIs in cell).
3. **Scorer** — Tier 1 lexical/string, Tier 2 `ModernBertClient` cosine on well-described only.
4. **Lead schema** — ranked, with provenance + nullable `disposition`; language-discipline enforced.

## Risks / notes
- **Upper-bound performance** — A3 positives are 10Q-coded (better text); real bypass targets are
  worse-described, so field precision < benchmark. State on every output.
- **FSRS gap** — cannot confirm subaward satisfaction; the stub must fail *open to review*, never
  silently clear a lead.
- **Successor gap** — no M&A-through resolution; Req 2.1 is partial until built, so some acquirer
  awards may surface as leads and must be caught in review.
- **Imbalanced retrieval** — add precision@k over a realistic pool before production.
