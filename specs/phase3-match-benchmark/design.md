# Phase III Match-Quality Benchmark — Design

> **Status:** Spec / design. Small-sample harness implemented under
> `scripts/phase3_benchmark/`; full census + stratification outstanding.

## Approach

Read-only over existing award data + a targeted FPDS ATOM pull. No new ingestion pipeline, no
model training. Three scripts, deterministic and re-runnable, producing derived parquet + a
markdown decision report.

## Data flow

```
FPDS ATOM feed (q=RESEARCH:SR3)  ──pull──►  data/raw/fpds/atom_sr3/*.xml (cached)
                                             │ parse
                                             ▼
                          data/derived/fpds_10q_sr3.parquet  (PIID, UEI, description, dates, PSC/NAICS)
award_data.csv (Phase II abstracts) ─────────┤ join by resolved identity (UEI → resolve_entities)
                                             ▼
        P1 (same-firm) + N1 (diff-firm hard) + N3 (same-topic sibling) pairs
                          data/derived/phase3_match_benchmark_pairs.parquet
                                             │ score
                          ┌──────────────────┴───────────────────┐
                    Jaccard/BM25 baseline              ModernBertClient cosine
                          └──────────────────┬───────────────────┘
                          ROC-AUC + bootstrap CI, per stratum → findings.md (A3)
```

## Components

1. **`pull_fpds_10q.py`** — paginated FPDS ATOM puller; extracts `<ns1:research>` (SR3/ST3),
   PIID, UEI, `descriptionOfContractRequirement`, dates, PSC/NAICS, agency. Cached per page.
   *Label source is the structured 10Q code — this is what keeps P1 labels leakage-free.*
2. **`build_pairs_and_score.py`** — pair construction (P1/N1[/N3]) + lexical baseline + AUC.
   Identity join via UEI; extend to full `resolve_entities` cascade for M&A/rename cases.
3. **`embed_and_score.py`** — ModernBERT-Embed (`nomic-ai/modernbert-embed-base`, the repo model
   behind `ModernBertClient`) cosine + AUC, compared to lexical.

## Metrics
- Headline: ROC-AUC(P1 vs N1) with bootstrap CI (Mann-Whitney; no sklearn dependency).
- Stratified by FPDS description-length quartile and agency (and award kind once M0a lands).
- N3 sibling discrimination accuracy; retrieval-framed precision@k over an imbalanced pool
  (fast-follow, needs M0a candidate pool + blocking).

## Risks / methodology notes
- **Balanced-pair AUC overstates retrieval precision** — real Product 2 ranks over an imbalanced
  candidate pool. A2 must add precision@k with realistic blocking before a full go.
- **N1 hardness** — current N1 uses agency+time (SBIR.gov lacks funding office); true
  same-office blocking will produce harder negatives and lower AUC. Flagged as optimistic.
- **Ceiling bias** — positives are 10Q-coded (better text); results are an upper bound.
- **10Q noise** — some SR3 records are mis-coded (e.g. a library BPA); a small positive-label
  noise floor exists and should be spot-audited.
