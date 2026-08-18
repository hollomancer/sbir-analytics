# Form D fundraising leverage — frozen design

This is the frozen method for `studies/form-d-fundraising`. It records the
estimand and computation path. It does not authorize citation.

## Estimand

Among SBIR/STTR awardees in calendar years 2009–2024, estimate two
lower-bound private-to-SBIR leverage ratios from SEC Form D
`totalAmountSold` (capital actually sold, not offering amount):

1. **Program-level ratio.** Numerator: Form D dollars from matched firms
   after year and industry-group filters. Denominator: all SBIR.gov award
   dollars in the same window, including firms with no Form D match.
2. **Per-matched-firm ratio.** Same numerator. Denominator: SBIR.gov award
   dollars only for matched firms that have at least one in-window award.

Each ratio is reported at two match-confidence filters: high only, and
high + medium. Uncertainty is a firm-level percentile bootstrap (1,000
iterations, seed 42).

A zero or missing Form D match is non-detection, never proof that the
firm raised no private capital. The ratios are not NASEM's DoD follow-on
federal-contract leverage and are not comparable to it.

## Data cut

- SBIR.gov bulk awards (`Award Year` 2009–2024; 2025 excluded as a partial
  year).
- Form D match records at `data/form_d_details.jsonl`, scored by
  `compute_form_d_confidence` under the 2026-04-23 two-signal rule
  (high = PI–executive name score ≥ 0.7 or ZIP match; medium = state
  match only).
- Industry groups excluded at offering grain: Insurance, Lodging and
  Conventions, Other Travel, Pooled Investment Fund, Restaurants,
  Retailing, Tourism and Travel Services.

Inputs are local and gitignored. Re-running requires those files.

## Computation

`scripts/data/bootstrap_form_d_leverage_ci.py` loads the two files, joins
on uppercase stripped company name, applies the filters above, and writes
the bootstrap snapshot. The dated findings record is
`docs/research/sbir-form-d-fundraising-analysis.md`.

## What would make the estimate wrong

- Treating non-filers as true zeros rather than undetected capital.
- Using `totalOfferingAmount` instead of `totalAmountSold`.
- Mixing the program-level and per-matched-firm denominators.
- Comparing the ratio to NASEM's 4:1 federal-contract leverage as if they
  measured the same channel.
- A name-join collision or miss that moves a large issuer across the
  match-confidence filter.
