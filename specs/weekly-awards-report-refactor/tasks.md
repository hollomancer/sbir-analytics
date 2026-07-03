# Tasks — Weekly Awards Report Refactor

> **Status (2026-07-02):** Substantially complete. The 2,807-line monolith is now a
> 116-line CLI over `sbir_etl/reporting/weekly/` (models, fetching, enrichment,
> llm_digests, llm, rendering, link_verification, debug, orchestrator), with the
> golden-file test green across the extraction and `mypy`/`ruff` clean. Remaining:
> T2.3 (injected clients), the typed-dataclass half of T3.2, coverage targets
> (T5.2), and the `_lib_*` alias removal (T5.3 — kept deliberately, see note).
> Discovered during Stage 0: the script was unimportable on main
> (`sbir_etl/extractors/solicitation.py` does not exist); the import is now
> optional and topics degrade to empty. Rebuilding SolicitationExtractor is a
> separate work item.

Sequenced tasks. Each should land as an independent PR with tests.

## Stage 0 — Baseline

- [x] **T0.1** Capture a golden-file output: run the current script against a
      fixed `--days` window with network calls stubbed, store markdown in
      `tests/fixtures/weekly_awards_report/golden.md`. Timestamps
      normalized to a sentinel. — implemented: golden.md generated via the
      harness (dates injected at runtime and normalized to sentinels);
      regenerate with `UPDATE_GOLDEN=1`.
- [x] **T0.2** Add `tests/unit/reporting/weekly/test_golden.py` that runs the
      current script as a subprocess (or imports `main`) against the fixture
      and diffs against `golden.md`. This test MUST pass before any
      extraction begins and stay green through every stage below. — implemented:
      imports the CLI's `main()`; passed against the pre-refactor script and
      stayed green through the extraction.

## Stage 1 — Pure-function extraction (no behavior change)

- [x] **T1.1** Move `format_amount`, `_format_date`, `_escape_md_cell`,
      `build_sbir_award_url`, `build_solicitation_url`,
      `build_usaspending_url`, `generate_markdown` to
      `sbir_etl/reporting/weekly/rendering.py`. Unit tests per function. —
      implemented: rendering.py + tests/unit/reporting/weekly/test_rendering.py.
- [x] **T1.2** Move `_company_key`, `clean_and_dedup_awards`,
      `fetch_weekly_awards`, `_resolve_csv_path`, `_check_data_freshness`
      to `sbir_etl/reporting/weekly/fetching.py`. Stub `httpx.get` in tests. —
      implemented: fetching.py (also holds the shared-extractor/history
      wrappers) + test_fetching.py; CSV resolution stubbed at the module seam.
- [x] **T1.3** Move `verify_reference_links`,
      `_print_link_verification_report` to
      `sbir_etl/reporting/weekly/link_verification.py`. — implemented (debug-mode
      only path; exercised via the orchestrator's debug summary).

## Stage 2 — Enrichment extraction

- [x] **T2.1** Extract `lookup_pi_external_data`,
      `lookup_usaspending_recipients`, `lookup_sam_entities`,
      `lookup_opencorporates`, `poll_press_wire` into
      `sbir_etl/reporting/weekly/enrichment.py`. These are thin wrappers
      over `sbir_etl/enrichers/*` that add budgeting / rate-limiting —
      move the budgeting helpers (`_stage_deadline`, `_past_deadline`) too. —
      implemented: enrichment.py (also owns the shared rate limiters and
      STAGE_TIMEOUT).
- [x] **T2.2** Extract `fetch_solicitation_topics`,
      `enrich_with_inflation`, `resolve_congressional_districts`,
      `map_naics_to_bea_sectors` into the same module. — implemented (plus
      `fetch_usaspending_contract_descriptions`, which the original task list
      missed; report dataclasses live in models.py).
- [ ] **T2.3** Accept an injected `USAspendingAPIClient`,
      `OpenAIClient`, `SolicitationExtractor` on each helper so tests can
      use mocks without monkeypatching module-level clients. — not done;
      stages are stubbable at the module seam (how the golden test works),
      but per-helper client injection remains open.

## Stage 3 — LLM generation extraction

- [x] **T3.1** Extract `_award_digest`, `_company_history_digest`,
      `_pi_history_digest`, `_pi_external_digest` into
      `sbir_etl/reporting/weekly/llm_digests.py` as pure functions. — implemented.
- [ ] **T3.2** Extract `research_companies`, `generate_weekly_synopsis`,
      `generate_award_descriptions`, `generate_company_diligence`,
      `generate_pi_diligence` into
      `sbir_etl/reporting/weekly/llm.py`. Each takes an `OpenAIClient`
      (already injectable — finish the job) and the relevant inputs, returns
      typed dataclasses. — extraction DONE (llm.py, moved verbatim); the
      OpenAIClient-injection and typed-dataclass-return halves are NOT done
      (functions still take api_key strings and return dicts/strs).

## Stage 4 — Orchestrator + thin CLI

- [x] **T4.1** Create `sbir_etl/reporting/weekly/orchestrator.py` with a
      `WeeklyAwardsReportBuilder` dataclass that composes fetching,
      enrichment, llm, and rendering stages. Takes dependencies via
      constructor. — implemented; note deviation: stage functions are resolved
      through their modules (patchable seams) rather than constructor-injected.
- [x] **T4.2** Reduce `scripts/data/weekly_awards_report.py` to argparse +
      `WeeklyAwardsReportBuilder(...).run()`. Target ≤200 lines. — implemented:
      116 lines; CLI flags unchanged (weekly.yml only consumes `--output`).
- [x] **T4.3** Verify the golden-file test still passes. — verified: byte-identical
      normalized output before and after extraction.

## Stage 5 — Follow-up

- [x] **T5.1** Run `ruff check` and `mypy sbir_etl/reporting/weekly` — zero
      errors, zero new `type: ignore`. — implemented; one exception: the
      optional SolicitationExtractor import carries a `type: ignore` because
      the module it imports does not exist on main (see status banner).
- [ ] **T5.2** Raise coverage on new modules to the R4 targets. — partial:
      golden E2E + 27 unit tests cover rendering/fetching/orchestration paths;
      enrichment/llm modules rely on the golden test and their underlying
      enrichers' suites. Coverage against the numeric target not yet measured.
- [ ] **T5.3** Remove the `_lib_*` alias imports; call the canonical
      enrichers directly. — deliberately kept: several aliases exist because the
      report wrapper shares the canonical function's name
      (`fetch_usaspending_contract_descriptions`, `get_company_history`);
      renaming the wrappers would churn the public seam for no behavior gain.
      Revisit only if the wrappers themselves get absorbed into the enrichers.

## Estimate

- Stage 0: 0.5 day
- Stage 1: 1 day
- Stage 2: 1.5 days
- Stage 3: 1 day
- Stage 4: 0.5 day
- Stage 5: 0.5 day

Total: ~5 days for one engineer.
