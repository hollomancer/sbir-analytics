# Firm Identity Resolution — Requirements

## Introduction

SBIR awards carry a heterogeneous mix of firm identifiers (`UEI`, `DUNS`, `CAGE`, and sometimes only a company name + address). The identifier space has changed over time: no unified federal ID pre-2004, DUNS as the primary key through April 4, 2022, UEI as the primary key thereafter. Firms whose registrations lapsed before the UEI transition never received a UEI at all. This produces a firm-level bifurcation: of multi-award firms in the 2000–2020 window, **40.9% are missing UEI on every award and 59.1% are missing on none** — only 2 firms out of 13,338 show scattered per-award patterns. UEI absence is a firm property, not per-record data-entry noise.

Downstream analyses that need to aggregate awards by firm — phase-transition detection, longitudinal capital-events analysis, commercialization benchmarking, cross-agency portfolio analysis — currently do this ad-hoc, each module maintaining its own idea of what constitutes "the same firm." Awards for the 5,452 multi-award firms with no UEI on any row are silently dropped from any join keyed on UEI.

This spec defines **one upstream ETL stage** that emits a canonical internal `firm_id` on every award, together with a provenance tier describing how the identity was resolved. `UEI`, `DUNS`, and `CAGE` become **output columns** populated where the resolution succeeds — not required inputs, not fields to be "filled" statistically. Where existing identifiers are present in the source, they are canonicalized and retained; where absent, they are recovered via external identifier crosswalks (SAM.gov current, SAM.gov historical, USASpending) and, failing that, resolved via fuzzy name+address matching against the same reference tables.

Firm identity is resolved **once**, upstream, so every downstream consumer joins on the same canonical key.

### Prior framing

An earlier `data-imputation` spec (now at `specs/archive/superseded/data-imputation/`) framed the UEI question as statistical imputation of a missing value. Empirical analysis of the SBIR bulk download showed this framing was wrong: identity is not a distribution to estimate but a firm property to look up. Nothing is being filled — identity is being resolved. See the archive README for the full reframe.

## Glossary

- **`firm_id`** — Stable internal canonical identifier, one per resolved firm, present on every award. Format: `firm_<method>_<hash>` (e.g., `firm_uei_ABC123` or `firm_fuzzy_a3f9c1e2`). Guaranteed to be identical across all awards attributed to the same firm.
- **Resolution method** — Which technique produced the identity match. Enum: `identifier_exact`, `duns_crosswalk`, `fuzzy_name_high`, `fuzzy_name_low`, `unresolved`.
- **Resolution source** — Which reference dataset the match was made against. Enum: `sam_gov_current`, `sam_gov_historical`, `usaspending`, `opencorporates`, `internal_dedup`, `none`.
- **Resolution score** — Numeric confidence in [0.0, 1.0]. `1.0` for identifier-exact matches, rapidfuzz score/100 for fuzzy matches, `0.0` for unresolved.
- **Canonicalization** — Reducing an existing identifier string to a normalized form (e.g., DUNS zero-padded to 9 digits, UEI uppercased and trimmed) before comparison. Distinct from resolution: canonicalization only touches values that are present in the source.
- **Reference table** — External dataset used as ground truth for identity lookup. See `Requirement 4` for the enumerated sources.

## Requirements

### Requirement 1 — Canonical firm_id emitted per award

**User Story:** As a downstream analyst, I want every award to carry a canonical `firm_id` that is identical across all awards belonging to the same firm, so that longitudinal firm aggregations do not need to reconcile across UEI, DUNS, and name variants at query time.

#### Acceptance Criteria

1. THE resolution stage SHALL emit a `firm_id` column on every award, populated for every row (including unresolved firms — see criterion 4).
2. THE `firm_id` SHALL be identical across all awards attributed to the same firm as of a given resolution run, and SHALL remain stable across re-runs unless the underlying reference tables change.
3. THE `firm_id` SHALL be deterministic given the same input awards + reference tables — a re-run without input changes SHALL produce byte-identical `firm_id` values.
4. WHERE resolution fails (no identifier match, no fuzzy-name match above the low threshold), THE `firm_id` SHALL be assigned a synthetic per-award value with method `unresolved` — never re-used across awards, so that unresolved rows cannot silently collapse into false firm aggregations.
5. THE `firm_id` SHALL NOT be a UEI or DUNS — it is an internal canonical ID, so that downstream code depending on it does not need to change when identifier-space regimes shift.

