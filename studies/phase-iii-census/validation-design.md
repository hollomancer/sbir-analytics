# Validation design — `phase-iii-census` permutation separation

**Status:** preregistered. Frozen before any draw beyond the single materialized
placebo has been run. Pin this file in `study.yaml` `frozen_artifacts` and cite
its digest as `validation_result.design_path` / `design_sha256`.

**Estimand under test:** not the census estimand. This design tests one
property of the census output — whether the separation between the actual frame
and the frozen cross-firm placebo is larger than the separation that the placebo
construction produces by chance.

## What is already known and what is missing

The study has materialized one placebo: a fixed-seed (`PLACEBO_SEED = 20260801`)
randomized cyclic cross-firm assignment of prior-award completion dates. On that
single draw the actual frame exceeds the placebo frame on every complete-filter
metric and in every cell.

One draw gives a direction. It cannot say whether the observed margin is large
relative to what this construction yields by chance, because a single draw has
no dispersion. `ValidationResult` requires `interval_low`, `interval_high`, and
`interval_method`, and none of those exist for N = 1.

## The test

Draw `N = 1000` independent assignments using seeds `PLACEBO_SEED + i` for
`i` in `1..1000`. The frozen draw (`i = 0`) is reported alongside but is **not**
a member of the null sample; it is the assignment the study already published.

For each draw, build the placebo census tables through the same
`build_placebo_study_tables` path the frozen draw used, and record the four
metric columns already defined for the comparison tables:

- `surviving_pairs`
- `distinct_firms`
- `distinct_contracts`
- `total_obligated_dollars`

**Statistic.** For one metric in one cell, the statistic is the actual frame's
value. A draw *counts as exceeded* when the actual value is strictly greater
than that draw's placebo value.

**Primary metric and cell.** `surviving_pairs` on the complete-filter cell.
Every other metric and cell is reported as a secondary result and may not be
substituted for the primary one after the draws are seen.

## Threshold

- `threshold_basis: proportion`
- `threshold_value: 0.95`
- `numerator`: draws the actual value strictly exceeded, on the primary metric
  and cell
- `denominator`: 1000
- `interval_method`: Wilson 95%

**Derivation.** The threshold is the conventional one-sided 5% level expressed
as an exceedance proportion. At N = 1000, the Wilson 95% interval for an
observed 0.95 is roughly `[0.935, 0.962]`, so the design can distinguish 0.95
from 0.90 but cannot resolve 0.95 from 0.96. That resolution is sufficient for a
pass/fail statement at the 5% level and is not sufficient for ranking two
near-threshold outcomes; no such ranking is a permitted claim.

`threshold_met` is true when the lower bound of the Wilson interval is at or
above 0.95, not merely when the point estimate is. Recording an interval whose
lower bound sits below the threshold and calling it met is the failure mode this
whole design exists to avoid.

## What a pass would and would not license

**Would:** the observed separation between the actual frame and the frozen
cross-firm placebo construction is larger than chance at the stated level, with
a stated interval.

**Would not:** any claim that an uncoded lineage proxy identifies a genuine
statutory Phase III award. The study's existing limitation on that point
survives promotion unchanged, and `permitted_claims` must say so in its own
voice. A reader who sees the inventory word `Validated` will otherwise read it
as "this measures Phase III correctly."

The distinction is not a hedge. The null being tested is a null over *award-grain
completion dates*: the placebo preserves the unique-award date multiset and
reassigns dates across firms. Rejecting it says the census output depends on the
real date-to-award correspondence rather than on the date distribution alone. It
says nothing about whether the pairs the census surfaces are statutory Phase III
work.

## Preconditions this design does not satisfy by itself

1. **Inputs.** `data/processed/phase_ii_awards.parquet` and the contract inputs
   must be present and provenance-verified. They are absent from a clean
   checkout.
2. **Process gate.** `scripts/data/build_phase_iii_placebo.py` states that its
   first production invocation is gated on a separate repository-owner approval.
   Running 1000 draws is a production invocation.
3. **Cost.** Each draw runs one memory-safe census pass. N = 1000 is 1000 census
   passes; the runtime and memory envelope must be measured on a small N before
   the full run is scheduled.

## Analysis rules, fixed before the draws

- Run once. A second run against a changed freeze is a new reviewable version,
  not a correction.
- Seeds are `PLACEBO_SEED + i` for `i` in `1..1000`, in that order. Every draw is
  reproducible from its seed; the recorded distribution must include the per-draw
  seed and its `mapping_sha256`.
- A draw that raises `PlaceboInputError` is recorded as a construction failure
  and excluded from `denominator`, with the count of exclusions reported. More
  than 10 exclusions invalidates the run rather than shrinking the denominator
  quietly.
- No metric, cell, N, or threshold changes after the first draw is executed.
- The full distribution is recorded, not only the summary.
