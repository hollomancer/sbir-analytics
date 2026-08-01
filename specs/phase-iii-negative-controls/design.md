# Phase III Negative Controls and Placebo — Dependency Scaffold

**Status:** **BLOCKED — dependency scaffold only.**

**Base dependency:**
[Phase III census PR #475](https://github.com/hollomancer/sbir-analytics/pull/475).

PR #475 implements frozen, auditable Phase 1 census tables. Those tables are
implementation outputs, not validated Phase III results. No production census count,
negative-control result, or placebo result has been materialized or quoted.

This stub makes the validation dependency visible before a count can acquire the
appearance of a finished result. It adds no control implementation, resolution method,
new numeric cutoff, or result.

## Inherited design

The control and SBIR arms must use the identical frozen census filter and pseudo-index
design from [`../phase-iii-census/design.md`](../phase-iii-census/design.md). The filter
must not branch on arm membership; an `if is_control:` inclusion path is a design failure.

## Required work before this gate can close

1. **Full-history eligibility:** certify that every control firm received no SBIR/STTR
   award anywhere in the complete award history, and report every exclusion with its
   reason.
2. **Matching:** match each SBIR firm to one through three controls on primary NAICS,
   employee-count band, state, year of first federal contract, and PSC family.
3. **Balance:** report standardized mean differences for every matched covariate and stop
   for review when a key covariate exceeds the pre-registered `0.1` balance limit.
4. **Arm-blind evaluation:** run the same census filter implementation on both arms with
   no arm-specific criterion or threshold.
5. **Distributional reporting:** publish the full per-firm distribution of criteria-met
   counts for both arms, their overlap coefficient, and the ratio of firms in each arm
   clearing the complete criteria set.
6. **Placebo:** permute `prior_period_of_performance_end` across real SBIR firms with a
   fixed, recorded seed, rerun the census, and report the unpermuted and permuted tables
   without selecting a favorable result.

## Current blockers

- The full-history SBIR.gov record has a material population without reliable UEI or
  DUNS linkage. Exact identifier exclusion therefore cannot yet certify that a SAM entity
  is SBIR/STTR-negative across the entire history; a replacement method has not been
  approved.
- The available SAM public entity extract does not provide the required employee-count
  covariate. No employee-band construction or substitute covariate has been approved.

Until both blockers are resolved and evidence-backed control and placebo artifacts exist,
the release gate in `tests/unit/phase_iii_negative_controls/test_release_gate.py` must
remain deliberately failing. Removing, skipping, or marking it expected-to-fail is not a
resolution.
