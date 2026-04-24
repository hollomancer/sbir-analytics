# Data Imputation — Requirements

## Introduction

The SBIR.gov bulk download is the canonical source of SBIR/STTR award records for this
pipeline, but it is systematically incomplete and internally inconsistent:

- `award_date` is missing on roughly **50% of records** while the configured completeness
  threshold is **95%** (`sbir_etl/validators/sbir_awards.py:561`, `config/base.yaml:50-59`).
- Core fields (`award_amount`, `award_date`, `program`, `phase`) use **lenient validators**
  that silently coerce invalid values to `None` (`sbir_etl/models/award.py:189-332`) rather
  than rejecting records. This produces hidden nulls that look like missing-at-random data
  but are actually parse failures.
- `company_uei` and `company_duns` are missing for many records, requiring fuzzy-name
  fallback matching at enrichment time (`sbir_etl/enrichers/company_categorization.py`).
- Date consistency violations (end-before-start, proposal-after-award) are emitted as
  `WARNING` rather than `ERROR` and pass through unchanged.

Downstream consumers — CET classification, phase-transition detection (≥85% precision
benchmark), leverage-ratio analysis, and weekly reporting — treat these nulls as true
absences. That biases cohort statistics (missing `award_date` disproportionately affects
older awards), suppresses legitimate phase-transition matches (missing `company_uei`),
and degrades any time-series analysis that keys on `award_year`.

This spec defines a **transparent, auditable imputation layer** that fills recoverable
gaps *without* overwriting source-of-truth data, so downstream code can deliberately
choose whether to include imputed values.

## Glossary

- **Imputation** — Deriving a value for a missing/invalid field from other fields on the
  same record, sibling records, or external enrichment sources. Distinct from
  *enrichment* (adding net-new fields from external APIs).
- **Raw field** — The value as it appeared in the SBIR.gov bulk download, after type
  parsing but before imputation.
- **Effective field** — The value downstream consumers should read: raw if present, else
  imputed if available, else null.
- **Imputation method** — The named strategy used to derive a value (e.g.,
  `contract_start_date_fallback`, `agency_phase_median`, `zip5_crosswalk`).
- **Provenance record** — Per-field metadata capturing whether a value was imputed, by
  which method, from which source fields, with what confidence.
- **Confidence tier** — `high` / `medium` / `low`, defined per imputation method based on
  empirical accuracy measured against non-null ground-truth holdouts.

## Requirements

### Requirement 1 — Non-destructive imputation

**User Story:** As a data consumer, I want imputed values to never overwrite raw source
data, so that I can always recover the original and audit downstream claims.

#### Acceptance Criteria

1. THE System SHALL preserve the raw extracted value for every imputable field in a
   `raw_<field>` column (or equivalent side table) alongside the imputed value.
2. THE System SHALL write imputed values only to the effective column consumed by
   downstream assets; the raw column SHALL remain byte-identical to extractor output.
3. THE System SHALL NOT impute fields that are primary keys (`award_id`) or subjective
   classification flags (`is_hubzone`, `is_woman_owned`, `is_socially_disadvantaged`).
4. THE System SHALL produce identical raw columns across repeated runs of the same bulk
   download (deterministic raw layer).

### Requirement 2 — Provenance and auditability

**User Story:** As an analyst, I want to filter imputed values in or out per-field, so
that I can run analyses at different confidence levels without re-deriving imputations.

#### Acceptance Criteria

1. THE System SHALL emit a per-record `imputation` struct column containing, for each
   imputed field: `method` (str), `confidence` (enum: high/medium/low),
   `source_fields` (list[str]), and `imputed_at` (UTC timestamp).
2. THE System SHALL expose boolean convenience columns `<field>_is_imputed` for every
   imputable field to enable cheap downstream filtering.
3. THE System SHALL version imputation methods (`method_version` int) so that historical
   imputations remain attributable to a specific algorithm even after logic changes.
4. THE System SHALL log a run-level imputation summary to `reports/imputation/` recording
   per-field impute rates, method distribution, and confidence distribution.
5. THE System SHALL ensure Neo4j nodes carry the `<field>_is_imputed` flags and
   `imputation_methods` list as node properties for graph-time filtering.

### Requirement 3 — Imputable fields and methods

**User Story:** As a pipeline operator, I want a documented catalog of imputation
methods per field, so that I know exactly what the pipeline will infer and what it
won't.

#### Acceptance Criteria

