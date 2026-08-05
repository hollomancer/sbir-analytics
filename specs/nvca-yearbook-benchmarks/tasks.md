# NVCA Yearbook Benchmark Reference Data — Tasks

> **Status:** **All tasks deferred — blocked on NVCA Yearbook source access.**
> This PR ships only the corrected spec (see `requirements.md`); implementation
> lands in a follow-up once a contributor with NVCA Yearbook PDF access can
> transcribe verified figures. Mark tasks complete only after the gating
> source-access step is satisfied.

## Phase 1: Source access (blocking)

- [ ] 1.1 (deferred / blocked-on-NVCA-access) Verify NVCA Yearbook data source
  access — confirm which edition(s) are available, page numbers for the
  public-summary cohort-outcome figures, and a stable `citation_url` for each.

## Phase 2: Baseline registry expansion

- [ ] 2.1 (deferred / blocked-on-NVCA-access) Add NVCA Yearbook baseline entries
  to `config/agency_private_capital/published_baselines.yaml` per Requirement 1
  — each with `as_of`, `population`, `citation`, `citation_url`, and a
  `cohort_metric` already implemented in `outcomes.py`
  (`phase_i_to_ii_graduation`, `phase_ii_to_federal_contract_transition`,
  `five_year_survival_proxy`, `ma_exit_rate`) or paired with a new metric
  added under task 3.1.
- [ ] 2.2 (deferred / blocked-on-NVCA-access) Preserve the existing
  `nvca_seed_to_series_a` entry; for newer Yearbook editions, add a new entry
  with the newer `as_of` rather than overwriting.

## Phase 3: Reconciliation wiring

- [ ] 3.1 (deferred / blocked-on-NVCA-access) For each new baseline whose
  `cohort_metric` is not already in `outcomes.py`, implement the matching
  SBIR-side cohort metric and update
  `agency_private_capital_outcomes` to emit it.
- [ ] 3.2 (deferred / blocked-on-NVCA-access) Add a corresponding `_ATTRIBUTION`
  entry in `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/reconcile.py`
  for each new (metric, baseline) pair, matching the existing five attribution
  narratives.
- [ ] 3.3 (deferred / blocked-on-NVCA-access) Add the corresponding `_CAVEAT`
  entry in `reconcile.py` for each new pair.

## Phase 4: F3 leverage-ratio baseline (NASEM 4:1)

- [ ] 4.1 (deferred / blocked-on-implementation-decision) Add a
  `nasem_dod_leverage_ratio` baseline entry to
  `config/agency_private_capital/published_baselines.yaml` per Requirement 3.
- [ ] 4.2 (deferred / blocked-on-implementation-decision) Implement
  `private_to_sbir_leverage_ratio` in `outcomes.py`, stratified by agency,
  vintage bucket, and firm size per the F3 anchor language.

## Phase 5: Testing

- [ ] 5.1 (deferred / blocked-on-NVCA-access) Integration tests covering each
  newly added (baseline, cohort_metric) pair through
  `agency_private_capital_baseline_comparison`.
- [ ] 5.2 (deferred / blocked-on-NVCA-access) Confirm existing
  registry-loading and `reconcile.py` tests stay green after additions.
