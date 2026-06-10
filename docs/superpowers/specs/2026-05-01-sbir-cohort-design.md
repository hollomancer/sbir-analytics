# SBIR Cohort Design — Form D Filer vs Non-Filer

**Date:** 2026-05-01
**Branch:** `claude/sbir-cohort-design-agqKe`
**Research questions:** A4 (Form D private-placement fundraising profile;
private-to-SBIR leverage ratio; debt-vs-equity composition; offering fill rate)

## Goal

Define firm-level cohorts that support a descriptive comparison between
SBIR awardees that filed a Form D Notice of Exempt Offering and those
that did not. Output is a cohort specification — the definitions, the
quantitative confidence scoring, the labeled calibration set, and the
weighted metric formulas — that downstream analyses (filer share,
leverage ratio, fill-rate distribution, equity-vs-debt mix) consume.

This spec does not run the analysis. It produces the cohort artifact
(`data/sbir_cohorts.parquet`), the calibration model
(`data/form_d_calibration.json`), and the labeled holdout
(`data/form_d_calibration_labels.jsonl`).

## Context

Two data sources, both already wired into the pipeline:

1. **SBIR bulk award data** — `sbir_etl/extractors/sbir.py`,
   `validated_sbir_awards` Dagster asset. ~533K awards, 1983–present,
   42-column schema (UEI, DUNS, agency, phase, program, award_year,
   award_amount, state, etc.).
2. **Form D matches** — `sbir_etl/enrichers/sec_edgar/form_d_scoring.py`
   produces `FormDMatchConfidence` per candidate filing with a
   continuous `score ∈ [0,1]` composed of name / person / state /
   address / temporal / year-of-inc signals.

Documented data-quality constraints that drive the design:

- **Form D electronic filing started Q1 2009.** Pre-2009 raises are
  invisible. Universe must restrict to firms whose first SBIR award
  is on or after 2009 to avoid contaminating the Non-filer cohort with
  firms that raised privately before EDGAR digitized.
