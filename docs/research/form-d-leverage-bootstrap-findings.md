# Form D leverage ratio — bootstrap confidence intervals

**Date:** 2026-06-20
**Companion to:** [sbir-form-d-fundraising-analysis.md](sbir-form-d-fundraising-analysis.md) (the published headline finding)
**Script:** [`scripts/data/bootstrap_form_d_leverage_ci.py`](../../scripts/data/bootstrap_form_d_leverage_ci.py)

## Summary

The published doc reports headline private-capital leverage ratios as point estimates: **1.82x** for the high-confidence cohort and **2.37x** for high+medium. This analysis adds **95% bootstrap confidence intervals at the firm level**, reproduces both headline numbers exactly, and surfaces two findings that change how readers should interpret the headline:

1. **The denominator choice is doing a lot of work.** The doc's ratio uses *total federal SBIR program spending* ($50.98B) as the denominator. A complementary **per-matched-firm** ratio — Form D $ divided by SBIR $ for firms that actually match in Form D (restricted to firms with in-window SBIR awards) — comes out to **9.48x [8.26, 10.85]** for the high-tier cohort. Neither number is wrong; they answer different policy questions. The doc doesn't currently flag this.
2. **DoD's leverage ratio is essentially 1:1 with a tight CI.** Among large-cohort agencies, **DoD is 1.011x [0.842, 1.214]** at the program level — statistically distinguishable from the cross-agency average and from NSF's 3.23x. This is a real finding worth understanding rather than a small-sample artifact.

## Method

Firm-level bootstrap with 1,000 iterations. Each iteration draws N firms with replacement from the cohort of size N, then recomputes the aggregate ratio sum(Form D $) / sum(SBIR $). RNG seed 42 for reproducibility.

Resampling at the firm level (not the offering, not the year) is the right unit because the leverage ratio is fundamentally a per-firm quantity. Within-firm offering correlation is correctly handled (a firm contributes its total to numerator and denominator each iteration). Offering-level resampling would produce artificially narrow CIs.

For the **program-level ratio**, the denominator is held fixed at the program total ($50.98B). The CI reflects only numerator variability — i.e., variability in which matched firms are in the cohort sample. For the **per-matched-firm ratio**, both numerator and denominator are recomputed from the resample.

Filters match the published doc exactly: tier (`high` or `high+medium`), year window (2009-2024 by `filing_date` and `Award Year`), and `EXCLUDED_INDUSTRY_GROUPS` (Pooled Investment Fund, Insurance, Restaurants, etc.) applied at the offering level.

## Headline results

### Doc-cohort: all matched firms (reproduces published doc)

| Cohort | Firms | Form D $B | Program SBIR $B | Program-level (95% CI) |
|---|---|---|---|---|
| High only | 3,640 | 92.96 | 50.98 | **1.824x** [1.650, 2.024] |
| High + Medium | 4,760 | 120.61 | 50.98 | **2.366x** [2.100, 2.668] |

Exact reproduction of the published 1.82x / 2.37x. The CIs are reasonably tight — high-only is statistically distinguishable from 1.5x and from 2.1x at the 95% level.

### Per-matched-firm: inner-join with SBIR awards in window

| Cohort | Firms | Form D $B | Matched SBIR $B | Program-level (95% CI) | Per-matched-firm (95% CI) |
|---|---|---|---|---|---|
| High only | 3,236 | 82.35 | 8.69 | 1.615x [1.447, 1.786] | **9.476x** [8.256, 10.845] |
| High + Medium | 3,996 | 97.75 | 10.53 | 1.918x [1.735, 2.126] | **9.282x** [8.173, 10.533] |

The inner-join drops 404 firms (high-tier) whose SBIR awards fall outside 2009-2024 but whose Form D filings are in window. Their Form D $ accounts for the gap between the doc cohort's $92.96B and the inner-join cohort's $82.35B.

### Per-agency program-level leverage (high-only)

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

## What the CIs reveal

### Headline 1.82x is statistically robust, but the headline framing hides a methodological choice

The 1.82x point estimate is tightly bracketed [1.650, 2.024]: under firm-level resampling, the headline is clearly distinguishable from 1.0x ("no leverage") and from 2.5x. The published number isn't a noisy estimate.

But the headline interpretation depends on a methodological choice the doc doesn't flag. The denominator is *total program SBIR spending*, including the ~$42B going to SBIR firms with no Form D activity at all. From a "what's the per-firm leverage SBIR achieves when it leads to private capital" perspective, the relevant number is closer to **9.48x [8.26, 10.85]** — a different headline entirely.

Both numbers matter, but they answer different policy questions:
- **1.82x ≈** "How much Form-D-detected private capital flows back to the SBIR-firm cohort per dollar of total program spending?" (Useful for: program-wide ROI framing, Congressional appropriations debates.)
- **9.48x ≈** "For SBIR awardees who go on to attract private capital (filtered to firms with in-window SBIR awards), what's their leverage?" (Useful for: investor/founder-track program design, Howell-style replication targets.)

