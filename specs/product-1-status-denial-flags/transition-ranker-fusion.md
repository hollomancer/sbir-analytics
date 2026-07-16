# Signal-Fusion Transition Ranker — Plan

> **Status:** Plan. Follows the rich-vs-rich retrieval result in
> [dark-undercount-analysis.md](./dark-undercount-analysis.md) (TF-IDF cosine **0.751**, robust:
> survives leakage-scrub 0.715 and same-agency/NAICS hard negatives ~0.73; ceiling is *content
> confusability*, not the text method — every neural method underperformed TF-IDF).

## Goal & success criterion
Beat **TF-IDF-alone (0.751 / top-3 = 51%)** on **held-out firms**, and produce a **calibrated score**
for the `phase-3-solicitation-alerts` **≥85% precision** lead-tool target. Success = a statistically
clear lift on GroupKFold-by-firm precision@K, **and** an ablation proving the lift comes from
*orthogonal (non-text)* signal — not more text.

## Why fusion (grounded in measurement)
The robustness battery isolated the failure mode: **confusable notices** — other-firm notices *more*
text-similar than a firm's own (hardest-negative AUC = 0.47). That confusion is *in the text*, so no
text model fixes it (dense 0.653, BM25 0.643, cross-encoder 0.640 all lost). Fusion disambiguates with
signals orthogonal to text: same program office, timed after Phase II, cites the firm's topic code.

## Build order (per direction, 2026-07-16)
**Phase 1 — TEMPORAL first.** Highest-value, lowest-leakage signal. A transition necessarily comes
*after* the firm's Phase I/II. Kills the large class of confusables that predate the SBIR work.
- `is_after` = notice/contract date ≥ firm's latest Phase I/II completion.
- `time_gap` = months between (bucketed; transitions cluster ~1–6 yrs after).
- Source: contract `signedDate` (FPDS XML, local) vs firm's latest `Award Year` (award_data.csv).
- Deliverable of Phase 1: `tfidf_cos + temporal` vs `tfidf_cos` alone, GroupKFold precision@K + ablation.

**Phase 2 — IDENTIFIER CROSS-REFERENCE.** High-precision, near-dispositive when present.
- `id_xref` = notice text cites the firm's SBIR contract # (`Contract` col) or `Topic Code` or prior
  solicitation # (exact regex, normalized).
- Source: firm identifiers from award_data.csv; notice text = recovered `desc`.
- **Framing caveat:** legit in *deployment* (we rank a *known* firm's candidates) but a form of leakage
  in the pure "which firm owns this notice" retrieval framing → **report with AND without it.**

**Later (not now):** organizational (`agency_match`, `naics_match` from FPDS XML), contract attrs
(`notice_type` J&A>award, `sole_source` from FPDS `reasonNotCompeted`), and an optional second text
view `char_ngram_cos` (char 3–5 TF-IDF — bridges jargon/acronym/part-number formatting variants and
J&A OCR/redaction noise; decorrelated from word-TF-IDF, used alongside it).

## Model
- **LightGBM, LambdaMART objective** (optimizes ranking/precision@K directly). Fallback: **logistic
  regression** (calibrated probabilities + interpretable coefficients).
- **Kept small** — ≤~8 features, shallow, regularized. With ~128 positive firms, feature count must be
  ≪ N or it memorizes.

## Validation (non-negotiable)
- **GroupKFold by UEI** — no firm in both train and test (else it learns firm-specific vocab → fiction).
- Firm-clustered **precision@K, MRR, AUC** on held-out folds vs TF-IDF-alone on the *same* folds.
- **Ablation table:** text-only → +temporal → +id_xref → (+organizational) to attribute the lift.
- **Two framings reported:** powered retrieval (hard negs = other firms' Phase III notices) as primary;
  deployment-shaped within-firm precision@K where a firm's full candidate pool is available.

## Risks & mitigations
1. **Small-N overfitting** — few features, regularize, GroupKFold, report CI.
2. **Identity leakage** (`id_xref`, `firm_name_in_notice`) — report with/without; quote identity-free as
   the conservative number.
3. **Coverage/label bias** — result conditional on the recoverable (posted-with-text) segment; document.
4. **Timing gaps** — recovery didn't store notice dates; use contract `signedDate` (FPDS, local) proxy.

## Deliverables
`scripts/phase3_benchmark/pc_fusion.py` — features + LambdaMART + GroupKFold; ablation table, feature
importances, precision@K with CI. Recorded to #423 (`claude/phase3-detection-phase0`).

## Data (all local — no new pulls)
Positives: 273 recovered notices / 165 firms (`pc_recover_combined.json`). Abstracts + firm identifiers:
`award_data.csv`. Agency/NAICS/date/sole-source per notice: FPDS coded XML (`data/raw/fpds/m0a_coded/`).
