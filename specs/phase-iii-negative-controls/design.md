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

1. **Full-history eligibility — bound the contamination, do not certify its absence.**
   Exact-identifier exclusion against the complete award history, reporting every
   exclusion with its reason. That screen cannot clear the population with no reliable
   UEI/DUNS, and no future work will: the identifiers are absent from the source record,
   which is a permanent property of it, not a dependency waiting to resolve. A
   requirement to *certify* a negative over that population would therefore never be
   satisfiable, and the gate would be permanent rather than blocking. What is required
   instead, following the standard matched-control treatment:
   - **estimate an upper bound** on the share of retained "controls" that are undetected
     SBIR/STTR recipients — a name-based screen over the unlinkable population yields a
     rate even where it cannot adjudicate any individual firm;
   - **pre-register that bound** as a reported quantity alongside the headline contrast;
   - **show the contrast survives the worst case** — assume every unlinkable,
     name-similar firm is SBIR-positive, and report whether the conclusion holds.

   The gate closes on a measured and disclosed contamination bound, not on proof of
   zero contamination.
2. **Matching:** match each SBIR firm to one through three controls on primary NAICS,
   state, year of first federal contract, and PSC family.

   **Employee-count band is dropped**, and the drop is deliberate rather than deferred:
   it was specified as a required covariate while simultaneously appearing in the
   blockers below as unavailable in the SAM public entity extract, which left the
   matching design not executable as written. Resolution: match without it, and report
   the cost — firm size is the covariate most plausibly correlated with both SBIR
   participation and contract outcomes, so its omission is the largest known threat to
   balance and **must be named in the results, not just here**. If an approved
   employee-count source later exists, reinstating it is a strict improvement; adding it
   back is not a precondition for closing the gate.
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
  DUNS linkage, so exact-identifier exclusion cannot certify that a SAM entity is
  SBIR/STTR-negative across the entire history. This is a **permanent property of the
  source**, not a pending dependency — requirement 1 is written to bound the resulting
  contamination rather than wait for it to close. The remaining work is to *build* that
  bound (the name-based screen and the worst-case robustness check), which is not done.
- The available SAM public entity extract does not provide an employee-count covariate.
  This is **no longer a blocker**: requirement 2 drops the covariate and requires the
  resulting balance cost to be reported. It is recorded here as a known limitation, and
  as the reason a size-band substitute would be worth approving later.

Until evidence-backed control and placebo artifacts exist — including the contamination
bound required by requirement 1 — the release gate in
`tests/unit/phase_iii_negative_controls/test_release_gate.py` must remain deliberately
failing. Removing, skipping, or marking it expected-to-fail is not a resolution.

**This branch is therefore not intended to merge while the gate is closed.** `unit-fast`
is a required check, so merging a deliberately failing test would turn `main` red for
every unrelated PR in the repo. The draft status is what enforces that today; it should
stay a draft until the gate can close.

One requirement here *can* be pinned by a green test today, with none of the blocked
data: requirement 4's arm-blindness. A test asserting that the census filter's call
signature takes no arm/label argument — or that the filter module never references the
arm column — would pass now, could live on `main`, and would go red the moment someone
adds the `if is_control:` branch this design calls a failure. That test is not blocked on
SAM or SBIR.gov and should land independently of this gate.
