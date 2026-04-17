# Requirements — Weekly Awards Report Refactor

## Purpose

Break up `scripts/data/weekly_awards_report.py` (2,807 lines, 44 top-level
functions) into focused, testable library modules and leave the script as a
thin CLI entry point.

## Context

Today the script mixes five distinct concerns in one file:

1. **Fetch / clean** — pull the SBIR awards CSV, dedup, filter window.
2. **Enrichment** — PI history, USAspending recipients, SAM entities,
   OpenCorporates, press-wire, solicitation topics, patent/publication lookups,
   inflation, congressional districts, NAICS→BEA.
3. **LLM generation** — synopsis, per-award descriptions, company diligence,
   PI diligence (all call OpenAI).
4. **Link verification** — check outbound references resolve.
5. **Rendering** — markdown formatting / templating.

Existing `sbir_etl/enrichers/*` already provides pieces (`award_history`,
`pi_enrichment`, `company_enrichment`, `openai_client`, `fiscal_bea_mapper`,
`inflation_adjuster`, `congressional_district_resolver`). The script reaches
into these with `_lib_*` aliases and wraps them with additional logic that
belongs alongside the libraries.

## Functional Requirements (EARS)

### R1 — Library-first layering

**WHEN** a piece of enrichment, LLM generation, or rendering logic exists in
`scripts/data/weekly_awards_report.py` **THEN** it SHALL be moved to a
`sbir_etl/` module and exposed via a public function with type annotations and
a unit test.

### R2 — Report orchestrator

**WHEN** the refactor is complete **THEN** a `sbir_etl/reporting/weekly/`
package SHALL contain:

- `fetching.py` — `fetch_weekly_awards`, `clean_and_dedup_awards`,
  `_resolve_csv_path`, `_check_data_freshness`.
- `enrichment.py` — `lookup_pi_external_data`, `lookup_usaspending_recipients`,
  `lookup_sam_entities`, `lookup_opencorporates`, `poll_press_wire`,
  `fetch_solicitation_topics`, `verify_reference_links`,
  `enrich_with_inflation`, `resolve_congressional_districts`,
  `map_naics_to_bea_sectors`.
- `llm.py` — `research_companies`, `generate_weekly_synopsis`,
  `generate_award_descriptions`, `generate_company_diligence`,
  `generate_pi_diligence`, plus the `_digest` helpers.
- `rendering.py` — `generate_markdown`, URL builders, amount/date formatters.
- `orchestrator.py` — a single `WeeklyAwardsReportBuilder` that composes the
  above and is the only class the CLI script imports.

### R3 — CLI script

**WHEN** the refactor is complete **THEN** `scripts/data/weekly_awards_report.py`
SHALL be ≤200 lines and contain only argument parsing, logging setup, and a
call into `WeeklyAwardsReportBuilder`.

### R4 — Test coverage

**WHEN** a function moves into `sbir_etl/reporting/weekly/` **THEN** a
corresponding test SHALL exist in `tests/unit/reporting/weekly/` that either:

- exercises the pure function directly, or
- uses a mocked enrichment / OpenAI client to cover the control flow.

Targets: ≥70% line coverage on each new module; ≥80% on `rendering.py` and
`fetching.py`.

### R5 — No behavior drift

**WHEN** the refactor lands **THEN** a golden-file test SHALL assert that a
representative input set produces byte-identical markdown (modulo timestamp)
versus the pre-refactor script output captured as a fixture.

## Non-functional

- Do NOT add new features during the refactor. Pure structural change.
- Preserve the `--days`, `--output`, `--debug` CLI flags and env-var reads
  (`OPENAI_API_KEY`, etc.).
- Preserve all log lines at `info` level to avoid surprising operators.

## Out of scope

- Switching the LLM vendor.
- Changing the schema of the markdown output.
- Consolidating NAICS enrichers (tracked separately in
  `specs/naics-enricher-consolidation`).

## Acceptance

- `scripts/data/weekly_awards_report.py` ≤ 200 lines.
- New modules under `sbir_etl/reporting/weekly/` with ≥70% coverage.
- Golden-file test passes against a recorded pre-refactor output.
- No change in the nightly report output (manual diff on one production run).
