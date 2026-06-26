# SBIR Federal Spending vs Form D Private Capital (2009-2024)

**Date:** 2026-04-23
**Methodology commit:** `f65abb89` (rule-based two-signal tiering + ZIP address matching)
**Field reference:** [form-d-data-dictionary.md](form-d-data-dictionary.md)
**DoD branch-level analysis:** [dod-form-d-leverage.md](dod-form-d-leverage.md)

> **Methodology appendices.** This doc folds in two methodology supplements that were previously separate companion notes: [Appendix A — Bootstrap confidence intervals](#appendix-a--bootstrap-confidence-intervals-pr-338) and [Appendix B — Pooled Investment Fund cross-link integrity audit](#appendix-b--pooled-investment-fund-cross-link-integrity-audit-pr-340).

## Methodology revision history

**2026-04-23 — commit [`f65abb89`](https://github.com/hollomancer/sbir-analytics/commit/f65abb89):**

- **What changed:** Replaced the weighted-composite confidence score with **rule-based two-signal tiering** (high = person ≥ 0.7 OR ZIP match; medium = state match; low = neither). Added ZIP-address matching as a parallel confirmation signal (motivation in the "HHS/NIH and Address Matching" section below). Added `EXCLUDED_INDUSTRY_GROUPS` (Pooled Investment Fund, Insurance, Restaurants, etc.) for false-positive prevention.
- **Net cohort impact (v1 → current):** High **2,212 → 3,640 (+65%)** · Medium 3,310 → 1,120 (−66%) · Low 4,883 → 5,645 (+16%). 2,844 records (27% of 10,405) changed tier under the new rule.
- **Address-signal-specific contribution:** 1,620 of the current high-tier records have ZIP as the deciding signal — i.e., they would have been medium or low under the new rule without the ZIP component. Detailed breakdown in the "HHS/NIH and Address Matching" section below.
- **Reproducibility:** The pre-change snapshot is preserved locally as `data/form_d_details_v1.jsonl` for verifying the methodology change. The file is gitignored under `/data/` (raw analysis output) and is regenerable by reverting `sbir_etl/enrichers/sec_edgar/form_d_scoring.py` to its pre-`f65abb89` state and re-running `scripts/data/fetch_form_d_details.py`.
- **Findings below are computed against the post-change (current) cohort.**

## Summary

For every $1 of federal SBIR funding, SBIR companies raised between
$1.82 and $2.37 in private capital via SEC Regulation D offerings,
depending on match confidence tier.

| Confidence Filter | Nominal Ratio | 95% Bootstrap CI | Companies |
|-------------------|---------------|-------------------|-----------|
| High + Medium | 2.37x | [2.10, 2.67] | 4,760 |
| High only | 1.82x | [1.65, 2.02] | 3,640 |

CIs are firm-level percentile bootstrap (1,000 iterations, seed 42) from PR #338 / [Appendix A](#appendix-a--bootstrap-confidence-intervals-pr-338), rounded to two decimal places for display (full-precision bounds: [1.650, 2.024] high-only, [2.100, 2.668] H+M). Both headlines are statistically distinguishable from 1.0x ("no leverage") and from each other; both are clearly distinguishable from NASEM's 4:1 benchmark.

These ratios measure a **different channel** than the commonly cited
NASEM 4:1 benchmark. NASEM measures follow-on *federal contracts* (FPDS);
this analysis measures *private capital* raised through Reg D filings.
The two are complementary, not comparable.

### Two ratio interpretations

The 1.82x headline uses *total federal SBIR program spending* ($50.98B) as the denominator. A complementary **per-matched-firm** ratio — Form D $ divided by SBIR $ only for firms with in-window SBIR awards — produces **9.48x [8.26, 10.85]** for the same high-tier cohort. Both are valid:

- **1.82x** ≈ "What fraction of total SBIR program spending is followed by Form-D-detected private capital across the matched-firm cohort?" (program-wide ROI framing.)
- **9.48x** ≈ "For SBIR awardees who go on to attract private capital, what's their leverage per SBIR dollar received?" (per-firm leverage framing.)

The denominator gap explains the 5× difference: the program total includes ~$42B going to SBIR firms with no Form D activity at all. See [Appendix A](#appendix-a--bootstrap-confidence-intervals-pr-338) for the full methodology comparison.

## Methodology

**SBIR data**: Bulk awards download from sbir.gov (219K awards). Federal
spending = sum of `Award Amount` by `Award Year`.

**Form D data**: SEC EDGAR Form D XML filings matched to SBIR companies
via company name fuzzy matching, with confidence scoring based on
PI-to-executive name matching, address matching, and state overlap.
Private capital = `totalAmountSold` (actual capital accepted by
investors), not `totalOfferingAmount` (intended raise target).

**Confidence tiers** (rule-based, two independent confirmation signals):
- **High**: PI name matches a Form D executive (person_score >= 0.7)
  OR SBIR ZIP code matches Form D issuer ZIP — 3,640 companies
- **Medium**: Neither person nor address match, but SBIR state matches
  Form D state — 1,120 companies
- **Low**: No confirming signal beyond name match, excluded from
  analysis — 5,645 companies

Address matching was added to address a structural limitation of
person matching for HHS/NIH companies, where the SBIR PI is often
an academic researcher who does not appear as an officer on the
company's Form D filing. See "HHS/NIH and Address Matching" below.

**Industry group exclusions**: Offerings in industry groups structurally
incompatible with SBIR companies are excluded: Insurance, Lodging and
Conventions, Other Travel, Pooled Investment Fund, Restaurants, Retailing,
Tourism and Travel Services. Pooled Investment Fund entities (520 companies,
92% low-tier) are VC/PE fund vehicles, not operating company raises;
[PR #340](https://github.com/hollomancer/sbir-analytics/pull/340)
quantified ~100 cross-links from PIFs to operating-co SBIR matches via
shared persons/CIKs and found the at-risk exposure is **$151M (0.16% of
high-only headline)** — well below the bootstrap CI noise floor. See
[Appendix B](#appendix-b--pooled-investment-fund-cross-link-integrity-audit-pr-340) for the audit
methodology (added by PR #340). The cross-link list is best treated as a
starting point for investor → portfolio relationship mapping, not as a
methodology bias to correct.

**Exclusions**: 2025 excluded (partial year for both SBIR awards and
Form D filings).

## Results — SBIR vs Private Capital by Year

| Year | SBIR Federal | Form D (H+M) | Ratio (H+M) | Form D (High) | Ratio (High) |
|------|-------------|--------------|-------------|---------------|-------------|
| 2009 | $2.39B | $3.27B | 1.37x | $2.36B | 0.99x |
| 2010 | $2.60B | $10.94B | 4.22x | $3.34B | 1.29x |
| 2011 | $2.31B | $4.84B | 2.09x | $3.40B | 1.47x |
| 2012 | $2.27B | $4.07B | 1.79x | $3.13B | 1.38x |
| 2013 | $2.13B | $4.00B | 1.88x | $2.74B | 1.29x |
| 2014 | $2.34B | $4.96B | 2.12x | $3.84B | 1.64x |
| 2015 | $2.50B | $5.61B | 2.24x | $4.68B | 1.87x |
| 2016 | $2.68B | $5.04B | 1.88x | $3.89B | 1.45x |
| 2017 | $3.19B | $7.74B | 2.43x | $4.95B | 1.55x |
| 2018 | $2.85B | $7.81B | 2.74x | $6.91B | 2.43x |
| 2019 | $3.82B | $7.22B | 1.89x | $5.96B | 1.56x |
| 2020 | $3.96B | $8.63B | 2.18x | $7.39B | 1.87x |
| 2021 | $3.84B | $17.77B | 4.63x | $15.18B | 3.96x |
| 2022 | $4.49B | $10.34B | 2.30x | $9.23B | 2.06x |
| 2023 | $4.72B | $8.44B | 1.79x | $7.49B | 1.59x |
| 2024 | $4.90B | $9.93B | 2.02x | $8.43B | 1.72x |
| **Total** | **$50.97B** | **$120.61B** | **2.37x** | **$92.96B** | **1.82x** |

## Debt vs Equity Composition

SBIR companies have steadily shifted from debt to equity financing over
the 2009-2024 period. Debt's share of dollar volume dropped from 21% in
2009 to 6% in 2024, reaching a floor of 3% in 2021 (peak VC boom year).

| Year | Equity % | Debt % |
|------|----------|--------|
| 2009 | 79% | 21% |
| 2010 | 87% | 13% |
| 2011 | 82% | 18% |
| 2012 | 76% | 24% |
| 2013 | 81% | 19% |
| 2014 | 87% | 13% |
| 2015 | 87% | 13% |
| 2016 | 87% | 13% |
| 2017 | 92% | 8% |
| 2018 | 93% | 7% |
| 2019 | 90% | 10% |
| 2020 | 90% | 10% |
| 2021 | 97% | 3% |
| 2022 | 89% | 11% |
| 2023 | 92% | 8% |
| 2024 | 94% | 6% |
| **Overall** | **90%** | **10%** |

Percentages are share of equity + debt dollar volume only (excludes
offerings with neither type tagged). An offering can include both
equity and debt securities.

### Instrument combinations

The most common offering structures (high+medium tier, excluding
filtered industry groups):

| Structure | Share | Interpretation |
|-----------|-------|----------------|
| Equity alone | 53% | Standard VC/angel equity round |
| Debt + options | 10% | Convertible note with warrants (early-stage bridge) |
| Equity + options | 9% | Preferred equity with warrants (standard VC) |
| Debt alone | 8% | Pure debt — revenue-based or equipment financing |

### Sector comparison

Debt vs equity split is remarkably uniform across SBIR funding agencies.
HHS (bio/health), DoD (defense), NSF, and DOE all show 65-70% equity-only
offerings. The smaller agencies diverge slightly: Agriculture skews more
debt (25%), EPA is the most debt-heavy (31% debt-only).

## Offering Fill Rate (Offered vs Sold)

SBIR companies offered $172B in aggregate and actually sold $120.6B —
a **70% fill rate**. The $51B gap represents unmet capital demand.

| Year | Offered | Sold | Fill Rate |
|------|---------|------|-----------|
| 2009 | $5.2B | $3.3B | 64% |
| 2010 | $13.4B | $10.9B | 81% |
| 2011 | $9.0B | $4.8B | 54% |
| 2012 | $8.5B | $4.1B | 48% |
| 2013 | $8.2B | $4.0B | 49% |
| 2014 | $9.1B | $5.0B | 55% |
| 2015 | $10.1B | $5.6B | 56% |
| 2016 | $7.6B | $5.0B | 67% |
| 2017 | $11.1B | $7.7B | 70% |
| 2018 | $10.5B | $7.8B | 74% |
| 2019 | $9.7B | $7.2B | 74% |
| 2020 | $11.3B | $8.6B | 76% |
| 2021 | $20.5B | $17.8B | 87% |
| 2022 | $13.4B | $10.3B | 77% |
| 2023 | $11.5B | $8.4B | 73% |
| 2024 | $12.8B | $9.9B | 77% |
| **Total** | **$172.0B** | **$120.6B** | **70%** |

The fill rate tracks VC market conditions closely: 48% at the
post-financial-crisis trough (2012), 87% at the 2021 peak, stabilizing
at 73-77% post-correction. Per-offering median fill rate is 80%, but
the 25th percentile is 45% — a quarter of offerings close less than
half their target.

## Private Capital by SBIR Agency

### Aggregate ratio (total Form D $ / total SBIR $)

| Agency | SBIR $ | FD (H+M) | Ratio (H+M) | FD (High) | Ratio (High) | % cos w/ FD (H+M) |
|--------|--------|----------|-------------|-----------|-------------|-------------------|
| NSF | $2.5B | $13.6B | 5.54x | $8.7B | 3.54x | 16% |
| USDA | $0.4B | $2.1B | 5.16x | $1.9B | 4.60x | 11% |
| DHS | $0.3B | $1.1B | 3.86x | $1.0B | 3.47x | 7% |
| NASA | $2.7B | $9.4B | 3.51x | $2.9B | 1.07x | 6% |
| HHS | $16.0B | $50.7B | 3.16x | $42.6B | 2.66x | 27% |
| Commerce | $0.2B | $0.5B | 2.52x | $0.5B | 2.35x | 6% |
| DOE | $4.0B | $7.4B | 1.85x | $6.3B | 1.57x | 10% |
| DoD | $24.5B | $35.0B | 1.43x | $28.5B | 1.16x | 17% |

Per-agency bootstrap CIs (PR #338 / [Appendix A](#appendix-a--bootstrap-confidence-intervals-pr-338)) reveal substantial heterogeneity. Highlights for the high-only column: **DoD 1.011x [0.842, 1.214]** (statistically distinguishable from the cross-agency average and from HHS / NSF / USDA at 95%; CI overlaps with DoE / NASA / DHS / Commerce / EPA — see DoD finding in the bootstrap doc); **NSF 3.230x [2.600, 4.016]**; **HHS 2.360x [2.059, 2.674]**. Small-cohort agencies (Commerce, DHS, NASA, EPA, USDA) have wide CIs (typical span ~3-10×) — quoting their per-agency point estimates without CI overstates precision.

NSF leads at 5.54x (H+M) / 3.54x (high-only). HHS — previously
the weakest agency in high-only (0.70x with person matching alone) —
now shows 2.66x after address matching recovered companies where the
PI is an academic collaborator rather than a company officer.

### Key agency findings

- **HHS has the highest Form D participation rate** (27% of companies)
  and the largest absolute Form D volume ($50.7B H+M). Address matching
  was critical for HHS — it promoted 1,176 companies from medium to
  high tier.
- **DoD has the lowest ratio** (1.43x H+M / 1.16x high) despite the
  largest SBIR budget. Only 17% of DoD companies raise private capital.
- **NSF punches above its weight** at 5.54x — smaller SBIR awards
  (lower denominator) combined with 16% Form D participation.

## Observations

1. **High-only ratio of 1.82x** is the headline number. For every $1
   of federal SBIR, companies with confirmed matches (person OR address)
   raised $1.82 in private Reg D capital.

2. **H+M ratio is stable at ~2.0-2.5x** across most years, with outliers
   in 2010 (4.22x) and 2021 (4.63x) — both VC boom years.

3. **High-only ratio trends upward** from ~1.0x (2009) to ~1.7x (2024),
   suggesting growing private capital flows to SBIR companies over time.

4. **Debt-to-equity shift** mirrors the broader venture market. As VC
   funding expanded post-2010, SBIR companies gained access to equity
   capital that was previously unavailable to deep-tech startups.

5. **This is not comparable to NASEM's 4:1.** NASEM measures follow-on
   federal contracts (FPDS data). This measures private Reg D capital.
   The two funding channels are additive — SBIR companies access both.

## HHS/NIH and Address Matching

Person matching — the original primary signal for high-tier assignment —
is structurally weaker for HHS/NIH-funded SBIR companies. Before
address matching was added, only 18% of HHS high+medium companies
were high-tier, vs 52-67% for every other agency.

**Root cause**: 88% of person-based high-tier matches are
PI → Executive Officer. For DoD/NSF, the SBIR PI is typically the
company founder/CTO who appears on the Form D as an officer. For
HHS/NIH, the PI is often a university researcher (8.5% have `.edu`
emails; many more are academic with non-institutional email) who
collaborates on the SBIR grant but is not an officer of the
commercializing company.

**Solution**: ZIP code matching between the SBIR company address and
the Form D issuer address provides a PI-independent confirmation
signal. Both data sources have 100% address coverage. ZIP matching
validates at high rates for genuine matches (70% for HHS high-tier,
67% for HHS medium-tier) and at 0% for low-tier (false positives),
confirming its discriminative power.

**Impact**: Address matching promoted 1,620 companies from medium
to high tier (1,617 medium → high, 3 low → high). HHS high-only
ratio improved from 0.70x to 2.66x. The gap between high-only
(1.82x) and H+M (2.37x) is now narrow, meaning the remaining
medium tier (1,120 companies) is genuinely uncertain rather than
a large bucket of unconfirmed matches.

## Caveats

- **Medium tier includes some false positives.** These are state-match-only
  records without person or address confirmation. The true ratio likely
  falls between the high-only (1.82x) and H+M (2.37x) bounds — a
  much narrower range than before address matching (0.88x to 2.37x).

- **Form D captures only Reg D private placements.** Public offerings,
  bank debt, grants, and revenue are not included.

- **Multiple Form D filings per company.** Companies that raise capital
  in multiple rounds have each offering counted in its filing year.
  This is correct for annual flow analysis but means the same company
  contributes to multiple years.

- **totalAmountSold is self-reported.** SEC does not independently verify
  the amounts reported in Form D filings.

- **Pooled Investment Funds excluded.** Fund vehicles matched to SBIR
  company names are excluded from totals. ~100 PIF→operating-co
  cross-links via shared persons/CIKs exist
  ([PR #340](https://github.com/hollomancer/sbir-analytics/pull/340)
  added the audit; see [Appendix B](#appendix-b--pooled-investment-fund-cross-link-integrity-audit-pr-340) for
  methodology). The audit quantified the at-risk operating-co exposure
  at $151M (0.16% of high-only headline), well below the bootstrap CI
  noise floor. Treat the cross-link list as a starting point for
  investor → portfolio relationship mapping, not as a bias correction.

---

## Appendix A — Bootstrap confidence intervals (PR #338)

**Date:** 2026-06-20
**Script:** [`scripts/data/bootstrap_form_d_leverage_ci.py`](../../scripts/data/bootstrap_form_d_leverage_ci.py)

This appendix folds in the methodology supplement (previously `form-d-leverage-bootstrap-findings.md`) that adds **95% bootstrap confidence intervals at the firm level** to the headline ratios above, reproduces both headline numbers exactly, and surfaces two findings that change how readers should interpret the headline:

1. **The denominator choice is doing a lot of work.** The headline ratio uses *total federal SBIR program spending* ($50.98B) as the denominator. A complementary **per-matched-firm** ratio — Form D $ divided by SBIR $ for firms that actually match in Form D (restricted to firms with in-window SBIR awards) — comes out to **9.48x [8.26, 10.85]** for the high-tier cohort. Neither number is wrong; they answer different policy questions (see "Two ratio interpretations" above).
2. **DoD's leverage ratio is essentially 1:1 with a tight CI.** Among large-cohort agencies, **DoD is 1.011x [0.842, 1.214]** at the program level — statistically distinguishable from the cross-agency average and from NSF's 3.23x. This is a real finding worth understanding rather than a small-sample artifact. The branch decomposition lives in [dod-form-d-leverage.md](dod-form-d-leverage.md).

### Method

Firm-level bootstrap with 1,000 iterations. Each iteration draws N firms with replacement from the cohort of size N, then recomputes the aggregate ratio sum(Form D $) / sum(SBIR $). RNG seed 42 for reproducibility.

Resampling at the firm level (not the offering, not the year) is the right unit because the leverage ratio is fundamentally a per-firm quantity. Within-firm offering correlation is correctly handled (a firm contributes its total to numerator and denominator each iteration). Offering-level resampling would produce artificially narrow CIs.

For the **program-level ratio**, the denominator is held fixed at the program total ($50.98B). The CI reflects only numerator variability — i.e., variability in which matched firms are in the cohort sample. For the **per-matched-firm ratio**, both numerator and denominator are recomputed from the resample.

Filters match the published doc exactly: tier (`high` or `high+medium`), year window (2009-2024 by `filing_date` and `Award Year`), and `EXCLUDED_INDUSTRY_GROUPS` (Pooled Investment Fund, Insurance, Restaurants, etc.) applied at the offering level.

### Headline results

#### Doc-cohort: all matched firms (reproduces the headline tables)

| Cohort | Firms | Form D $B | Program SBIR $B | Program-level (95% CI) |
|---|---|---|---|---|
| High only | 3,640 | 92.96 | 50.98 | **1.824x** [1.650, 2.024] |
| High + Medium | 4,760 | 120.61 | 50.98 | **2.366x** [2.100, 2.668] |

Exact reproduction of the published 1.82x / 2.37x. The CIs are reasonably tight — high-only is statistically distinguishable from 1.5x and from 2.1x at the 95% level.

#### Per-matched-firm: inner-join with SBIR awards in window

| Cohort | Firms | Form D $B | Matched SBIR $B | Program-level (95% CI) | Per-matched-firm (95% CI) |
|---|---|---|---|---|---|
| High only | 3,236 | 82.35 | 8.69 | 1.615x [1.447, 1.786] | **9.476x** [8.256, 10.845] |
| High + Medium | 3,996 | 97.75 | 10.53 | 1.918x [1.735, 2.126] | **9.282x** [8.173, 10.533] |

The inner-join drops 404 firms (high-tier) whose SBIR awards fall outside 2009-2024 but whose Form D filings are in window. Their Form D $ accounts for the gap between the doc cohort's $92.96B and the inner-join cohort's $82.35B.

#### Per-agency program-level leverage (high-only)

| Agency | Firms (w/ Form D) | Program $B | Form D $B | Program-level (95% CI) | Per-firm (95% CI) |
|---|---|---|---|---|---|
| **DoD** | 931 (859) | 24.50 | 24.77 | **1.011x [0.842, 1.214]** | 7.095x [5.50, 9.20] |
| HHS | 1,241 (1,190) | 16.03 | 37.84 | 2.360x [2.059, 2.674] | 9.738x [8.34, 11.32] |
| DOE | 169 (154) | 4.01 | 5.98 | 1.492x [0.754, 2.755] | 11.128x [5.06, 23.92] |
| NASA | 62 (57) | 2.68 | 3.01 | 1.126x [0.344, 2.466] | 26.494x [7.39, 65.18] |
| **NSF** | 677 (631) | 2.46 | 7.93 | **3.230x [2.600, 4.016]** | 14.666x [11.68, 18.26] |
| USDA | 73 (63) | 0.41 | 1.20 | 2.915x [1.630, 4.427] | 22.581x [12.36, 36.57] |
| DHS | 20 (18) | 0.29 | 0.99 | 3.481x [0.639, 7.500] | 40.376x [6.25, 122.88] |
| Commerce | 19 (19) | 0.19 | 0.45 | 2.322x [0.461, 5.023] | 44.958x [8.78, 102.09] |
| **Education** | 22 (21) | 0.16 | 0.04 | **0.226x [0.127, 0.346]** | 1.559x [0.76, 2.92] |
| **Transportation** | 4 (4) | 0.16 | 0.00 | **0.009x [0.008, 0.010]** | 0.460x [0.27, 1.14] |
| EPA | 18 (17) | 0.08 | 0.12 | 1.467x [0.600, 2.568] | 23.549x [9.98, 44.18] |

### What the CIs reveal

#### Headline 1.82x is statistically robust, but the framing hides a methodological choice

The 1.82x point estimate is tightly bracketed [1.650, 2.024]: under firm-level resampling, the headline is clearly distinguishable from 1.0x ("no leverage") and from 2.5x. The published number isn't a noisy estimate.

But the headline interpretation depends on a methodological choice. The denominator is *total program SBIR spending*, including the ~$42B going to SBIR firms with no Form D activity at all. From a "what's the per-firm leverage SBIR achieves when it leads to private capital" perspective, the relevant number is closer to **9.48x [8.26, 10.85]** — a different headline entirely. Both numbers matter but answer different policy questions (program-wide ROI vs investor/founder-track leverage).

#### DoD's 1.011x is the most policy-significant finding

DoD is the largest SBIR funder ($24.50B in window, 48% of total program) but its program-level leverage is **essentially 1:1** with a tight CI [0.842, 1.214]. The CI does NOT include 1.5x or higher. This is statistically clean (859 DoD firms with Form D, narrow CI), distinguishable from HHS (2.360x [2.059, 2.674]) and NSF (3.230x [2.600, 4.016]) at the 95% level, and far below NASEM's 4:1 finding (which measures non-SBIR DoD-federal follow-on, a different channel). The four candidate explanations this raised are decomposed and resolved in [dod-form-d-leverage.md](dod-form-d-leverage.md).

#### NSF leads at 3.23x with credible bounds

NSF's program-level leverage [2.600, 4.016] is the highest among large-cohort agencies. The upper bound brushes against NASEM's 4:1 benchmark. NSF's small SBIR award sizes combined with relatively high Form D participation rate (16%) are the mechanism.

#### Education and Transportation are essentially zero

ED at 0.226x [0.127, 0.346] and DOT at 0.009x [0.008, 0.010] both have tight CIs around near-zero values. These agencies' SBIR programs produce essentially no Form D follow-on activity.

#### Small-cohort agency CIs are very wide and shouldn't be quoted

Commerce, DHS, NASA, EPA, USDA all have wide CIs reflecting the small number of matched firms. Quoting "USDA's 2.92x leverage" as a point estimate without [1.630, 4.427] CI overstates precision by a large factor.

### What this appendix doesn't address

CIs quantify **sampling uncertainty only**. They do NOT capture: measurement error in `total_amount_sold` (self-reported, est. 5-15% additional noise); SBIR ↔ Form D matching error (probabilistic confidence scoring; false positives screened by tier filter but not eliminated); the "in-window SBIR" filtering decision; or selection effects in Form D filing (firms raising via bank debt, revenue, bootstrap, or public offerings are not represented). The realistic credibility margin is wider than the 95% bootstrap bounds suggest.

### Reproducibility

```bash
.venv/bin/python scripts/data/bootstrap_form_d_leverage_ci.py
```

Default config: 1,000 iterations, seed 42, window 2009-2024, inputs `data/form_d_details.jsonl` + `data/raw/sbir/award_data.csv`. Outputs to `reports/ml/form_d_leverage_ci.{json,md}` (gitignored). Self-contained, numpy only, runs in ~5 seconds.

---

## Appendix B — Pooled Investment Fund cross-link integrity audit (PR #340)

**Date:** 2026-06-21
**Script:** [`scripts/data/audit_form_d_pif_cross_links.py`](../../scripts/data/audit_form_d_pif_cross_links.py)

This appendix folds in the integrity audit (previously `form-d-pif-cross-link-audit.md`). The disclaimer above references cross-links between Pooled Investment Fund (PIF) entities and operating-company SBIR matches via shared `related_persons` or CIK. PIF entities are excluded from cohort totals via `EXCLUDED_INDUSTRY_GROUPS`, but the disclaimer raised an open question: do those cross-links indicate that some counted operating-company matches might be inflated or false-positive?

**This audit quantifies the answer: no material methodology risk.**

- **97 cross-link pairs** found in current data (vs. the disclaimer's 71 — drift from snapshot timing or a stricter filter at the time; same concept).
- **35 distinct high-tier operating cos** are cross-linked to PIFs, contributing **$1.551B counted (1.67% of high-only $92.96B headline)**.
- **Only 9 of those 35 ops ($151M = 0.16% of headline) are "at-risk"** — i.e., their high-tier match relies on the person signal AND has no ZIP-match backup.
- **26 of 35 (74%) are fully safe** — either both signals confirm, or ZIP confirms independently.
- **At-risk exposure is well below the bootstrap CI noise floor** (high-only CI is [1.65, 2.02]).

The cross-link list itself is an *underexploited asset*, not a bias risk: it identifies legitimate investor → portfolio relationships (fund partners serving on operating-company boards) worth mapping for separate analysis.

### Method

A cross-link is one (PIF, operating-co) pair where: the PIF record has only Pooled-Investment-Fund-tagged offerings (pure PIF); the operating co has at least one non-PIF offering (so it appears in cohort totals); and they share a `related_persons.name` (normalized: trim + uppercase) OR a `cik`. Cross-links to LOW-tier ops are excluded because low-tier records are dropped from cohort totals already.

For each HIGH-tier cross-linked op, classify its tier-confirmation robustness:

| Profile | Definition | Risk |
|---|---|---|
| Both signals | person_score ≥ 0.7 AND zip_match | None — two independent signals |
| ZIP-only | zip_match=1, person_score < 0.7 | None — ZIP independent of cross-link person |
| Person-only (at-risk) | person_score ≥ 0.7, no zip_match | At-risk if cross-link person is the deciding signal |
| Neither full | low scores | Shouldn't happen at high tier; investigate |

### Results

#### Tier distribution

| Op tier | Cross-link rows | Distinct ops |
|---|---|---|
| High | 42 | 35 |
| Medium | 9 | ~7 |
| Low | 46 | excluded already |

#### Headline impact

| Cohort | Counted $ from cross-linked ops | Headline | % of headline |
|---|---|---|---|
| High-only | $1.551B | $92.96B | **1.67%** |
| High + Medium | ~$3.0B | $120.61B | **~2.49%** |
| **At-risk subset (high)** | **$151M** | **$92.96B** | **0.16%** |

#### High-tier op robustness profile

| Profile | # distinct ops | Risk |
|---|---|---|
| Both person AND ZIP confirm | 8 | None |
| ZIP confirms (person<0.7) | 18 | None |
| **Person confirms only (no ZIP)** | **9** | **At-risk** |
| Neither full signal | 0 | (didn't occur) |

#### At-risk operating cos (9 total, $151M aggregate)

| Op company | Counted $ |
|---|---|
| Checkerspot | $78.3M |
| TRUE ANOMALY | $23.6M |
| Lionano | $22.7M |
| 3AM INNOVATIONS | $9.0M |
| PolySpectra | $8.4M |
| Dnalite Therapeutics | $5.6M |
| Construction Robotics | $2.2M |
| AQUANANO | $0.9M |
| Grid7 | $0.5M |

These are *probably* legitimate matches (a founder serving on both an operating co and an investor fund's board is normal in VC ecosystems) but the matching methodology can't verify without manual review.

#### Top shared names

| Name | # cross-links |
|---|---|
| MARC GOLDBERG | 9 |
| ROBERT CUNNINGHAM | 6 |
| FANG ZHENG | 6 |
| DAKIN SLOSS | 6 |
| N/A N/A | 4 |
| DAVID BROWN | 4 |
| CHARLES LANNON | 4 |
| KIRK NIELSEN | 4 |

These are mostly real, identifiable individuals — fund partners who also serve as board members or executive officers of operating companies. Expected ecosystem behavior, not a methodology bug.

### Interpretation

The cross-link concern is real conceptually but small in dollar terms. The 0.16% at-risk exposure is well below the [1.65, 2.02] high-only bootstrap CI band — the cross-link uncertainty is already absorbed into the existing CI margin.

1. **No methodology change is needed.** The matching pipeline correctly excludes PIF entities from totals, and the residual cross-link exposure on the operating-co side is below noise.
2. **The caveat language was conservative.** Reframing from "71 cross-links identified for future investor-relationship mapping" to "~100 cross-links identified; quantified at $151M (0.16%) at-risk exposure" more accurately characterizes the methodology risk.
3. **The real opportunity is investor-relationship mapping.** Of the 35 distinct high-tier cross-linked ops, most have legitimate VC-partner-as-board-member overlap. Mapping which PIF invests in which SBIR firm would be a useful follow-on for the F-area research questions, *not* a bias correction.

### Reproducibility

```bash
.venv/bin/python scripts/data/audit_form_d_pif_cross_links.py
```

Default config: inputs `data/form_d_details.jsonl`, year window 2009-2024, hardcoded high-only and H+M headline numbers from this doc. Outputs `reports/ml/form_d_pif_cross_links.{json,md}` (gitignored). Runs in <1s.
