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
- [x] T18 Publication format accepted: policy brief = default NSET-facing deliverable;
      technical findings = appendix (`publication-format.md`); nanotech policy brief +
      Q/H provisional briefs; technical nanotech Summary trimmed to point at brief

## Phase 1b — Dark-majority area-awareness foundation

- [x] T11 `sbir_etl.utils.transition_report_paths.ReportPaths` + unit tests
- [x] T12 `sbir_etl.utils.transition_signals` enrichment helpers + unit tests;
      wire into `build_tech_area_cohort.py` (always write `deficiency_class`)
- [x] T13 Migrate `nano_form_d_temporal.py` to `--area` / `--legacy` (reference pattern)
- [x] T14 Migrate WS1, WS2, dark_firm_liveness (B82 optional), trademarks
  - [x] WS1 `nano_ws1_contract_evidence.py` (`resolve_area_paths`)
  - [x] WS2 `nano_ws2_resolve_no_uei.py` (`resolve_area_paths`)
  - [x] dark_firm_liveness / trademarks (`resolve_area_paths`; SBIR CSV, B82
        extract, USPTO zips stay global — only cohort input + outputs are area-scoped)
- [x] T15 Migrate WS5a, alias graph, alias-expanded; gate WS5c on YAML
  - [x] `nano_ws5a_subawards.py`, `build_firm_alias_graph.py`,
        `nano_alias_expanded_evidence.py` → `resolve_area_paths`
  - [x] WS5c gated on area YAML `sector_registries:` list
        (`ReportPaths.load_config()`); nanotech enables clinical_trials + fda_510k,
        quantum/hypersonics declare `[]` → no-op
- [~] T16 Migrate capture-recapture / survey_frame; nanotech `--legacy` cutover
  - [x] `nano_capture_recapture.py`, `nano_survey_frame.py` → `resolve_area_paths`
  - [ ] nanotech `--legacy` cutover — deliberate global default flip (unflagged
        nano → `data/reports/nanotechnology/`); left as its own decision since
        every migrated script currently keeps legacy-as-default. Cohort production
        under the new layout is `build_tech_area_cohort.py --area nanotechnology`
        (blocked on porting the hand-maintained NNI Method-B table from
        `build_nano_cohort.py`)

## Phase 2 — Follow-ups

- [x] T6 Point remaining `nano_*` dark-majority scripts at `ReportPaths`
      — `nano_ws5b_sam_status`, `nano_subaward_leverage`,
      `nano_dark_firm_maintenance_lapses`, `nano_ma_signal`,
      `nano_prime_acquisitions`, `nano_survival_analysis`,
      `nano_prime_edgar_filings`, `nano_verify_report_figures` migrated
      (figures use `paths.analysis_dir`; added `prime_edgar_text`,
      `prime_deal_terms`, `dark_firm_maintenance_lapses` stems).
      `build_nano_cohort.py` intentionally NOT migrated — it is the legacy v0
      cohort builder that `build_tech_area_cohort.py` replaces; migrating it would
      create two builders both writing the area cohort.
- [ ] T8 Optional Method C for quantum (`G06N10`) once CPC extract is generalized
- [ ] T9 Dagster asset wrapper (only after CLI is stable across ≥3 areas)
- [ ] T19 When digest / Form D / M&A exist: extend Q/H policy-brief headline tables with
      channel rows (`Measure | Result | How to use it`) + Policy interpretation blocks;
      hypersonics prioritizes WS1 + WS5a over Form D; quantum keeps small-N caveats
- [ ] T20 Optional: `build_tech_area_cohort.py` emits `policy_brief_stub.md` from
      `overlap_summary.json` + agency aggregates
