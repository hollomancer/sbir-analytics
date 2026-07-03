# Tasks — NAICS Enricher Consolidation

## Status (2026-07-02)

**Largely complete — 11 of 16 tasks verified done against the codebase.** Stage 1
(shim deletion), Stage 3 consolidation (canonical mapper is
`sbir_etl/enrichers/fiscal_bea_mapper.py`; the two `transformers/` mappers are
deleted and unique behavior was ported), and Stage 4 (strategy registry) are
implemented. Ruff and mypy pass on the touched modules (verified 2026-07-02).
Remaining open items: the Stage 2 audit artifacts (T2.1/T2.2 — no audit table or
`design.md` decision record exists in this spec dir; the consolidation happened
without them), the golden-file comparison (T3.1/T3.5 — no golden-file test
exists, and the losing mappers are already deleted so it can no longer be
produced as specified), and the steering-docs update (T5.3 —
`docs/steering/enrichment-patterns.md` does not reference the canonical mapper).

## Stage 1 — Delete shim re-exports (small, tractable)

- [x] **T1.1** Update all imports in
      `tests/unit/enrichers/naics/test_fiscal_strategies.py` and
      `tests/unit/enrichers/test_naics_strategies.py` to point at
      `sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies`.
      — implemented: both test files import from
      `sbir_etl.enrichers.naics.fiscal.strategies.simple_strategies` (e.g.
      `test_naics_strategies.py:19-24`); no shim imports remain.
- [x] **T1.2** Delete `strategies/agency_defaults.py`,
      `strategies/original_data.py`, `strategies/sector_fallback.py`,
      `strategies/topic_code.py`.
      — implemented: files no longer exist;
      `sbir_etl/enrichers/naics/fiscal/strategies/` now contains only
      `base.py`, `simple_strategies.py`, `text_inference.py`,
      `usaspending_dataframe.py`.
- [x] **T1.3** Verify no remaining hits for
      `"Backward-compat re-export"` in `sbir_etl/`.
      — verified: zero grep hits in `sbir_etl/` (2026-07-02).

## Stage 2 — Audit the three NAICS → BEA mappers

- [ ] **T2.1** Diff
      `sbir_etl/transformers/naics_bea_mapper.py`,
      `sbir_etl/transformers/naics_to_bea.py`, and
      `sbir_etl/enrichers/fiscal_bea_mapper.py`. Produce a table showing:
      class/function name, inputs, outputs, crosswalk source, hierarchical
      fallback behavior, test coverage.
      — note (2026-07-02): no audit table exists in the repo, and the two
      `transformers/` mappers have since been deleted, so the diff can no
      longer be produced as written. Effectively superseded by the completed
      Stage 3 consolidation.
- [ ] **T2.2** Identify which is the canonical implementation (likely
      `enrichers/fiscal_bea_mapper.py` given it is used by
      `weekly_awards_report.py`). Record the decision in `design.md`.
      — note (2026-07-02): the decision was made in practice
      (`enrichers/fiscal_bea_mapper.py` is canonical; see the port comment at
      `fiscal_bea_mapper.py:58-59`), but no `design.md` exists in this spec
      directory to record it.

## Stage 3 — Consolidate mappers

- [ ] **T3.1** Capture a golden-file of current outputs: feed a set of
      representative NAICS codes through each of the three mappers and
      record `(naics_code, bea_sector, confidence, source)` tuples.
      — note (2026-07-02): no golden-file artifact or test found in the repo;
      the non-canonical mappers are already deleted, so this safety net was
      skipped.
- [x] **T3.2** Port any unique behaviors from the losing mappers into the
      canonical one. Typical candidates: hierarchical fallback thresholds,
      sector aggregation rules, weighted-allocation support.
      — implemented: `sbir_etl/enrichers/fiscal_bea_mapper.py:58-59` documents
      the fallback table "Ported from the deleted
      sbir_etl.transformers.naics_bea_mapper.NAICSBEAMapper so that
      map_naics_to_bea_summary() has a last-resort fallback matching the
      deleted mapper's behavior."
- [x] **T3.3** Update all call sites to import from the canonical path.
      `grep` sites: `sbir_etl/`, `packages/`, `scripts/`.
      — implemented: `sbir_etl/transformers/sbir_fiscal_pipeline.py:19` and
      `sbir_etl/transformers/fiscal/district_allocator.py:73` import
      `NAICSToBEAMapper` from `..enrichers.fiscal_bea_mapper`; grep of
      `sbir_etl/`, `packages/`, `scripts/`, `tests/` shows no remaining
      imports of the deleted modules.
- [x] **T3.4** Delete the non-canonical modules.
      — implemented: `sbir_etl/transformers/naics_bea_mapper.py` and
      `sbir_etl/transformers/naics_to_bea.py` no longer exist.
- [ ] **T3.5** Re-run the golden-file comparison — expect zero diff.
      — note (2026-07-02): blocked/skipped along with T3.1 (no golden file was
      ever captured).

## Stage 4 — Strategy registration for the fiscal NAICS enricher

- [x] **T4.1** Introduce
      `sbir_etl/enrichers/naics/fiscal/strategy_registry.py` exposing a
      single `default_strategies()` factory that returns the ordered
      strategy list.
      — implemented: `sbir_etl/enrichers/naics/fiscal/strategy_registry.py`
      with `default_strategies(usaspending_df=None)` returning the six
      strategies in confidence order.
- [x] **T4.2** Refactor `NAICSFiscalEnricher` to accept a strategy list in
      its constructor (default: `default_strategies()`). Existing
      behavior unchanged.
      — implemented: `FiscalNAICSEnricher.__init__` in
      `sbir_etl/enrichers/naics/fiscal/enricher.py` accepts
      `strategies: list[EnrichmentStrategy] | None = None` and falls back to
      `default_strategies(usaspending_df=usaspending_df)`.
- [x] **T4.3** Update tests to exercise custom strategy orderings through
      the constructor to lock in the registration pattern.
      — implemented: `tests/unit/enrichers/naics/test_fiscal_strategies.py`
      (`TestDefaultStrategies`, `TestFiscalNAICSEnricherStrategiesArg::
      test_custom_strategies_override_default`,
      `test_default_strategies_used_when_none_passed`).

## Stage 5 — Cleanup

- [x] **T5.1** `ruff check sbir_etl/enrichers/naics sbir_etl/transformers`
      passes.
      — verified 2026-07-02: "All checks passed!".
- [x] **T5.2** `mypy` on touched files — zero new errors, zero new
      `type: ignore`.
      — verified 2026-07-02: `uv run mypy sbir_etl/enrichers/naics
      sbir_etl/enrichers/fiscal_bea_mapper.py` → "Success: no issues found in
      12 source files".
- [ ] **T5.3** Update `docs/steering/` NAICS documentation to reference the
      single canonical mapper.
      — note (2026-07-02): `docs/steering/enrichment-patterns.md` contains a
      generic NAICS enrichment example but no reference to
      `enrichers/fiscal_bea_mapper.py` as the canonical mapper.

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
