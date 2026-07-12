# Tech-Area Transition Report — Tasks

## Phase 1 — Spec + v1 cohort CLI

- [x] T1 Write `requirements.md`, `design.md`, `tasks.md`
- [x] T2 Add `config/transition_reports/` YAMLs for
      `nanotechnology`, `quantum_information_science`, `hypersonics`
- [x] T3 Implement `scripts/data/build_tech_area_cohort.py`
- [x] T4 Run quantum + hypersonics; record sizes / Jaccard / spot-check in `validation.md`
- [x] T5 Nanotech smoke: Method A size exact match to 2,849 with ported keyword pack
- [x] T10 Quantum pack precision pass (`soft_patterns` + `title_or_multi`); hypersonics
      TPS/Mach `core_cooccur` rule — see `validation.md`
- [x] T17 Provisional findings reports for quantum + hypersonics (cohort / triangulation /
      agency composition; pathway rates deferred until signal artifacts exist)
      — `docs/quantum_information_science_sbir_transition_findings.md`,
        `docs/hypersonics_sbir_transition_findings.md`

## Phase 1b — Dark-majority area-awareness foundation

- [x] T11 `sbir_etl.utils.transition_report_paths.ReportPaths` + unit tests
- [x] T12 `sbir_etl.utils.transition_signals` enrichment helpers + unit tests;
      wire into `build_tech_area_cohort.py` (always write `deficiency_class`)
- [x] T13 Migrate `nano_form_d_temporal.py` to `--area` / `--legacy` (reference pattern)
- [~] T14 Migrate WS1, WS2, dark_firm_liveness (B82 optional), trademarks
  - [x] WS1 `nano_ws1_contract_evidence.py` (`resolve_area_paths`)
  - [x] WS2 `nano_ws2_resolve_no_uei.py` (`resolve_area_paths`)
  - [ ] dark_firm_liveness / trademarks
- [ ] T15 Migrate WS5a, alias graph, alias-expanded; gate WS5c on YAML
- [ ] T16 Migrate capture-recapture / survey_frame; nanotech `--legacy` cutover

## Phase 2 — Follow-ups

- [ ] T6 Point remaining `nano_*` dark-majority scripts at `ReportPaths`
- [ ] T8 Optional Method C for quantum (`G06N10`) once CPC extract is generalized
- [ ] T9 Dagster asset wrapper (only after CLI is stable across ≥3 areas)
