# Requirements — Fiscal Impact Sensitivity & NASEM Reconciliation

> **Status:** Not yet started. **Blocked on `specs/fiscal-tax-impact-v2.md` landing** —
> the D2 jurisdiction-separated tax estimates (BEA NIPA-derived rates) must be
> implemented before this D3 sensitivity layer can be computed.
> Anchors inventory question **D3** in [docs/research-questions.md](../../docs/research-questions.md).

**Research question anchor:** D3 — robustness of fiscal return estimates to parameter uncertainty; entity-resolution coverage reconciliation to NASEM; BEA NIPA vs. hardcoded rate comparison
**Answers for:** Treasury / OMB analysts, GAO reviewers, policy analysts benchmarking against NASEM
**Complexity tier:** Uncertainty & reconciliation (Tier 3)

---

## Done when

> A Treasury analyst preparing testimony can state: "Our base-case estimate of
> federal fiscal returns per SBIR dollar is $[X] ± $[Y] (95% sensitivity band).
> State-specific rates change the estimate by ±[Z]% vs. national averages.
> We reconcile to NASEM [L1][L2] as follows: our match rate covers [A]% of SBIR
> award dollars; adjusting for ER coverage closes [B] percentage points of any
> gap. The NIPA-derived rate estimate is within [C]% of the TechLink/IMPLAN-based
> benchmark [L19]."

---

## Introduction

The D2 fiscal impact pipeline (`sbir_etl/transformers/sbir_fiscal_pipeline.py`)
produces point estimates of federal, state, and local tax receipts from SBIR spending.
Point estimates are useful only when accompanied by uncertainty bounds that tell
analysts how sensitive the result is to parameter choices, data limitations, and
methodology differences vs. published benchmarks.

This spec implements three outputs:

1. **Sensitivity bands** — vary the key input parameters (BEA NIPA tax rates, BEA
   I-O multipliers, ER match rate coverage) over plausible ranges and report the
   resulting range of fiscal return estimates.

2. **NASEM reconciliation** — compare the pipeline estimate to TechLink [L19],
   NASEM [L1][L2], and IMPLAN-style benchmarks and attribute any divergence to
   specific methodology differences (time window, sector coverage, ER match rate).

3. **State-rate sensitivity** — quantify how much the national-average NIPA rate
   vs. state-specific rates (TX has no income tax; CA at 13.3%) changes state-by-state
   fiscal return estimates, completing the jurisdiction-separated D2 output.

**Dependency:** All three require the BEA NIPA-derived rate infrastructure from
`specs/fiscal-tax-impact-v2.md` (D2). Do not implement this spec until that work
has landed on `main`.

---

## User Stories

**As a Treasury analyst preparing OMB testimony on SBIR program ROI,** I want
sensitivity bands around the point-estimate fiscal return, so that I can state a
defensible range rather than a false-precision single figure when the Secretary asks
"how confident are we in that number?"

**As a policy analyst benchmarking against the NASEM / TechLink study [L19],** I
want a structured reconciliation that attributes any divergence to specific methodology
differences, so that I can explain to a GAO reviewer why our number differs from the
$39.4B tax-revenue figure in the 1995–2018 TechLink study — rather than leaving it
unexplained.

---

## Requirements

### Requirement 1 — Parameter sensitivity bands

**User Story:** As a Treasury analyst, I want fiscal return estimates computed over
a grid of plausible parameter values, so that I can report a sensitivity band rather
than a brittle point estimate.

#### Acceptance Criteria

1. THE System SHALL vary the following parameters over their plausible ranges and
   compute fiscal return estimates for each combination:
   - Federal effective income tax rate ± 2 percentage points around the NIPA central
     estimate (Table 3.2)
   - BEA I-O output multiplier ± 10% around the sector-level central estimate
   - Entity-resolution match rate coverage: 80%, 90%, 95%, 100% of award dollars matched
2. THE System SHALL report the resulting distribution of total-tax-receipt estimates as
   a 5th/25th/50th/75th/95th percentile table for each fiscal return metric.
3. THE System SHALL identify which parameter drives the widest sensitivity band, so
   analysts know where to focus data-quality investment.
4. THE System SHALL emit sensitivity results to
   `reports/fiscal-sensitivity/sensitivity_<period>.parquet` and a markdown summary
   to `reports/fiscal-sensitivity/sensitivity_<period>.md`.

### Requirement 2 — NASEM / TechLink reconciliation

**User Story:** As a policy analyst benchmarking against published studies, I want a
structured reconciliation report explaining divergence from NASEM / TechLink figures,
so that I can characterize methodology differences rather than leaving them unexplained.

#### Acceptance Criteria

1. THE System SHALL produce a reconciliation report documenting: measurement time window,
   sector coverage (NAICS sectors included / excluded), ER match rate and coverage
   qualifier, tax-rate source (NIPA tables vs. hardcoded), and I-O multiplier vintage.
2. WHEN the pipeline estimate of total federal tax receipts diverges from the TechLink
   [L19] benchmark by more than 20%, THE System SHALL identify which methodology
   difference accounts for the largest share of the gap.
3. THE System SHALL emit both a JSON artifact (for programmatic consumption) and a
   markdown summary to `reports/leverage-ratio/fiscal-reconciliation.md`, consistent
   with the report format in `specs/leverage-ratio-analysis/` Requirement 3.
4. THE System SHALL note explicitly that TechLink [L19] uses IMPLAN's proprietary
   I-O model while this pipeline uses BEA's publicly available tables — a methodological
   difference that may persist regardless of data quality.

### Requirement 3 — State-rate sensitivity

**User Story:** As a Treasury analyst reporting state-level fiscal returns, I want the
sensitivity of state tax receipt estimates to the choice of national-average vs.
state-specific rates, so that I can characterize how much the results change when
Texas (no income tax) or California (13.3% top rate) is treated distinctly.

#### Acceptance Criteria

1. THE System SHALL compute state-level tax receipt estimates under two scenarios:
   (a) national-average NIPA rate applied uniformly; (b) state-specific rates from
   `data/reference/tax/state_effective_rates.csv` (the Tax Foundation / Census ASGF
   table from `specs/fiscal-tax-impact-v2.md` Phase 3).
2. THE System SHALL compute the difference between scenario (a) and (b) for each
   state and rank states by absolute delta and relative delta.
3. THE System SHALL flag states where the national-average rate under- or over-states
   the state-specific estimate by more than 20% as **high-sensitivity jurisdictions**.
4. THE System SHALL note that state-specific rates require the Phase 3 data from
   `specs/fiscal-tax-impact-v2.md` to be available; when that file is absent,
   THE System SHALL fall back to national averages and emit a warning.