1. THE System SHALL support imputation of `award_date` via cascade:
   `proposal_award_date` → `contract_start_date` → `date_of_notification` →
   `solicitation_close_date + agency_lag` → `fiscal_year midpoint`.
2. THE System SHALL support imputation of `company_uei` and `company_duns` via
   cross-award backfill: when the same normalized `(company_name, company_state)` key
   has a known UEI/DUNS on any other award in the corpus, propagate it.
3. THE System SHALL support imputation of `award_amount` via agency-phase-program-year
   group median with a bounded `±2σ` sanity check; values that would fall outside the
   existing `$5M` cap are flagged, not assigned.
4. THE System SHALL support imputation of `congressional_district` via tiered zip
   crosswalk (zip+4 → zip5 → city/state centroid), reusing
   `sbir_etl/enrichers/congressional_district_resolver.py`, and populate the existing
   `congressional_district_confidence` field.
5. THE System SHALL support repair of `contract_end_date` when it is absent or precedes
   `contract_start_date`, using agency-phase-typical durations.
6. THE System SHALL support imputation of `naics_code` via hierarchical fallback
   (6→4→3→2 digits) and, when entirely absent, nearest-neighbor inference from award
   abstracts against awards with known NAICS.
7. THE System SHALL NOT impute `principal_investigator`, contact fields, or classification
   booleans; it SHALL only normalize/deduplicate existing values for these fields.

### Requirement 4 — Configurable and toggleable

**User Story:** As a developer, I want to enable, disable, and tune each imputation
method from config, so that I can A/B test impact on downstream benchmarks.

#### Acceptance Criteria

1. THE System SHALL expose an `imputation` section in `config/base.yaml` with per-method
   toggles (`enabled: true/false`) and method-specific parameters (cascade order,
   grouping keys, confidence thresholds).
2. THE System SHALL support dev/prod overrides via the existing config layering pattern.
3. THE System SHALL allow a `dry_run` mode that computes imputations and emits the
   provenance report *without* populating the effective columns, for validation.

### Requirement 5 — Integration with existing quality and enrichment stages

**User Story:** As a pipeline maintainer, I want imputation to run at a well-defined
stage that does not corrupt quality metrics, so that source-completeness measurements
remain truthful.

#### Acceptance Criteria

1. THE System SHALL run imputation **after** extraction and **after** raw validation
   (`sbir_etl/validators/sbir_awards.py`), and **before** entity enrichment
   (`sbir_etl/enrichers/company_enrichment.py`).
2. THE System SHALL measure completeness thresholds in `sbir_etl/quality/checks.py`
   against **raw** columns, not imputed columns, so that the ~50% `award_date` gap
   remains visible as a source-data issue.
3. THE System SHALL emit a separate quality report (`reports/imputation/coverage.json`)
   that measures post-imputation effective completeness per field.
4. THE System SHALL reconcile the `award_date` completeness threshold in
   `config/base.yaml` to reflect realistic raw coverage (separate raw vs. effective
   thresholds).

### Requirement 6 — Validation and backtesting

**User Story:** As a data scientist, I want each imputation method validated against
records where ground truth exists, so that published confidence tiers are empirically
defensible.

#### Acceptance Criteria

1. THE System SHALL provide a backtest harness that masks known-good values, re-imputes
   them, and reports MAE/accuracy per method.
2. THE System SHALL set `confidence: high` only for methods with ≥90% backtest accuracy
   on holdout, `medium` for 75–90%, `low` below 75%.
3. THE System SHALL verify the phase-transition precision benchmark (≥85%) does not
   regress when imputed fields are included, via existing
   `packages/sbir-ml/` evaluation tests.
4. THE System SHALL fail CI if backtest accuracy for any method drops more than 5
   percentage points below its recorded baseline.

### Requirement 7 — Downstream consumer contract

**User Story:** As a Neo4j loader author, I want a clear contract for consuming imputed
fields, so that graph queries can opt in or out deterministically.

#### Acceptance Criteria

1. THE System SHALL document in `docs/steering/` which downstream assets read effective
   vs. raw columns.
2. THE System SHALL default `packages/sbir-ml/` (CET, transition detection) to reading
   **raw** values with explicit opt-in to imputed values, to protect precision
   benchmarks.
3. THE System SHALL default `packages/sbir-analytics/` reporting assets to reading
   **effective** values (imputed where available) with `_is_imputed` columns surfaced
   in reports.
4. THE System SHALL default `packages/sbir-graph/` loaders to writing effective values
   with `is_imputed` flag properties on nodes.
