# Tasks — Weekly Awards Report Refactor

Sequenced tasks. Each should land as an independent PR with tests.

## Stage 0 — Baseline

- [ ] **T0.1** Capture a golden-file output: run the current script against a
      fixed `--days` window with network calls stubbed, store markdown in
      `tests/fixtures/weekly_awards_report/golden.md`. Timestamps
      normalized to a sentinel.
- [ ] **T0.2** Add `tests/unit/reporting/weekly/test_golden.py` that runs the
      current script as a subprocess (or imports `main`) against the fixture
      and diffs against `golden.md`. This test MUST pass before any
      extraction begins and stay green through every stage below.

## Stage 1 — Pure-function extraction (no behavior change)

- [ ] **T1.1** Move `format_amount`, `_format_date`, `_escape_md_cell`,
      `build_sbir_award_url`, `build_solicitation_url`,
      `build_usaspending_url`, `generate_markdown` to
      `sbir_etl/reporting/weekly/rendering.py`. Unit tests per function.
- [ ] **T1.2** Move `_company_key`, `clean_and_dedup_awards`,
      `fetch_weekly_awards`, `_resolve_csv_path`, `_check_data_freshness`
      to `sbir_etl/reporting/weekly/fetching.py`. Stub `httpx.get` in tests.
- [ ] **T1.3** Move `verify_reference_links`,
      `_print_link_verification_report` to
      `sbir_etl/reporting/weekly/link_verification.py`.

## Stage 2 — Enrichment extraction

- [ ] **T2.1** Extract `lookup_pi_external_data`,
      `lookup_usaspending_recipients`, `lookup_sam_entities`,
      `lookup_opencorporates`, `poll_press_wire` into
      `sbir_etl/reporting/weekly/enrichment.py`. These are thin wrappers
      over `sbir_etl/enrichers/*` that add budgeting / rate-limiting —
      move the budgeting helpers (`_stage_deadline`, `_past_deadline`) too.
- [ ] **T2.2** Extract `fetch_solicitation_topics`,
      `enrich_with_inflation`, `resolve_congressional_districts`,
      `map_naics_to_bea_sectors` into the same module.
- [ ] **T2.3** Accept an injected `USAspendingAPIClient`,
      `OpenAIClient`, `SolicitationExtractor` on each helper so tests can
      use mocks without monkeypatching module-level clients.

## Stage 3 — LLM generation extraction

- [ ] **T3.1** Extract `_award_digest`, `_company_history_digest`,
      `_pi_history_digest`, `_pi_external_digest` into
      `sbir_etl/reporting/weekly/llm_digests.py` as pure functions.
- [ ] **T3.2** Extract `research_companies`, `generate_weekly_synopsis`,
      `generate_award_descriptions`, `generate_company_diligence`,
      `generate_pi_diligence` into
      `sbir_etl/reporting/weekly/llm.py`. Each takes an `OpenAIClient`
      (already injectable — finish the job) and the relevant inputs, returns
      typed dataclasses.

## Stage 4 — Orchestrator + thin CLI

- [ ] **T4.1** Create `sbir_etl/reporting/weekly/orchestrator.py` with a
      `WeeklyAwardsReportBuilder` dataclass that composes fetching,
      enrichment, llm, and rendering stages. Takes dependencies via
      constructor.
- [ ] **T4.2** Reduce `scripts/data/weekly_awards_report.py` to argparse +
      `WeeklyAwardsReportBuilder(...).run()`. Target ≤200 lines.
- [ ] **T4.3** Verify the golden-file test still passes.

## Stage 5 — Follow-up

- [ ] **T5.1** Run `ruff check` and `mypy sbir_etl/reporting/weekly` — zero
      errors, zero new `type: ignore`.
- [ ] **T5.2** Raise coverage on new modules to the R4 targets.
- [ ] **T5.3** Remove the `_lib_*` alias imports; call the canonical
      enrichers directly.

## Estimate

- Stage 0: 0.5 day
- Stage 1: 1 day
- Stage 2: 1.5 days
- Stage 3: 1 day
- Stage 4: 0.5 day
- Stage 5: 0.5 day

Total: ~5 days for one engineer.
