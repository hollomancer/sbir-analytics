# Input Validation Hardening — Requirements

## Introduction

The SBIR extractor and Pydantic models currently apply **lenient validators** that coerce invalid values to `None` on core fields (`award_amount`, `program`, `phase`) rather than rejecting the record or quarantining the field (`sbir_etl/models/award.py:189-332`). Date-consistency violations (`contract_end_date < contract_start_date`, `proposal_receipt_date > award_date`) are emitted as `WARNING` in `sbir_etl/models/award.py` (`validate_date_order` and related field validators) and pass through unchanged into downstream assets.

The operational consequence is that downstream code cannot distinguish two very different rows: one where the source field was truly missing, and one where the source field was present but malformed. Both appear as `None`. Cohort and quality metrics treat parse failures as source-data gaps, which biases coverage measurements and hides upstream data issues that would otherwise be actionable.

This spec covers **validator strictness only**. It does not cover firm identity resolution (see `specs/firm-identity-resolution/`) or the time-key convention for choosing between `award_date` and `award_year` (documented in `docs/steering/`, not a spec). The bundled `data-imputation` spec that previously conflated all three concerns is archived at `specs/archive/superseded/data-imputation/`.

## Glossary

- **Lenient coercion** — Validator behavior where an invalid value is converted to `None` and the record proceeds through the pipeline. For `program` and `phase`, invalid values are logged at `WARNING` before coercion; `award_amount` coercion is currently quieter. Current default for all three fields.
- **Strict rejection** — Validator behavior where an invalid value causes the field to be quarantined with a distinguishing sentinel (or the record routed to a rejection stream). Proposed default.
- **Parse-failure null** — A field value that is `None` because the source data was malformed, not because the source data was absent. Currently indistinguishable from a true absence.
- **True null** — A field value that is `None` because the source data did not contain a value. The intended semantic for downstream consumers.

## Requirements

### Requirement 1 — Distinguish parse failures from true absences

**User Story:** As a downstream analyst, I want to distinguish a record where a field was truly absent from a record where the field was present but malformed, so that quality metrics reflect real source-data gaps rather than pipeline parse failures.

#### Acceptance Criteria

1. THE `Award` model SHALL emit a per-field `field_parse_status` map (or equivalent) recording, for each strictly-validated field, one of `{present, absent, parse_failure}`.
2. THE `field_parse_status` map SHALL be populated at extraction/validation time for at minimum `award_amount`, `program`, `phase`, `contract_start_date`, `contract_end_date`, `award_date`.
3. THE downstream persistence layer (Parquet, DuckDB) SHALL retain the `field_parse_status` map through the `validated_sbir_awards` asset.
4. THE `sbir_etl/quality/checks.py` completeness thresholds SHALL count `parse_failure` separately from `absent`; a field with 5% true absence and 3% parse failures reports both, not a combined 8% "missing" rate.

### Requirement 2 — Strict validation for currency and enumerated fields

**User Story:** As a pipeline maintainer, I want malformed currency, program, and phase values to be flagged rather than silently dropped, so that source-data quality issues surface upstream instead of being absorbed as hidden nulls.

#### Acceptance Criteria

1. WHEN `award_amount` receives a value that fails currency parsing (unparseable string, negative, exceeds the existing `$5M` sanity cap), THE validator SHALL record `parse_failure` in `field_parse_status.award_amount`, set the field to `None`, and log the raw source string once per unique failure mode per run.
2. WHEN `program` receives a value not in the accepted enumeration, THE validator SHALL record `parse_failure`, set the field to `None`, and log the raw value.
3. WHEN `phase` receives a value not in the accepted enumeration (or a numeric value that cannot be mapped to `Phase I`/`Phase II`/`Phase III`), THE validator SHALL record `parse_failure`, set the field to `None`, and log the raw value.
4. THE validator SHALL NOT change existing behavior for records where the source field is genuinely absent — those SHALL continue to produce `None` with `field_parse_status.<field> = absent`.
5. THE strict-validation behavior SHALL be the default; a `strict_validation: false` config knob MAY exist for backward-compatibility during migration but SHALL emit a deprecation warning when set.

### Requirement 3 — Date-consistency violations elevated to errors

**User Story:** As a data consumer, I want records with impossible date orderings to fail validation loudly rather than pass through as WARNING, so that impossible states cannot silently corrupt time-series analysis.

#### Acceptance Criteria

1. WHEN `contract_end_date` is present AND `contract_start_date` is present AND `contract_end_date < contract_start_date`, THE validator SHALL emit `ERROR` (not `WARNING`), record `field_parse_status.contract_end_date = parse_failure`, and set `contract_end_date` to `None`.
2. WHEN `proposal_receipt_date` is present AND `award_date` is present AND `proposal_receipt_date > award_date`, THE validator SHALL emit `ERROR`, record the anomaly in a per-run quarantine log at `reports/validation/date_consistency.json`, and set the offending field(s) to `None` per the same `field_parse_status` semantics.
3. THE quarantine log SHALL include `award_id`, the raw source values, and the specific violation category.
4. THE CI quality gate SHALL fail the run if per-batch date-consistency error rate exceeds a configurable threshold (default: 1% of records).

### Requirement 4 — Coverage report reflects the new distinction

**User Story:** As a pipeline operator, I want the run-level coverage report to expose true-absence vs. parse-failure rates per field, so that I can prioritize upstream fixes against parse-failure spikes rather than chase red herrings in overall completeness numbers.

#### Acceptance Criteria

1. THE run-level quality report at `reports/quality/coverage.json` SHALL expose per-field `{present, absent, parse_failure}` counts, not just a single completeness percentage.
2. THE existing `data_quality.completeness` thresholds in `config/base.yaml` SHALL apply to `present + absent` combined (matching current semantics), and a separate `parse_failure_rate` threshold SHALL apply to `parse_failure` counts.
3. THE default `parse_failure_rate` threshold for `award_amount`, `program`, `phase` SHALL be `0.005` (0.5%); higher rates fail the quality gate.

## Non-goals

- Identity resolution (`company_uei`, `company_duns`) — covered by `specs/firm-identity-resolution/`.
- Time-key routing between `award_date` and `award_year` for pre-2004 rows — this is a documented convention, not a validation problem.
- Statistical imputation of `award_amount` from agency-phase-program medians — dropped from scope; see `specs/archive/superseded/data-imputation/README.md`.
- Congressional-district or NAICS derivation — deferred; the existing enrichers run where needed.
