# Tasks — NAICS Enricher Consolidation

## Stage 1 — Delete shim re-exports (small, tractable)

- [ ] **T1.1** Update all imports in
      `tests/unit/enrichers/naics/test_fiscal_strategies.py` and
      `tests/unit/enrichers/test_naics_strategies.py` to point at
      `sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies`.
- [ ] **T1.2** Delete `strategies/agency_defaults.py`,
      `strategies/original_data.py`, `strategies/sector_fallback.py`,
      `strategies/topic_code.py`.
- [ ] **T1.3** Verify no remaining hits for
      `"Backward-compat re-export"` in `sbir_etl/`.

## Stage 2 — Audit the three NAICS → BEA mappers

- [ ] **T2.1** Diff
      `sbir_etl/transformers/naics_bea_mapper.py`,
      `sbir_etl/transformers/naics_to_bea.py`, and
      `sbir_etl/enrichers/fiscal_bea_mapper.py`. Produce a table showing:
      class/function name, inputs, outputs, crosswalk source, hierarchical
      fallback behavior, test coverage.
- [ ] **T2.2** Identify which is the canonical implementation (likely
      `enrichers/fiscal_bea_mapper.py` given it is used by
      `weekly_awards_report.py`). Record the decision in `design.md`.

## Stage 3 — Consolidate mappers

- [ ] **T3.1** Capture a golden-file of current outputs: feed a set of
      representative NAICS codes through each of the three mappers and
      record `(naics_code, bea_sector, confidence, source)` tuples.
- [ ] **T3.2** Port any unique behaviors from the losing mappers into the
      canonical one. Typical candidates: hierarchical fallback thresholds,
      sector aggregation rules, weighted-allocation support.
- [ ] **T3.3** Update all call sites to import from the canonical path.
      `grep` sites: `sbir_etl/`, `packages/`, `scripts/`.
- [ ] **T3.4** Delete the non-canonical modules.
- [ ] **T3.5** Re-run the golden-file comparison — expect zero diff.

## Stage 4 — Strategy registration for the fiscal NAICS enricher

- [ ] **T4.1** Introduce
      `sbir_etl/enrichers/naics/fiscal/strategy_registry.py` exposing a
      single `default_strategies()` factory that returns the ordered
      strategy list.
- [ ] **T4.2** Refactor `NAICSFiscalEnricher` to accept a strategy list in
      its constructor (default: `default_strategies()`). Existing
      behavior unchanged.
- [ ] **T4.3** Update tests to exercise custom strategy orderings through
      the constructor to lock in the registration pattern.

## Stage 5 — Cleanup

- [ ] **T5.1** `ruff check sbir_etl/enrichers/naics sbir_etl/transformers`
      passes.
- [ ] **T5.2** `mypy` on touched files — zero new errors, zero new
      `type: ignore`.
- [ ] **T5.3** Update `docs/steering/` NAICS documentation to reference the
      single canonical mapper.

## Estimate

- Stage 1: 0.5 day (shim cleanup)
- Stage 2: 0.5 day (audit)
- Stage 3: 1 day (consolidation)
- Stage 4: 0.5 day (registration)
- Stage 5: 0.5 day (cleanup)

Total: ~3 days.

## Risk

Medium. The three NAICS → BEA mappers may have subtle behavior differences
around hierarchical fallback confidence scoring. The golden-file test in
T3.1/T3.5 is the primary safety net — do NOT skip it.
