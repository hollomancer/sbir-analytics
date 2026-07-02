# Data Imputation — Archived

**Archived:** 2026-07-02
**Status:** Superseded before any code was implemented (`sbir_etl/imputation/` never created; no `config/base.yaml[imputation]` section landed; no tasks in `tasks.md` were checked off).

## Why archived

The spec framed two headline problems as statistical imputation of missing values:

1. `award_date` missing on ~50% of records
2. `company_uei` / `company_duns` missing on many records

Empirical analysis of the underlying SBIR.gov bulk download (`data/raw/sbir/award_data.csv`, 219,501 rows) showed that both framings were wrong:

- **`award_date` missingness is a schema cutover, not a distribution.** It is ~100% missing pre-2004 (the field did not exist in the source data model), then agency-specific cutovers occur through 2015, then ~0% missing (except HHS at 7.2%). `Award Year` is 100% populated across the entire corpus. The correct operation is **time-key routing** — use `award_date` where present, fall back to the already-populated `Award Year` — not statistical imputation. There is nothing to estimate.
- **`company_uei` missingness is a firm-level bifurcation, not per-award noise.** Of multi-award firms with any UEI-missing rows in the 2000–2020 window, 40.9% are missing UEI on **every** award and 59.1% are missing on **none**. Only 2 firms out of 13,338 show scattered per-award patterns. This is not a missing-value problem; it is an **entity-resolution problem**. Firms are either resolved against the identifier registry or they are not. The correct operation is upstream **firm identity resolution** with a canonical internal `firm_id` emitted per award, tiered by resolution method (UEI/DUNS/CAGE/fuzzy-name), with UEI as one output column populated where the resolution succeeds.

The spec's own §4.1 (`award_date.cascade`) and §4.2 (`identifiers.cross_award_backfill`) methods were already deterministic derivation rather than statistical imputation. The vocabulary — "imputation", "backfill", "confidence", "MICE/missForest considered and rejected" — invited a solution space that was not the correct solution space for the actual missingness structure.

## Superseded by

Two focused specs replace this one:

- **`specs/firm-identity-resolution/`** — Upstream firm-identity resolution as a canonical ETL stage. Emits `firm_id`, `uei`, `duns`, `cage`, `resolution_method`, `resolution_score`, `resolution_source` on every award. Reuses existing infrastructure (`sbir_etl/enrichers/company_fuzzy_matcher.py`, `sbir_etl/utils/company_canonicalizer.py`, `sbir_etl/extractors/sam_gov.py`, `packages/sbir-ml/sbir_ml/transition/features/vendor_resolver.py`). Replaces §4.2 of this spec and subsumes the `company_uei` / `company_duns` framing.
- **`specs/input-validation-hardening/`** — Validator strictness for `award_amount` / `program` / `phase` (currently silently coerced to `None`) and date-consistency violations (currently emitted as `WARNING` rather than `ERROR`). Replaces §1 acceptance criteria around lenient validators. Not identity or date-key routing.

## What was dropped, not moved

The following methods from this spec were not carried into either replacement because their analytic value did not clear the top-two-use-case cut and they were not blocking any active downstream work:

- **§4.3 `award_amount.solicitation_max`** and **§4.4 `award_amount.agency_phase_median`** — statistical fill for `award_amount`. May be revisited if a specific downstream benchmark surfaces demand.
- **§4.5 `contract_dates.solicitation_period_of_performance`** and **§4.7 `contract_dates.end_date_repair`** — contract-end-date repair. Deferred.
- **§4.6 `geography.congressional_district`** — a thin wrapper over the existing `congressional_district_resolver.py`. The resolver already runs where needed; wrapping it under an imputation registry added no value.
- **§4.8 `naics.*`** — NAICS hierarchical rollup and abstract-NN inference. Deferred.

## Time-key routing (the `award_date` reframe)

Not a spec — a documented convention. `award_date` should be used where present, with fallback to `Award Year` (fiscal-year granularity) elsewhere. The one non-trivial residual is HHS post-2015 at 7.2% date-missing, which should be a known caveat for NIH/HHS-specific analyses. This convention lives in `docs/steering/` (to be added) rather than as a separate spec.
