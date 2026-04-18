# Data Imputation — Implementation Plan

Execution order is top-to-bottom within each phase. Phases 1–3 are required; Phase 4
is the initial method rollout; Phase 5 hardens operability.

## Phase 1 — Foundation

- [ ] 1.1 Add `sbir_etl/imputation/` module skeleton with `registry.py`, `provenance.py`,
  `config.py`, `runner.py`, and `methods/__init__.py`.
- [ ] 1.2 Extend `sbir_etl/models/award.py` with `raw_<field>` shadow fields for
  `award_date`, `award_amount`, `company_uei`, `company_duns`, `congressional_district`,
  `contract_end_date`, `naics_code`; add `<field>_is_imputed` booleans; add
  `imputation: list[ImputationEntry]` field.
  → **verify**: Pydantic model round-trips a fixture record; raw fields serialize to
  Parquet via the existing `validated_sbir_awards` persistence path
  (`pandas.DataFrame.to_parquet`, see
  `packages/sbir-analytics/sbir_analytics/assets/sbir_ingestion.py:158`).
- [ ] 1.3 Add `ImputationEntry` model in `sbir_etl/models/enrichment.py` (or new
  `imputation.py`) with `field`, `method`, `method_version`, `confidence`,
  `source_fields`, `imputed_at`.
- [ ] 1.4 Implement `ImputationMethod` protocol + `ImputationRegistry` with topological
  ordering and cycle detection.
  → **verify**: Unit test registers two methods with a dependency, asserts correct
  execution order; cycle raises at load time.
- [ ] 1.5 Implement `ImputationRunner` that clones raw columns, applies methods in
  order, builds the provenance struct, and emits `<field>_is_imputed` booleans.
  → **verify**: Unit test on a 10-row fixture shows raw columns byte-identical and
  effective columns populated.
- [ ] 1.6 Add `imputation` section to `config/base.yaml` with per-method toggles and
  `dry_run` flag; wire through `sbir_etl/config/` schemas.
  → **verify**: `pytest tests/unit/test_config.py` passes with new section loaded.

## Phase 2 — Provenance & quality integration

- [ ] 2.1 Split `sbir_etl/quality/checks.py` completeness checks into `raw_*` and
  `effective_*` variants; measure raw against source thresholds and effective against
  post-imputation thresholds.
  → **verify**: Existing quality report unchanged for raw; new
  `reports/imputation/coverage.json` emitted.
- [ ] 2.2 Update `config/base.yaml` thresholds to split raw vs effective completeness
  for `award_date`, `award_amount`, `company_uei`, `congressional_district`.
  → **verify**: Raw `award_date` threshold set near actual coverage (~50%); effective
  threshold remains 95%.
- [ ] 2.3 Emit run-level imputation summary log to `reports/imputation/summary.json`
  with per-field impute rate, per-method counts, per-confidence distribution.
- [ ] 2.4 Add `imputation_methods` list property and `<field>_is_imputed` booleans to
  Neo4j loaders in `packages/sbir-graph/sbir_graph/loaders/`.
  → **verify**: Cypher query `MATCH (a:Award) WHERE a.award_date_is_imputed = true
  RETURN count(a)` returns expected count on fixture load.

## Phase 3 — Dagster integration

- [ ] 3.1 Create `imputed_sbir_awards` asset in
  `packages/sbir-analytics/sbir_analytics/assets/imputation.py` depending on
  `validated_sbir_awards`.
- [ ] 3.2 Rewire downstream enrichment assets (`company_enrichment`,
  `congressional_district_*`, etc.) to depend on `imputed_sbir_awards` instead of
  `validated_sbir_awards`.
  → **verify**: `dagster asset materialize --select imputed_sbir_awards+` succeeds end
  to end on fixture data.
- [ ] 3.3 Add quality-check asset that emits `reports/imputation/coverage.json` and
  fails materialization if effective thresholds not met.

## Phase 4 — Method implementations

- [ ] 4.1 `award_date.cascade` — cascade through `proposal_award_date`,
  `contract_start_date`, `date_of_notification`, `solicitation_close_date +
  agency_lag`, `fiscal_year` midpoint. Build agency-lag lookup at runner init.
  → **verify**: On a labeled fixture, cascade fills ≥95% of null `award_date`s;
  agency-lag derivation is deterministic.
- [ ] 4.2 `identifiers.cross_award_backfill` — build `(normalized_name, state)` →
  UEI/DUNS lookup from non-null records, apply to null rows; log conflicts to
  `reports/imputation/uei_conflicts.json`.
  → **verify**: Fixture with 3 awards from same company (1 with UEI, 2 without) ends
  with all 3 having the same UEI and `_is_imputed` correctly flagged.
