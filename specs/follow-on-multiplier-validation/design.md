# Follow-on Funding Multiplier Validation, Sensitivity & Review-Sampling — Design

**Status:** Spec.
**Date:** 2026-06-30.
**Builds on:** [PR #323](https://github.com/hollomancer/sbir-analytics/pull/323) (`packages/sbir-analytics/sbir_analytics/assets/follow_on_multiplier/`).
**Supersedes:** [PR #324](https://github.com/hollomancer/sbir-analytics/pull/324), closed as a parallel-implementation fork (different schema, different module path).

> The follow-on funding multiplier is the non-SBIR federal obligations per dollar of SBIR/STTR investment for SBIR-recipient firms. NASEM's reviews of DoD SBIR call this quantity the *leverage ratio*; this codebase uses *follow-on funding multiplier* for the same calculation.

## Why this is a separate spec

The follow-on funding multiplier asset in `assets/follow_on_multiplier/` (landing in PR #323) computes the core metric. PR #324 attempted to add validation gates, sensitivity analysis, and manual-review sampling — but did so as an independent implementation at `tools/mission_b/` with a completely different data schema (`canonical_company_id` vs `company_id`; `analysis_amount` + `is_sbir` flag vs `sbir_amount`/`non_sbir_amount` columns). Schema-aligning #324 onto #323's foundation would have been a 2-3 hour rewrite of code that hadn't yet been validated against real data — and the Copilot review identified several substantive bugs (silent NaN coercion, tautological validation checks, IndexError on empty scenarios, type-mixing in evidence sorting).

This spec captures the **design intent** from #324 so it can be re-implemented cleanly on top of #323's foundation when the next investment cycle starts.

## Goals

1. **Validation:** Independent invariants that test whether the computed follow-on multiplier is internally consistent with its source data and SBIR/STTR classification.
2. **Sensitivity:** Full-factorial parameter sweep across the methodological choices (match threshold, fiscal-year window, dollar basis, negative-obligation treatment, STTR inclusion) so the headline multiplier is bounded by an interval rather than asserted as a point.
3. **Manual-review sampling:** Deterministic stratified sample of obligations carrying the evidence fields a human reviewer needs to confirm entity-match and SBIR/STTR classification accuracy.

## Non-goals

- Re-implementing the core multiplier calculation (already in `assets/follow_on_multiplier/analysis.py`).
- Replacing #323's `agency_results` / NASEM reconciliation outputs.
- Producing a single "right" follow-on multiplier — the point of sensitivity analysis is to surface ranges.

## Architecture

Three modules added under `packages/sbir-analytics/sbir_analytics/assets/follow_on_multiplier/`:

```
assets/follow_on_multiplier/
├── analysis.py            (existing — PR #323)
├── asset.py               (existing — PR #323)
├── integration.py         (existing — PR #323)
├── reconcile.py           (existing — PR #323)
├── validation.py          (NEW — invariants + report gates)
├── sensitivity.py         (NEW — factorial parameter sweep)
└── review_sampling.py     (NEW — manual-review sample with evidence)
```

All three modules consume the canonical schema from #323's `integration.py` (`build_canonical_obligations`). No new field types are introduced.

## Validation invariants (`validation.py`)

Each invariant is a function `(prepared_obligations, computed_result, config) -> ValidationResult` with six fields: `name`, `passed: bool`, `observed_value`, `expected_value`, `tolerance`, `explanation`. The runner collects results; `enforce_report_gate()` raises if any gate fails.

| Invariant | What it checks |
|---|---|
| `source_reconciliation` | Sum of computed numerator and denominator equals the totals derived independently from `is_sbir`/`is_sttr` flags (within a tolerance for floating-point drift). **NOT** tautological — independently computes numerator/denominator from source flags and compares to the analysis output. |
| `no_sbir_in_non_sbir_numerator` | The non-SBIR obligations (numerator) sum, restricted to rows with `is_sbir == True OR is_sttr == True`, should be `0` within the configured tolerance. Any positive value signals SBIR/STTR leakage into the numerator. |
| `no_duplicate_obligations_after_matching` | `obligation_id` is unique across the prepared obligations frame. Catches join-fanout bugs from the entity-match step. |
| `deobligations_handled_as_configured` | If `config.include_negative_obligations == True`, the sum of `obligation_amount < 0` rows present in the prepared frame equals the sum of those rows in the source (i.e., they were retained, not silently clipped). If `False`, those rows are absent from the prepared frame. |
| `stable_aggregation_across_dimensions` | The headline `(non_sbir_obligations, sbir_sttr_obligations)` totals equal the sums from the `company`, `agency`, and `cohort` aggregates. |
| `match_quality_coverage` | The match-quality stratification reports cover ≥99% of obligation dollars. Surfaces cases where a meaningful share of dollars has no match-confidence value. |
| `required_output_dimensions` | Each output frame contains the required core columns (`follow_on_multiplier`, `record_count`, `scenario_id`) so downstream consumers can rely on a stable schema. Per-frame dimension columns (e.g., `company_id`, `agency`, `cohort_year`) are not constrained — the check verifies presence of the core columns, not absence of additional ones. |
| `no_unexplained_invalid_multipliers` | Any row with `follow_on_multiplier == NaN` has either `sbir_sttr_obligations == 0` (legitimate undefined) or carries an explicit reason in metadata. |

Each invariant carries a tolerance value (default `1e-6` for dollar sums) so floating-point drift doesn't cause spurious failures.

**Lessons from #324's Copilot review:** the original implementation had `source_num`/`source_den` computed from `numerator_eligible`/`denominator_eligible` flags AND `sbir_in_numerator` computed by AND-ing the same flags — making the check tautological. The spec'd version must compute the source totals from the raw `is_sbir`/`is_sttr` columns *independently of* the eligibility flags the analysis uses, and treat any discrepancy in the numerator as evidence of SBIR/STTR leakage.

## Sensitivity analysis (`sensitivity.py`)

Full-factorial sweep across the configurable methodology choices:

| Parameter | Default | Sweep values |
|---|---|---|
| `match_confidence_threshold` | 0.8 | `[0.7, 0.8, 0.9]` |
| `fiscal_year_start` / `fiscal_year_end` | full window | `[(2014, 2024), (2018, 2024), (2020, 2024)]` |
| `inflation_adjusted` | False | `[False, True]` |
| `include_negative_obligations` | True | `[True, False]` |
| `sttr_treatment` | "include" | `["include", "exclude"]` |

That's 3 × 3 × 2 × 2 × 2 = 72 scenarios. Each produces a `FollowOnMultiplierResult` carrying the same `scenario_id` schema #324 introduced (kept as a useful identifier). The runner emits a `sensitivity_summary` table with one row per scenario: scenario_id, headline multiplier, numerator total, denominator total, obligation count.

**Lessons from #324's Copilot review:** the original implementation assumed every scenario produced at least one headline row and used `.iloc[0]`. The spec'd version must handle the empty-headline case (when filters remove all obligations) — return a sentinel `FollowOnMultiplierResult` with NaN multiplier and explicit `n_obligations=0` rather than raising IndexError.

## Manual-review sampling (`review_sampling.py`)

Stratified sample across confidence-bucket × agency × dollar-decile, deterministic via a seed parameter. Each sampled obligation carries the evidence fields a human reviewer needs:

| Field | Source | Why it matters for review |
|---|---|---|
| `obligation_id` | source | Anchor for the record being reviewed |
| `company_id` | entity-resolution (canonical schema from #323) | The match the reviewer is checking |
| `match_confidence` | entity-resolution (canonical schema from #323) | Score the reviewer is calibrating against |
| `is_sbir`, `is_sttr` | source | Classification the reviewer confirms |
| `obligation_amount`, `fiscal_year`, `agency` | source | Disposition context |
| `original_recipient_name` | source | Raw name from USAspending |
| `matched_canonical_name` | entity-resolution | The canonical name the match resolved to |
| `review_status` | reviewer input (empty initially) | `confirmed` / `incorrect` / `ambiguous` |
| `reviewer` | reviewer input | Initials or ID |
| `review_notes` | reviewer input | Free text |
| `entity_match_confirmed` | reviewer input | bool |
| `sbir_classification_confirmed` | reviewer input | bool |
| `review_evidence_reference` | reviewer input | URL / source reference |

The sampling function returns a CSV-writable DataFrame. Reviewers fill in the right-hand columns and the function can re-load + aggregate review results.

**Lessons from #324's Copilot review:** the original implementation sorted `set(obligation_id)` directly — if `obligation_id` values mix types (ints, strings) or include nulls, `sorted(set(values))` raises a `TypeError`. The spec'd version must cast to strings (and skip nulls) before sorting to keep deterministic ordering robust to mixed-type IDs.

## Report gate

`enforce_report_gate(validation_results, sensitivity_summary) -> None`:
- Raises if any validation invariant failed.
- Computes the sensitivity span only over scenarios with **finite, strictly positive** multipliers (drop NaN, ±inf, and ≤ 0 values before computing `max / min`). Sentinel rows from empty scenarios (NaN multiplier, `n_obligations=0`) and degenerate cases (zero or negative denominators) are excluded from the gate.
- If fewer than two scenarios remain after filtering, the gate raises a `SensitivityGateInsufficientData` error (not a multiplier-span violation) so the failure mode is unambiguous.
- Raises if the filtered span exceeds the configured threshold (default: 2× — i.e., `max / min > 2` across the surviving scenarios means the methodology choices dominate the result).
- Logs a warning (not a raise) if the span is between 1.5× and 2×.

Wired into the Dagster asset for the follow-on-multiplier report so a methodologically-fragile result fails the asset run instead of being silently published.

## Testing approach

- **Unit tests per invariant** with hand-constructed fixtures that exercise pass and fail paths.
- **Fixtures explicitly include** the edge cases the original #324 implementation broke on: empty filtered output, mixed-type obligation IDs, NaN `company_id` values (canonical schema from #323), negative obligations.
- **Sensitivity smoke test** that runs a 4-scenario subset against a small fixture and verifies the sensitivity_summary frame has the expected shape and scenario_ids.
- **Review-sampling determinism test** with a fixed seed asserting the same input produces the same sample.
- **Report-gate integration test** with crafted inputs that trip each gate condition.

## Effort estimate

- Validation module: ~6-8 hours including tests
- Sensitivity module: ~3-4 hours
- Review sampling: ~3-4 hours
- Report-gate integration into Dagster asset: ~1-2 hours
- Documentation: ~2 hours

**Total: ~16-20 hours of focused work**, or 2-3 days for thorough implementation including the test coverage that #324 lacked.

## Open questions for implementation

1. **Where does the canonical "review sample CSV" get written?** Probably `data/processed/follow_on_multiplier/review_sample_<scenario_id>.csv`, but should this be part of the asset output or a separate Dagster asset/job?
2. **What's the right multiplier-span threshold for the report gate?** 2× is a starting point; should be tuned empirically against the first sensitivity run.
3. **Should the validation invariants run on every scenario in the sensitivity sweep, or only on the headline scenario?** Running them all is more thorough but expensive on a 72-scenario factorial. Default: headline only, with a flag to run all.

These are the kinds of decisions worth deferring to actual implementation rather than over-spec'ing here.
