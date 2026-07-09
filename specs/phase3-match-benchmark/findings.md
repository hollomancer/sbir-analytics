# Phase III Match-Quality Benchmark — Findings (A3 decision gate)

> **Status:** Preliminary result on a small labeled sample (M0b). Full A0 census and
> agency/kind stratification pending; conclusions below are directional but decision-grade.
> Supports inventory questions **B3** (Phase III undercount / transition detection) and **A2**
> (DIB integration via FPDS) in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** Can text similarity distinguish true SBIR Phase III derivative
pairs from plausible non-derivative pairs, given real-world FPDS description quality? This gates
**Product 2 (bypass leads)**.
**Complexity tier:** Relational → Inferential (Tier 2–3)

## Sample

- **Positives (P1):** 401 same-firm pairs = (a firm's most-recent-prior Phase II abstract) ×
  (its FPDS record **coded `research=SR3`**, i.e. Element 10Q, pulled from the FPDS ATOM feed).
  Labels come from the **structured 10Q code, not description keywords** — no label leakage.
  190 distinct firms.
- **Hard negatives (N1):** 401 pairs = a coded Phase III description × a **different** firm's
  same-agency, prior-in-time Phase II abstract. (Soft version of "same funding office" — see
  Limitations.)
- Source: `data/derived/fpds_10q_sr3.parquet` (600 SR3 records; 100% UEI fill; **median
  description 47 chars**) joined to Phase II abstracts in `data/raw/sbir/award_data.csv`.

## Result — the four benchmark questions

**1. Is Product 2 viable as a lead ranker?** *Conditionally.* P1-vs-N1 ROC-AUC:

| FPDS description length | n | Lexical (Jaccard) | ModernBERT-Embed cosine |
|---|---|---|---|
| Overall | 401 | 0.598 (CI 0.567–0.627) | **0.570 (CI 0.532–0.609)** |
| Q1 ≤26 chars | 101 | 0.490 | 0.292 |
| Q2 27–42 | 100 | 0.538 | 0.504 |
| Q3 43–94 | 103 | 0.613 | 0.666 |
| **Q4 ≥100 chars** | 97 | 0.755 | **0.824** |

Not viable as a blanket ranker (overall AUC ≈ chance; the embedder is *below* lexical overall).
**Viable only in the well-described stratum (Q4, ~25% of records), where ModernBERT reaches 0.824.**

**2. Which strata carry the signal?** FPDS **description length** is the dominant gate. Below
~100 chars the descriptions are boilerplate ("SBIR PHASE III AWARD.") that share zero content
tokens with the abstract (median Jaccard = 0.000 on both classes) and embed to a generic point —
Q1 embedding AUC 0.292 is *worse than chance*. Product 2 blocking **must** exclude thin
descriptions or it underperforms a coin flip.

**3. Did the lexical baseline match the embeddings?** Overall, lexical **beats** embeddings
(0.598 vs 0.570) — cheaper wins where text is thin. Embeddings only justify their cost in Q4
(+0.069 AUC). Any Product 2 build should run lexical first and reserve the embedder for
well-described candidates.

**4. Ceiling caveat (stated verbatim, per the task):**
> P1/P2 positives are agency-coded awards — the sample where agencies did the paperwork and wrote
> the better descriptions. True bypass cases live disproportionately where coding and text quality
> are worst. All benchmark results are an **upper bound** on real-world Product 2 performance; only
> the P3 gold set escapes this bias, and it is tiny.

The Q4 0.824 is therefore an **upper bound confined to ~1/4 of coded records**; uncoded bypass
cases (the actual Product 2 targets) have systematically worse text and will score lower.

## Recommendation
- **Do not descope Product 2 to string-evidence-only outright** — there is real embedding signal
  (0.824) in the well-described stratum, above the task's provisional precision anchor's spirit.
- **Do gate Product 2 hard on description length** (block below ~100 chars) and **run it as a
  two-tier lead ranker**: Tier 1 = string evidence (product/system name, explicit award ref),
  Tier 2 = ModernBERT cosine **only on well-described candidates**. Treat all leads as
  upper-bound signal for human review, never findings.
- **Confirm before full build:** (a) precision@k over a realistic *imbalanced* candidate pool
  (this AUC is on balanced pairs); (b) N3 sibling discrimination; (c) re-run N1 with true
  same-funding-office blocking (harder negatives will lower AUC). These are the remaining A2 items.

## Limitations (direction of bias)
- **N1 is a soft hard-negative** — matched on agency + time, not funding office/command (SBIR.gov
  has no office field), so N1 is *easier* than the ideal → the AUCs here are **optimistic**.
- **Non-lineage not fully confirmed** — N1 uses UEI≠ + name≠ as the lineage check; true
  successor-in-interest resolution (acquirer-of-Phase-II-firm ≠ negative) does not exist in the
  repo, so a few N1 pairs could be mislabeled acquisitions. Direction: inflates apparent AUC.
- **Balanced pairs, not retrieval** — real Product 2 ranks over a large imbalanced pool; AUC
  overstates precision@k.
- **Single research code (SR3)** — STTR Phase III (ST3) and agency mix not yet stratified.

## Reproduce
```
python scripts/phase3_benchmark/pull_fpds_10q.py SR3 --pages 60      # -> data/derived/fpds_10q_sr3.parquet
python scripts/phase3_benchmark/build_pairs_and_score.py             # -> pairs + lexical AUC
python scripts/phase3_benchmark/embed_and_score.py                   # -> ModernBERT AUC
```