The published doc should either (a) report both, or (b) make the methodological choice explicit so readers don't misread 1.82x as "the per-firm SBIR leverage."

### DoD's 1.011x is the most policy-significant finding

DoD is the largest SBIR funder ($24.50B in window, 48% of total program) but its program-level leverage is **essentially 1:1** with a tight CI [0.842, 1.214]. The CI does NOT include 1.5x or higher. This is:

- Statistically clean (859 DoD firms with Form D, narrow CI)
- Distinguishable from HHS (2.360x [2.059, 2.674]) at the 95% level
- Distinguishable from NSF (3.230x [2.600, 4.016]) at the 95% level
- **Far below NASEM's 4:1 finding** (which measures non-SBIR DoD-federal follow-on, not private capital, but is the relevant benchmark for "DoD SBIR commercialization leverage")

Several candidate explanations worth distinguishing in follow-up work:
1. DoD SBIR firms are systematically less commercially-oriented (more government-services, more classified work, more SBIR-as-sole-revenue)
2. DoD SBIR firms commercialize through *federal contracts* rather than *private capital* — they don't raise Form D because their downstream revenue comes from FPDS contracts, not VC
3. Defense IP and classification restrictions discourage outside investment, making Form D filing less attractive
4. Acquisition path is more common than capital-raising path (consistent with the M&A analysis in PR #286)

Each of these has different policy implications. This is exactly the Path B item #3 deep-dive that needs to happen.

### NSF leads at 3.23x with credible bounds

NSF's program-level leverage [2.600, 4.016] is the highest among large-cohort agencies. The upper bound brushes against NASEM's 4:1 benchmark — suggesting that for NSF SBIR specifically, private-capital follow-on may approach the "leverage of 4× non-SBIR funding" benchmark that NASEM measures in a different channel. NSF's small SBIR award sizes combined with relatively high Form D participation rate (16% per the doc) are the mechanism.

### Education and Transportation are essentially zero

ED at 0.226x [0.127, 0.346] and DOT at 0.009x [0.008, 0.010] both have tight CIs around near-zero values. These agencies' SBIR programs produce essentially no Form D follow-on activity. Could be:
- Mission-specific (educational research, transportation infrastructure) doesn't attract VC
- Small cohort sizes (4 DOT firms, 21 ED firms) — but the CIs are narrow precisely because what little leverage exists is consistently low across the few firms

### Small-cohort agency CIs are very wide and shouldn't be quoted

Commerce, DHS, NASA, EPA, USDA all have wide CIs reflecting the small number of matched firms. Quoting "USDA's 2.92x leverage" as a point estimate without [1.630, 4.427] CI overstates precision by a large factor.

## What this doesn't address

CIs quantify **sampling uncertainty only**. They do NOT capture:

- **Measurement error in `total_amount_sold`.** Form D filers self-report; SEC does not audit. Estimated 5-15% additional noise from this source alone.
- **SBIR ↔ Form D matching error.** The confidence scoring is itself probabilistic; false positives (e.g., the ADVR-Inc Bozeman vs. ADVR-Inc Charleston SC collision flagged in prior work) are screened by the tier filter but not eliminated.
- **The "in-window SBIR" filtering decision.** I've shown both lenses, but a more rigorous treatment would also account for firms whose SBIR-side activity straddles the window boundary.
- **Selection effects in Form D filing.** Form D requires a securities offering exemption filing; firms that raise capital through other channels (bank debt, revenue, founder bootstrap, public offerings) are not represented. The "leverage" measured here is Form-D-mediated capital specifically, not total private capital.

The realistic credibility margin around these CIs is wider than the 95% bootstrap bounds suggest.

## Reproducibility

```bash
.venv/bin/python scripts/data/bootstrap_form_d_leverage_ci.py
```

Default config: 1,000 iterations, seed 42, window 2009-2024, inputs `data/form_d_details.jsonl` + `data/raw/sbir/award_data.csv`. Outputs to `reports/ml/form_d_leverage_ci.{json,md}` (gitignored under `/data/-adjacent reports/`).

The script is self-contained, uses only numpy from the project's existing dependency set, and runs in ~5 seconds on a development laptop.

## Follow-up work suggested

1. **Update the published `sbir-form-d-fundraising-analysis.md`** to add CI bracketing to the headline tables (or reference this doc as the methodology supplement). The current doc presents point estimates without uncertainty quantification.

2. **Drill into DoD's 1:1 finding** (Path B item #3). Decompose by firm type: classified vs. unclassified, service-only vs. product, single-agency vs. multi-agency. Compare to NASEM's 4:1 follow-on-federal-contract finding for the same DoD cohort and explain the channel difference.

3. **Quantify the matching-error contribution** to CI width. Currently the bootstrap treats the cohort as fixed and only resamples *which* firms enter; it doesn't account for *whether* a given firm is correctly matched. A two-stage bootstrap (resample matches THEN resample firms) would give wider, more honest CIs.
