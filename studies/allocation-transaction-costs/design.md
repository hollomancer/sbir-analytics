# Allocation transaction costs — frozen design

This is the frozen method for `studies/allocation-transaction-costs`. It
records the estimand and computation path. It does not authorize citation.

## Estimand

Among NIH competing applications in overlapping fiscal years, estimate three
separate mechanism-year quantities for NIH SBIR/STTR phases versus NIH
R01-equivalent grants, under declared duration conventions and hour
assumptions:

1. Transaction **hours** per funded award (applicant + reviewer).
2. Transaction **dollars** per funded award (applicant + reviewer + agency,
   with agency missing unless a named lower bound is attached).
3. Transaction cost **per dollar awarded**.

Also estimate the break-even SBIR applicant-hour threshold at which (3) for
NIH SBIR Phase I equals (3) for NIH R01-equivalent, holding wages equal.

The quantities are not a welfare estimate, not a measure of scientific
quality, and not a causal effect of offering SBIR instead of R01s.

## Grain

Mechanism × fiscal year × duration convention. No firm identity. SBIR and
STTR stay separate. Phase I, Phase II Regular, Direct Phase II, Phase IIB,
Fast Track, and CRP stay separate.

## Data cut

- NIH RePORT Table #215 (rId=584), FY2015–FY2025, competing applications,
  awards, success rates, and total funding by SBIR/STTR phase.
- NIH Data Book report 29 (applications, awards) joined to report 158
  (annual average size) for R01-equivalent grants, FY1998–FY2025.
- Comparison years are the intersection, FY2015–FY2025.

Inputs are committed CSVs hashed in `sources.yaml`.

## Duration conventions

NIH Data Book R01-equivalent average size is an **annual** figure. Table
#215 SBIR Phase I total funding / awards is a **competing-year** figure
(approximately the Phase I project). Two conventions are always reported:

- `annual_award_size` — use each series as published.
- `project_total` — multiply the R01 annual average by
  `duration.r01_project_years` from `assumptions.yaml`; leave SBIR Phase I
  unchanged.

## Formulas

Let `s = awards / applications` and `D` be mean award dollars under the
duration convention.

Applicant hours per funded award:

`A = hours_per_application / s`

Review hours per funded award:

`R = reviewers_per_application * reviewer_hours / s`

Applicant cost: `AC = applications * hours_per_application * wage`

Review cost: `RC = applications * reviewers * reviewer_hours * reviewer_wage`

Agency cost `GC` is missing by default. A sensitivity may set
`GC_sbir = sbir_admin_allowance_ceiling * dollars_awarded` and leave
`GC_r01` missing. That ceiling is not total NIH selection cost.

Then:

- hours per award = `A + R`
- dollars per award = `(AC + RC + GC) / awards` when GC is present, else
  `(AC + RC) / awards` with `gc_included = false`
- cost per awarded dollar = `(AC + RC + GC) / (awards * D)`

Break-even SBIR applicant hours, same wage, GC omitted:

`h_sbir* = h_r01 * (s_sbir * D_sbir) / (s_r01 * D_r01)`

The three outcomes are never collapsed into one efficiency score.

Paperwork Reduction Act burden-hour estimates and university F&A rates are
not valid values of `hours_per_application`.

## What would make the estimate wrong

- Treating PRA hours or F&A rates as observed proposal-writing time.
- Combining SBIR with STTR, or Phase I with Phase II.
- Using the 3% administrative-funding allowance as total agency cost.
- Mixing the annual and project-total duration conventions.
- Transferring FDP university-PI hours onto SBIR firms without labeling the
  transfer.
- Citing a preferred hour cell as the result instead of the break-even.