- **UEI did not exist before 2018.** 2018–2019 UEI/DUNS coverage is
  ~70%; pre-2018 is worse. Defining "firm" as "UEI" undercounts older
  firms; firm identity uses the existing entity-resolution cluster,
  with normalized-name + state as the fallback (matches the Form D
  pipeline's existing strategy).
- **Award date is ~50% missing globally.** Vintage bucketing uses
  `award_year` (more present), not `award_date`.
- **Match-confidence distribution is dominated by Low tier (54.3%);
  Medium is state-only (10.8%); High is 35%.** Raw score must be
  treated as ordinal until calibrated.

## Universe

One row per firm. Firm identity:

1. If the entity-resolution cluster ID is present on the award row,
   use it.
2. Else, use `(normalized_name, state)` as the fallback identifier
   (same normalization the Form D matcher applies in
   `text_normalization.normalize_name`).
3. Drop awards with no recoverable firm identity (record the count in
   the diagnostic output).

Inclusion filters:

- Firm has ≥1 SBIR award with `award_year ≥ 2009`.
- Firm has ≥1 award with non-null `award_amount > 0` (excludes
  metadata-only rows).

The `award_year < 2009` legacy population is retained as a separate
sensitivity slice — not part of the primary universe but reported for
context.

## Cohorts

Two primary, mutually exclusive, jointly exhaustive within the universe.

| Cohort | Definition |
|---|---|
| **C1 Filers** | `P_filer ≥ 0.5` after calibration |
| **C2 Non-filers** | `P_filer < 0.5` after calibration |

`P_filer` is computed per firm; see *Quantitative confidence scoring*
below. The 0.5 cutoff defines the binary cohort assignment for
display purposes only — every weighted metric uses the continuous
`P_filer` and does not depend on the cutoff.

### Stratifications

Applied to both cohorts so every comparison can be sliced.

| Stratum | Buckets |
|---|---|
| **Vintage** (first-award `award_year`) | `2009–2014` / `2015–2019` / `2020+` |
| **Agency posture** | dominant funder by award-count share ≥60%: `DoD-dominant` / `HHS-dominant` / `NSF-dominant` / `DOE-dominant` / `mixed-other` |
| **Phase ladder reached** | max phase observed: `P1-only` / `P2-reached` / `P3-reached` |
| **State** | retained as a dimension; no a-priori bins (long-tailed) |

The 60% agency-dominance threshold is a starting point. The audit task
(Tier 0 below) reports the histogram of dominant-agency share so the
threshold can be adjusted with evidence before downstream analysis runs.

## Quantitative confidence scoring

### Match-level score

`FormDMatchConfidence.score ∈ [0,1]` is the existing weighted sum in
`sbir_etl/enrichers/sec_edgar/form_d_scoring.py`. The weights are pinned
to the code at spec-acceptance commit; any change to the scoring logic
requires updating this spec so the cohort definition remains
reproducible.

### Firm-level filer probability

For firm `f` with candidate Form D matches `i ∈ M(f)` and per-match
scores `s_i`:

```
P_filer(f) = 1 - Π_{i ∈ M(f)} (1 - s_i')
```

where `s_i' = calibrate(s_i)` is the calibrated probability (see
below). For firms with `M(f) = ∅`, `P_filer(f) = 0`.

The noisy-OR form is the right Bayesian frame: a firm is a filer if
*any* of its candidate matches is a true match, and multiple weak
matches do corroborate. `max` is rejected because it discards
corroboration; `mean` is rejected because it punishes firms with one
strong + many weak hits.

### Calibration (option B: boundary-zone labeling)

Raw match `score` is heuristic. Calibrate to a probability via
isotonic regression on a labeled holdout drawn from the decision
boundary.

**Sampling protocol:**

- Draw 50 candidate firm–filing match pairs from the score band
  `0.4 ≤ score ≤ 0.7`.
- Stratified across vintage buckets (≥10 per bucket) to surface any
  vintage-specific drift in the scoring function.
- Each pair is labeled `is_match ∈ {0, 1}` by inspection of: filer
  name vs SBIR company name, related-persons list vs PI / contact
  names, issuer address vs SBIR company address, year-of-incorporation
  vs first-award year, jurisdiction-of-incorporation plausibility.

**Anchor pairs** (no labeling required, included to fix the endpoints):

- 25 random pairs with `score ≥ 0.85` labeled `1` (anchor high end)
- 25 random pairs with `score ≤ 0.20` labeled `0` (anchor low end)

This gives a 100-pair labeled set. Isotonic regression on (raw score
→ label) produces the calibration map. Output:

- `data/form_d_calibration_labels.jsonl` — the labeled pairs
- `data/form_d_calibration.json` — the fitted isotonic map +
  per-vintage Brier scores

If a vintage bucket's per-bucket Brier score is materially worse than
the others (>0.05 absolute gap), promote calibration to per-vintage
maps and re-run.

## Weighted cohort metrics

Every aggregate uses `w_f = P_filer(f)` per firm.

```
Filer share              = Σ_f w_f / N
Leverage ratio (firm)    = Σ_f w_f · sold_f      / Σ_f w_f · award_amount_f
Leverage ratio (program) = Σ_f w_f · sold_f      / Σ_f         award_amount_f
Median raise per filer   = weighted median of sold_f, weights w_f
Fill-rate distribution   = weighted distribution of (sold_f / offered_f), weights w_f
Equity share             = Σ_f w_f · equity_offering_f / Σ_f w_f · sold_f
506(b) vs 506(c) split   = Σ_f w_f · {506b}_f       / Σ_f w_f
First-award → first-Form-D lag = weighted percentiles, weights w_f
```

Per-firm `sold_f`, `offered_f`, `equity_offering_f` aggregate across
all candidate Form D filings for the firm, each weighted by its own
calibrated match score `s_i'`. This avoids a single low-confidence
filing inflating a firm's reported raise.

`offered_f = 0` is excluded from the fill-rate distribution. Filings
flagged `is_amendment = True` are deduplicated to the latest-by-date
within an `accession_number` family.

## Uncertainty reporting

For every headline metric, report three numbers:

1. **Point estimate** using calibrated `P_filer` and weighted formula above.
2. **Sensitivity band** at hard cutoffs `P_filer ≥ {0.5, 0.7, 0.9}`,
   binary cut, no weighting. Shows how much each result depends on
   the borderline zone.
3. **Bootstrap 95% CI** by resampling firms with replacement
   (`n_bootstrap = 1000`), recomputing the weighted metric per draw.

Headline metrics are: filer share (overall and per-stratum),
program-level leverage ratio, median raise, equity share.

## Diagnostics

Ship with the cohort artifact:

- `P_filer` histogram across the universe (overall and per-vintage).
- Mean `P_filer` by vintage bucket — surfaces structural undermatching
  (older firms appearing as Non-filers because of name drift, not
  because they didn't raise).
- Calibration plot: predicted bin-mean vs observed match rate on the
  labeled holdout.
- Per-signal contribution: of confirmed filers (`P_filer ≥ 0.9`), the
  share whose evidence included address-match, person-match,
  temporal-match, etc.
- Universe construction counts: awards processed, firms identified,
  pre-2009-first-award firms excluded, no-firm-identity awards
  dropped, agency-dominance histogram (drives the 60% threshold call).

## Output artifacts

| File | Contents |
|---|---|
| `data/sbir_cohorts.parquet` | One row per firm: identity columns, cohort label, `P_filer`, vintage bucket, agency posture, phase ladder reached, state, aggregated raise totals, contributing-match count, imputation provenance flags (see *Imputation interaction*) |
| `data/form_d_calibration_labels.jsonl` | Labeled match pairs (anchor + boundary-zone) |
| `data/form_d_calibration.json` | Fitted isotonic map, per-vintage Brier scores, calibration metadata |
| `reports/cohort_diagnostics.md` | Diagnostic plots and counts listed above |

## Imputation interaction

The data-imputation spec
(`specs/data-imputation/`, branch `claude/sbir-data-imputation-strategy-HEDC0`)
proposes per-row imputation of `award_date`, `award_amount`,
`company_uei`/`duns`, `congressional_district`, `contract_end_date`,
and `naics_code`, with non-destructive `raw_<field>` shadow columns,
per-row `<field>_is_imputed` booleans, and an `imputation` provenance
struct (field/method/method_version/confidence/source_fields).

This spec ships against raw `validated_sbir_awards`. When the
imputation work lands on `main`, three fields become useful for the
cohort artifact, one is a trap, and the rest are not consumed.

| Imputed field | Cohort use | Confidence gate |
|---|---|---|
| `award_date` | (a) `temporal_score` signal in the per-match score; (b) date-granular first-award → first-Form-D lag | Restrict to `confidence ∈ {high, medium}`. The low tier (FY-midpoint) is too coarse for daily-resolution temporal scoring. |
| `company_uei` / `duns` | Collapse same-firm awards across the 2018 UEI introduction in firm-identity construction | `confidence = high` only. `cross_award_backfill` is a deterministic match within the corpus; medium/low tiers do not exist for this method. |
| `award_amount` | **Excluded from the leverage-ratio denominator.** Imputing the denominator inside a metric biased toward agency-phase medians produces circular understatement of leverage. | Reported instead as a sensitivity slice that *excludes* firms whose total `award_amount` includes any imputed value. |
| `congressional_district`, `contract_end_date`, `naics_code` | Not consumed by the v1 cohort artifact. `naics_code` becomes useful if a sector-stratification axis is added later (currently out of scope). | — |

The cohort artifact passes through imputation provenance flags
(`award_date_is_imputed`, `uei_is_imputed`, `award_amount_is_imputed`)
per firm, set to `True` if any contributing award row carries the
flag. This keeps the diagnostic question *"which cohort labels depend
on imputed inputs?"* answerable without rerunning anything.

The imputation work does not eliminate the structural pre-2018
identity gap. `cross_award_backfill` only propagates UEIs that exist
*somewhere in the corpus*, so a 2010-only firm that never re-won
post-2018 retains no UEI and continues to use the name+state fallback.

## Out of scope

- Phase II → Phase III transition outcomes by capital posture
  (research question B; deferred — depends on transition detector
  outputs and would expand this spec into inferential territory).
- M&A exit linkage to filer cohort (research question A4 sub-question;
  served by the M&A detection spec, not this one).
- CET-area stratification (depends on CET classifier output;
  deferred).
- 1983–2008 legacy slice analysis. Retained as a sensitivity slice
  but not analyzed in the headline cohort report.

## Tasks

### Tier 0 — Data-quality audit (gates everything else)

- T0.1 Compute `award_year` presence rate by year (1983–present);
  confirm year-bucket usability.
- T0.2 Compute `award_amount > 0` rate, agency-dominance histogram,
  phase-ladder distribution across the universe.
- T0.3 Compute match-`score` distribution by vintage bucket; confirm
  no vintage has a degenerate score profile that breaks calibration.
- T0.4 Decide agency-dominance threshold from the histogram (default
  60%; revise if the distribution is bimodal at a different cut).

Output: `reports/cohort_universe_audit.md` plus a go/no-go on the
proposed buckets.

### Tier 1 — Universe construction

- T1.1 Build firm identity column on `validated_sbir_awards`
  (cluster ID → name+state fallback).
- T1.2 Aggregate awards to firm level: first-award year, max phase,
  dominant agency, total `award_amount`, state.
- T1.3 Apply universe filters; emit drop counts to the audit report.

### Tier 2 — Calibration

- T2.1 Sample 50 boundary-zone pairs (stratified by vintage) + 50
  anchor pairs (25 high, 25 low).
- T2.2 Hand-label boundary-zone pairs; record evidence per pair.
- T2.3 Fit isotonic regression; compute overall and per-vintage Brier
  scores. Promote to per-vintage maps if any bucket's Brier is >0.05
  worse than the median.
- T2.4 Persist `data/form_d_calibration.json`.

### Tier 3 — Cohort assembly

- T3.1 Compute per-firm `P_filer` via noisy-OR over calibrated
  match scores.
- T3.2 Aggregate per-firm raise totals (sold, offered, equity, debt,
  exemption split, 506(b)/(c) split) — each filing weighted by its
  own calibrated match score.
- T3.3 Assign cohort labels at `P_filer ≥ 0.5`; stamp stratification
  columns.
- T3.4 Emit `data/sbir_cohorts.parquet`.

### Tier 4 — Diagnostics

- T4.1 Render `P_filer` histograms (overall, per-vintage).
- T4.2 Render calibration plot.
- T4.3 Compute per-signal contribution decomposition.
- T4.4 Emit `reports/cohort_diagnostics.md`.

### Tier 5 — Acceptance

- T5.1 Verify universe count is reproducible from
  `validated_sbir_awards` (deterministic given input snapshot).
- T5.2 Verify calibration is reproducible (fixed random seed for
  bootstrap and for the labeled-pair sampling).
- T5.3 Spot-check 10 firms across cohorts and strata; confirm cohort
  labels and aggregated raise totals match raw evidence.

### Tier 6 — Imputation upgrade (deferred; gated on imputation spec landing on `main`)

Only runs after the data-imputation work lands. Measures the
imputation lift on the cohort, rather than assuming it.

- T6.1 Re-run universe construction (T1.1–T1.3) using *effective*
  `award_date` (high+medium tiers) and *effective* `company_uei`
  (high tier only). Keep `award_amount` at raw values.
- T6.2 Re-run calibration (T2.x) on the imputation-aware match
  scores; the `temporal_score` signal will activate on more rows.
- T6.3 Re-run cohort assembly (T3.x); pass `award_date_is_imputed`,
  `uei_is_imputed`, `award_amount_is_imputed` provenance flags
  through to `data/sbir_cohorts.parquet`.
- T6.4 Emit a delta report: universe size change, mean-`P_filer`
  shift, per-stratum filer-share shift, and a leverage-ratio
  sensitivity slice that excludes firms with any imputed
  `award_amount` contribution. Output:
  `reports/cohort_imputation_delta.md`.