### Requirement 2 — Tiered resolution method with provenance

**User Story:** As a pipeline maintainer, I want every `firm_id` assignment to carry a tier-labeled provenance record, so that downstream consumers can filter to high-confidence resolutions (e.g., for precision-critical use cases) or accept the full recall (for exploratory analysis).

#### Acceptance Criteria

1. THE resolution stage SHALL emit, alongside `firm_id`, the columns `resolution_method`, `resolution_score`, and `resolution_source` on every award.
2. THE `resolution_method` values SHALL be one of `identifier_exact` (UEI, DUNS, or CAGE matched exactly against a reference row), `duns_crosswalk` (DUNS resolved to a UEI via SAM.gov's DUNS↔UEI mapping), `fuzzy_name_high` (rapidfuzz score ≥ 90 on normalized `(name, state)`), `fuzzy_name_low` (rapidfuzz score in `[75, 90)`), or `unresolved`.
3. THE `resolution_score` SHALL be `1.0` for `identifier_exact` and `duns_crosswalk`, the rapidfuzz score / 100 for fuzzy tiers, and `0.0` for `unresolved`.
4. THE `resolution_source` SHALL identify the reference dataset that produced the match, matching the enum in the Glossary.
5. THE columns SHALL persist through the `validated_sbir_awards` asset into Parquet and DuckDB storage without transformation, and SHALL be surfaced as node properties on `:Organization` nodes in Neo4j (`resolution_method`, `resolution_score`, `resolution_source`).

### Requirement 3 — Output identifier columns populated where resolvable

**User Story:** As a downstream consumer, I want `UEI`, `DUNS`, and `CAGE` to be populated on each award where the resolution succeeded in recovering them, so that existing code keyed on these identifiers continues to work without needing to know about the new `firm_id`.

#### Acceptance Criteria

1. WHERE the source award already carries a valid identifier (UEI/DUNS/CAGE), THE resolution stage SHALL canonicalize it (see Glossary) and retain the value in the output column.
2. WHERE the source award is missing an identifier BUT the resolved firm has that identifier in the reference table, THE resolution stage SHALL populate the output column with the value from the reference table, and SHALL record the source in a new `<identifier>_source` column (values: `sbir_source`, `sam_gov_current`, `sam_gov_historical`, `usaspending`, `absent`).
3. THE resolution stage SHALL NOT overwrite a source-provided identifier with a reference-derived value unless the two differ AND the source value is malformed (invalid checksum for DUNS, invalid length for UEI); in the malformed case, the reference value replaces it and the anomaly is logged at `reports/resolution/identifier_conflicts.json`.
4. WHERE resolution cannot recover an identifier (unresolved firm, or resolved firm with no identifier in any reference table — e.g., pre-2004 firms whose DUNS registration lapsed before the 2022 UEI transition), THE output column SHALL remain `None` with `<identifier>_source = absent`.

### Requirement 4 — Reference table cascade

**User Story:** As a pipeline operator, I want the resolution stage to consult reference tables in a documented cascade, so that I know which sources are used, in what order, and where the coverage boundaries lie.

#### Acceptance Criteria

1. THE resolution stage SHALL consult reference tables in the following order, stopping at the first match: `sam_gov_current` → `sam_gov_historical` → `usaspending` → `internal_dedup`.
2. THE `sam_gov_current` reference SHALL be loaded via the existing `sbir_etl.extractors.sam_gov.SAMGovExtractor`.
3. THE `sam_gov_historical` reference SHALL be loaded from a monthly SAM.gov historical entity extract; the fetch and refresh cadence is out of scope for this spec and SHALL be documented in a follow-up operational runbook.
4. THE `usaspending` reference SHALL reuse existing USAspending vendor tables already ingested by `packages/sbir-analytics/sbir_analytics/assets/usaspending_ingestion.py`.
5. THE `internal_dedup` reference SHALL be the SBIR awards table itself — used only for cross-award identifier propagation, where the same normalized `(company_name, state)` appears with a known identifier on some rows and no identifier on others (leverages the firm-level bifurcation finding: consistent presence or absence is the dominant pattern).
6. Fuzzy-name resolution SHALL run only after identifier-based cascade fails, and SHALL query the union of the identifier reference tables. The blocker key SHALL be `(normalized_name_prefix, state)` matching the existing `sbir_etl/enrichers/company_fuzzy_matcher.py` implementation.

### Requirement 5 — Reuses existing infrastructure

**User Story:** As a reviewer, I want to confirm the resolution stage does not duplicate machinery that already exists, so that I can approve it as a specification-and-orchestration change rather than a build-from-scratch project.

#### Acceptance Criteria

1. THE resolution stage SHALL invoke `sbir_etl.enrichers.company_fuzzy_matcher.enrich_awards_with_companies` for the bulk-mode name+identifier match against the joined reference tables. The function's existing `_match_score`, `_match_method`, `_matched_company_idx`, `_match_candidates` output columns SHALL be re-emitted under the names in Requirement 2, with the mapping documented in `design.md`.
2. THE resolution stage SHALL invoke `sbir_etl.utils.company_canonicalizer.canonicalize_companies_from_awards` for cross-award internal-dedup consolidation (Requirement 4, criterion 5). The function's `UEI > DUNS > normalized_name` preference rule SHALL be preserved.
3. THE resolution stage SHALL NOT re-implement rapidfuzz-based matching, phonetic matching, or the identifier-first cascade — these are already present in `company_fuzzy_matcher.py` and shall be used as-is.
4. THE `sbir_etl/ot_consortium/runner.py:175` use of `VendorResolver` (a proof-of-concept non-transition caller) SHALL be updated to consume `firm_id` from the resolution stage instead of running its own resolver invocation. This is an incidental cleanup, not a scope creep.

### Requirement 6 — Precision floor: phase-transition detection

**User Story:** As the owner of the transition-detection benchmark, I want promotion of fuzzy matches into `firm_id` to preserve the ≥85% precision benchmark on the existing transition-detection evaluation, so that recall improvements do not silently degrade precision.

#### Acceptance Criteria

1. THE resolution stage SHALL be validated against the existing phase-transition precision benchmark defined in `packages/sbir-ml/` evaluation tests, per `CLAUDE.md`'s stated ≥85% precision floor.
2. THE evaluation SHALL be run with `firm_id` used as the join key in place of the current ad-hoc identifier joins. Precision SHALL NOT regress below 0.85.
3. WHERE precision would regress, the fuzzy tier admitted to `firm_id` SHALL be tightened (e.g., raise the `fuzzy_name_high` threshold) until precision is recovered. The chosen threshold and its measured precision SHALL be recorded in `reports/resolution/precision_calibration.json`.
4. THE CI gate for transition detection SHALL fail if the benchmark drops below 0.85 after firm-identity resolution is enabled.

### Requirement 7 — Recall lift: longitudinal firm view

**User Story:** As an analyst running commercialization and capital-events cohort analyses, I want awards belonging to the same firm to be joinable on `firm_id` across identifier-space regimes (pre-DUNS, DUNS-only, UEI-era) and across the 5,452 multi-award firms currently stranded by UEI absence, so that longitudinal joins recover previously-invisible awards without introducing false unifications.

#### Acceptance Criteria

1. THE resolution stage SHALL be validated against a fixed sample of multi-award firms constructed from the SBIR bulk download at `data/raw/sbir/award_data.csv`, split into two evaluation sets:
   - **Recall-lift set:** the 5,452 multi-award firms observed to be missing UEI on every award in the 2000–2020 window. The resolution stage SHALL assign a shared `firm_id` to at least 60% of the awards belonging to these firms via the identifier or fuzzy cascade.
   - **False-unification set:** a manually curated sample of ≥100 firm pairs that are known to be distinct despite similar names (e.g., corporate suffixes, common surnames, holdings/subsidiary confusion). The resolution stage SHALL NOT assign the same `firm_id` to any pair in this set.
2. THE recall-lift and false-unification results SHALL be reported in `reports/resolution/recall_precision.json` per run.
3. THE resolution stage SHALL surface, for downstream capital-events and commercialization consumers, a `firm_award_count` column derived by counting awards sharing the same `firm_id` — so that cohort filters (e.g., "firms with ≥15 Phase II awards") can key on the resolved identity rather than the raw UEI.

### Requirement 8 — Pipeline position and idempotency

**User Story:** As a pipeline maintainer, I want the resolution stage to run at a well-defined position in the DAG that does not disturb existing raw quality metrics, so that source-completeness measurements remain truthful and re-runs are cheap.

#### Acceptance Criteria

1. THE resolution stage SHALL run **after** extraction and after strict validation (`sbir_etl/validators/sbir_awards.py`), and **before** identifier-dependent enrichment (`sbir_etl/enrichers/company_enrichment.py`, `sbir_etl/enrichers/sec_edgar/`, `sbir_etl/enrichers/categorization.py`).
2. THE quality-check coverage report SHALL continue to measure source-completeness on the pre-resolution `UEI` / `DUNS` fields (so that the ~40% pre-resolution UEI-missing rate remains visible as a source-data metric), and SHALL emit a separate `reports/resolution/coverage.json` recording post-resolution effective coverage.
3. THE resolution stage SHALL be idempotent: running it twice on the same input awards + reference tables SHALL produce identical output.
4. THE resolution stage SHALL be materialized as a Dagster asset in `packages/sbir-analytics/`, depending on `validated_sbir_awards` and any reference-table assets it consumes.

## Non-goals

- **Statistical imputation of any field.** Superseded framing; see archived `data-imputation` spec.
- **Time-key routing for `award_date`.** Documented as a convention in `docs/steering/`, not a spec — the correct operation is "use `award_date` where present, fall back to `Award Year`" and requires no algorithmic work.
- **Validator strictness for `award_amount` / `program` / `phase`.** Covered by `specs/input-validation-hardening/`.
- **Merging or splitting existing `:Organization` nodes in Neo4j.** The `specs/unify-company-into-organization/` spec covers label unification and assumes an identifier as the join key. This spec produces the `firm_id` that Neo4j loaders will use; graph-side migrations are out of scope.
- **Real-time entity resolution.** This is a batch upstream ETL stage; sub-second resolution APIs are not required.
- **Manual review UI for fuzzy matches.** Fuzzy-tier matches are recorded with score and candidate list in `_match_candidates`; a review workflow is a follow-up if the false-unification rate justifies it.

## Reference: existing infrastructure

The following modules already implement most of the algorithmic work this spec requires. The resolution stage is largely composition and provenance emission, not new algorithms:

- `sbir_etl/enrichers/company_fuzzy_matcher.py` — Identifier-first + rapidfuzz-based bulk matcher. Entry point: `enrich_awards_with_companies(awards, master)`. Called today by `scripts/data/run_sbir_enrichment_check.py`, `sbir_etl/utils/company_canonicalizer.py`, `examples/enhanced_matching_demo.py`. **Fully standalone; not coupled to transition detection.**
- `sbir_etl/utils/company_canonicalizer.py` — Cross-award internal-dedup with UEI > DUNS > normalized-name preference. Consumes the fuzzy matcher.
- `sbir_etl/extractors/sam_gov.py` — SAM.gov entity extract loader. Currently loads a single snapshot; `Requirement 4, criterion 3` adds the historical variant as a follow-up.
- `packages/sbir-ml/sbir_ml/transition/features/vendor_resolver.py` — In-memory single-query resolver. Consumed by `sbir_etl/ot_consortium/runner.py`. Complementary to the bulk matcher, not a duplicate — used for lookup-mode queries in analytic code, not the bulk ETL stage this spec defines.
- `sbir_etl/enrichers/company_enrichment.py` — Federal API lookups (USASpending, SAM.gov, FPDS). Provides the reference tables consumed by the resolution stage.