- [ ] 4.3 **Prerequisite — extend solicitation extraction.** Add
  `phase_i_max_amount`, `phase_ii_max_amount`, and
  `period_of_performance_months` (per phase) to `sbir_etl/models/solicitation.py` and
  populate them in `sbir_etl/extractors/solicitation.py`. Backfill historical
  solicitations from SBIR.gov bulk download.
  → **verify**: Solicitation fixtures parse the new fields; coverage of solicitations
  with at least `phase_i_max_amount` is ≥80% on a recent fiscal-year sample.
- [ ] 4.4 `award_amount.solicitation_max` — join awards to solicitations on
  `(solicitation_number, topic_code)`; use phase max as imputed value when the
  agency-phase modal cluster equals the max (≥80%), otherwise as a hard upper bound on
  §4.5 fallback.
  → **verify**: Backtest accuracy on labeled awards with known solicitation linkage
  ≥90% MAPE for high-confidence tier; ceiling is never exceeded.
- [ ] 4.5 `award_amount.agency_phase_median` — group-median imputation (only runs when
  §4.4 did not produce a value) with min group size of 10, $5M cap check.
  → **verify**: Fixture with known group medians produces expected imputed values;
  small groups are skipped.
- [ ] 4.6 `geography.congressional_district` — wrap existing
  `congressional_district_resolver.py`; map resolver score to provenance tier
  (≥0.90 → high, 0.70–0.89 → medium, <0.70 → low).
  → **verify**: Uses existing resolver fixtures; provenance tier matches the mapping
  table in design §4.6.
- [ ] 4.7 `contract_dates.solicitation_period_of_performance` — derive
  `contract_end_date` from `contract_start_date + solicitation period_of_performance`
  when solicitation linkage exists.
  → **verify**: When solicitation period is present, end date matches start +
  period_of_performance_months; raw value preserved.
- [ ] 4.8 `contract_dates.end_date_repair` — fallback when §4.7 did not fill it;
  uses phase-typical durations.
  → **verify**: Inverted end dates are replaced; original values preserved in
  `raw_contract_end_date`.
- [ ] 4.9 `naics.solicitation_topic` — derive NAICS from solicitation topic
  research-domain crosswalk (reuses agency topic-prefix mappings where available).
  → **verify**: For a fixture set of awards with known solicitation linkage and known
  NAICS, top-1 accuracy ≥75% on the agency-topic crosswalk.
- [ ] 4.10 `naics.hierarchical_fallback` — validate 6-digit code; fall back to
  shortest valid prefix via `sbir_etl/enrichers/naics/`.
  → **verify**: Invalid 6-digit codes with valid 4-digit prefixes are repaired;
  already-valid codes are unchanged.
- [ ] 4.11 `naics.abstract_nn` — TF-IDF nearest-neighbor on abstracts ≥100 chars;
  `enabled: false` by default. Runs only when §4.9 produced nothing.
  → **verify**: Method runs under opt-in flag; `confidence: low` applied.

## Phase 5 — Backtest, validation, docs

- [ ] 5.1 Implement `sbir_etl/imputation/backtest.py` with `mask_and_reimpute(field,
  fraction)` and `run_backtest_suite()`.
  → **verify**: CLI `python -m sbir_etl.imputation.backtest` produces
  `reports/imputation/backtest.json` with per-method accuracy/MAE.
- [ ] 5.2 Record baseline backtest accuracy to
  `reports/imputation/backtest_baseline.json`; add CI gate that fails on ≥5pp
  regression.
- [ ] 5.3 Re-run `packages/sbir-ml/` transition-detection evaluation with imputed-opt-in
  mode; confirm ≥85% precision benchmark holds.
  → **verify**: Evaluation report shows precision ≥0.85 both with and without imputed
  values.
- [ ] 5.4 Add integration test in `tests/integration/` that materializes
  `imputed_sbir_awards` + downstream enrichment on a fixture snapshot and asserts
  provenance fields round-trip through DuckDB and Neo4j.
- [ ] 5.5 Document the imputation layer in `docs/steering/imputation.md`: method
  catalog, confidence definitions, consumer contract, and operator runbook for
  toggling methods.
- [ ] 5.6 Update CLAUDE.md "Key Directories" table to reference
  `sbir_etl/imputation/`; add a one-line note about `raw_*` shadow columns under
  "Common Patterns".
