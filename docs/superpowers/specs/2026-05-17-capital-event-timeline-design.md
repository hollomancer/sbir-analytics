# Capital-Event Timeline — Design Spec

**Date:** 2026-05-17
**Branch:** `claude/capital-events-timeline`
**Research questions:** A4 (private capital signals), B2 (Phase II→III
commercialization), B3 (Phase II → III latency)

## Goal

For each firm in the Form D high-confidence SBIR cohort, produce a unified,
chronologically-sorted stream of capital events drawn from existing data
sources. Two artifacts:

- `capital_events.parquet` — long-format, one row per event
- `capital_events_per_firm.parquet` — wide-format summary, one row per firm

This is the foundational dataset for downstream questions about *how SBIR
awardees' capital structure evolves over time*: time-from-first-SBIR to
first-Form-D, Phase-II-to-exit latency by agency, capital intensity vs.
SBIR-only firms, stage transitions.

## Context

The repo already has substantial per-source data:

- `raw/sbir/award_data.csv` — SBIR awards, multi-year, all agencies
- `form_d_details.jsonl` — Reg D filings with offering type + amount
- `enriched_sbir_ma_events.jsonl` — M&A events with press wire + ownership
  enrichment (richer than the older `sbir_ma_events.jsonl`)
- Phase 3 USAspending cache — post-SBIR federal contracts
- PatentsView pipeline output — granted patents linkable to firms
- `ucc1_pilot_matches.jsonl` — secured-debt UCC filings (sparse in v1;
  produced by the UCC1 pilot)
- `form_d_high_conf_cohort.jsonl` — 3,639-firm cohort export from UCC1's
  `scripts/data/ucc/export_cohort.py`

Every downstream analysis currently joins these per-source files
ad-hoc. The result is repeated joining logic, inconsistent firm-identity
handling across analyses, and a high barrier to answering simple
event-timing questions.

## Scope

### Cohort (v1)

Form D high-confidence cohort only — the 3,639-firm subset produced by
`scripts/data/ucc/export_cohort.py`. Every firm has at least some
private-capital signal by definition. Path to V2 (broader cohort with
any private-capital signal, ~10k firms) is documented as a non-goal
for this spec.

### Event types (v1)

Six event types, projected to a common schema:

| Type | Source | One event per |
|---|---|---|
| `sbir_award` | `raw/sbir/award_data.csv` | Award row (agency × phase × year) |
| `form_d_filing` | `form_d_details.jsonl` | Reg D offering |
| `ma_event` | `enriched_sbir_ma_events.jsonl` (high+medium confidence only) | M&A event |
| `usaspending_contract` | Phase 3 USAspending cache | Contract obligation |
| `patent_grant` | PatentsView pipeline output | Granted patent |
| `ucc_filing` | `ucc1_pilot_matches.jsonl` (optional input) | UCC filing |

UCC filings are sparse in v1 (~4 rows from Active Motif from the UCC1
pilot's partial run). The schema accommodates them; row count grows
naturally when/if DE bulk UCC is acquired later.

### Out of scope (V2 follow-ons)

- Dagster asset promotion
- Cohort C (broader SBIR + private-capital firms)
- Derived events (Phase III contract transitions, stage classifications) —
  computable downstream from the events table
- IPO events — would need EDGAR extraction beyond what exists today
- Press wire as standalone events — already partially captured in M&A
  events via the `enriched_*` enrichment
- Fiscal-year bucketing — downstream concern, not part of the base table
- Neo4j loading

## Schema

### Long-format events table

`$SBIR_DATA_DIR/capital_events.parquet` — one row per event.

| Column | Type | Notes |
|---|---|---|
| `company_name` | string (non-null) | Canonical cohort key; matches `form_d_high_conf_cohort.jsonl::company_name`. |
| `event_date` | string (non-null), ISO `YYYY-MM-DD` | All events normalized to a single date convention. |
| `event_type` | string enum (non-null) | One of `sbir_award`, `form_d_filing`, `ma_event`, `usaspending_contract`, `patent_grant`, `ucc_filing`. |
| `event_subtype` | string nullable | Per-type qualifier (see "Per-source builders" below). |
| `amount_usd` | float64 nullable | Award $, raise $, contract obligation $, or null where N/A. |
| `counterparty` | string nullable | Agency / acquirer / secured party / assignee, depending on type. |
| `source_id` | string (non-null) | Unique-within-source ID (award number, accession number, file number, etc.). Lets consumers trace any event back to its source row. |
| `metadata` | string (non-null), JSON-encoded | Source-specific extras. Keeps the columnar schema flat while preserving raw signal. |

Sort order on disk: `(company_name, event_date, event_type)`. Stable
ordering enables deterministic downstream analysis.

### Wide-format per-firm summary

`$SBIR_DATA_DIR/capital_events_per_firm.parquet` — one row per cohort firm.

| Column | Type | Notes |
|---|---|---|
| `company_name` | string (non-null) | Cohort key |
| `state`, `city`, `agency`, `first_award_year`, `last_award_year` | inherited from cohort | Carried over from the cohort export for convenience |
| `sbir_award_count` | int | Total SBIR award rows |
| `total_sbir_amount` | float | Sum of `amount_usd` for `sbir_award` events |
| `form_d_filing_count` | int | Total Reg D offerings |
| `total_form_d_raised` | float | Sum across all Form D events |
| `has_ma_event` | bool | True if any `ma_event` row |
| `first_ma_event_date` | string nullable | Earliest MA event date |
| `ma_confidence_max_tier` | string nullable | `high` if any high-tier event, else `medium` |
| `usaspending_contract_count` | int | Total contract obligation rows |
| `total_usaspending_obligated` | float | Sum of obligations |
| `first_usaspending_year` | int nullable | Earliest contract year |
| `patent_count` | int | Total granted patents |
| `first_patent_year` | int nullable | Earliest patent grant year |
| `ucc_filing_count` | int | Total UCC filings (likely 0–small for v1) |
| `has_ucc_match` | bool | Convenience flag |
| `first_event_date` | string | Earliest event of any type |
| `last_event_date` | string | Latest event of any type |
| `event_type_count` | int | Number of distinct `event_type` values present |

### Inspection artifact

`$SBIR_DATA_DIR/capital_events_sample.jsonl` — first 100 rows of the events
table in JSONL for quick human inspection.

## Architecture

Standalone Python script (`scripts/data/build_capital_events.py`) reading
per-source files from `$SBIR_DATA_DIR`, projecting each into the common
events schema, concatenating, sorting, summarizing, writing parquet.

No Dagster wiring in v1. Promotion to a Dagster asset is a follow-on once
the schema and downstream consumption patterns stabilize.

### File layout

```
scripts/data/
  build_capital_events.py          # orchestrator + CLI entry
  capital_events/
    __init__.py
    _common.py                     # data path helper (reuse UCC1 pattern)
    schema.py                      # CapitalEvent TypedDict + EventType StrEnum
    summarize.py                   # per-firm wide-format aggregator
    sources/
      __init__.py
      sbir_awards.py               # build_sbir_events(cohort, awards_csv)
      form_d.py                    # build_form_d_events(cohort, form_d_details)
      ma_events.py                 # build_ma_events(cohort, enriched_ma)
      usaspending.py               # build_usaspending_events(cohort, cache_path)
      patents.py                   # build_patent_events(cohort, patents_path)
      ucc.py                       # build_ucc_events(cohort, ucc_matches)

tests/unit/scripts/capital_events/
  __init__.py
  conftest.py                      # shared cohort fixture + per-source mini fixtures
  test_schema.py
  test_sbir_awards.py
  test_form_d.py
  test_ma_events.py
  test_usaspending.py
  test_patents.py
  test_ucc.py
  test_summarize.py
  test_orchestrator.py             # end-to-end with tiny synthetic data
```

### Per-source builder contract

Each builder is a pure function:

```python
def build_<source>_events(
    cohort: list[CohortRow],
    source_path: Path,
) -> Iterator[CapitalEvent]:
    """Yield CapitalEvent rows from this source for cohort firms only."""
```

Pure functions = trivially testable, no I/O coupling beyond the input path.

### Per-source projection rules

**`sbir_awards.py`** — reads `raw/sbir/award_data.csv` (uses
`scripts/data/ucc/export_cohort.py`'s `_normalize_sbir_award` helper or
equivalent). For each row whose normalized `Company` matches a cohort
firm's normalized `company_name`:
- `event_date` = award proposal/award date (use the same date convention
  the SBIR awards table standardizes on; ISO format)
- `event_subtype` = `sbir_phase_i` / `sbir_phase_ii` / `sbir_phase_iii`
  (parsed from the Phase column)
- `amount_usd` = `Award Amount`
- `counterparty` = `Agency`
- `source_id` = the row's `Agency Tracking Number` (or `Contract` if
  ATN missing — both are stable per-award IDs)
- `metadata` = `{"branch": <DoD branch if applicable>, "solicitation_number": ..., "solicitation_year": ...}`

**`form_d.py`** — reads `form_d_details.jsonl`. Selects records using the
same rule the cohort export uses (high tier + name-or-zip match). For
each offering on each matched record:
- `event_date` = `filing_date`
- `event_subtype` = derived from `offerings[].types_of_securities_offered`:
  one of `equity`, `debt`, `option_warrant`, `combination`, `other`. If
  the offering has `is_business_combination=true`, override to
  `combination`.
- `amount_usd` = `total_amount_sold`
- `counterparty` = null (Form D doesn't name buyers)
- `source_id` = `accession_number`
- `metadata` = `{"min_investment": ..., "related_person_count": ...,
  "business_combination": bool}`

**`ma_events.py`** — reads `enriched_sbir_ma_events.jsonl`. Filters to
`confidence in {"high", "medium"}` (per the corrected field name from UCC1
work; the file uses `confidence`, not `tier`). One event per record:
- `event_date` = top-level `event_date`
- `event_subtype` = the confidence tier (`high` / `medium`)
- `amount_usd` = null (deal sizes generally not disclosed in this dataset)
- `counterparty` = `acquirer` if known, else null
- `source_id` = `<company_name>__<event_date>` (no native unique ID;
  composite key is stable enough)
- `metadata` = `{"signals": signals_dict, "press_wire_signals":
  press_wire_signals, "signal_count": signal_count}`

**`usaspending.py`** — reads the Phase 3 USAspending cache. Uses the
existing Phase 3 linkage (reuse whatever join key Phase 3 already uses
between cohort firms and USAspending vendors — likely UEI- or name-based).
For each contract obligation row:
- `event_date` = obligation date (or contract action date — pick one
  consistently, document in `metadata`)
- `event_subtype` = contract type (`definitive`, `idv`, `delivery_order`,
  etc.)
- `amount_usd` = obligation amount
- `counterparty` = funding agency
- `source_id` = `unique_award_key` or equivalent stable ID from
  USAspending
- `metadata` = `{"awarding_agency": ..., "naics": ..., "contract_type": ...}`

**`patents.py`** — reads patent grants. Uses name-based matching against
cohort firms via `sbir_etl.enrichers.matching` (same helper UCC1 uses).
One event per granted patent:
- `event_date` = grant date
- `event_subtype` = null in v1 (CET classification is downstream)
- `amount_usd` = null
- `counterparty` = null (cohort firm = assignee)
- `source_id` = patent number
- `metadata` = `{"title": ..., "cpc_codes": [...], "claim_count": ...}`
  (whatever the existing patent pipeline carries)

**`ucc.py`** — reads `ucc1_pilot_matches.jsonl` if present; emits empty
iterator if file is missing (logged as warning). One event per matched
filing:
- `event_date` = `filing_date`
- `event_subtype` = `filing_type` (`initial` / `amendment` /
  `continuation` / `assignment` / `termination`)
- `amount_usd` = null (UCC doesn't disclose principal)
- `counterparty` = `secured_party_name`
- `source_id` = `filing_number`
- `metadata` = `{"secured_party_address": ..., "match_confidence": ...,
  "match_score": ...}`

### Data flow

```
form_d_high_conf_cohort.jsonl
            │
            ▼
    load cohort (3,639 firms)
            │
            ├──► sbir_awards.py     ──┐
            ├──► form_d.py          ──┤
            ├──► ma_events.py       ──┤
            ├──► usaspending.py     ──┼──► concat ──► sort by (company, date, type)
            ├──► patents.py         ──┤
            └──► ucc.py             ──┘            │
                                                    │
                                ┌───────────────────┤
                                ▼                   ▼
                      write capital_events.parquet  summarize.py per-firm
                      write capital_events_sample.jsonl       │
                                                              ▼
                                                  write capital_events_per_firm.parquet
```

## Error handling

- **Missing source file**: log warning, that source contributes 0 events.
  Don't fail the run. Lets the script work when some upstream data is
  stale (e.g., UCC1 not yet populated for new cohort members).
- **Source-file parse error** (malformed JSONL/CSV row): log warning with
  row index, skip the row, continue. Per-source skip count printed in
  the run summary.
- **Cohort-firm name not present in source**: not an error; firms can
  legitimately have zero events of any given type.
- **Date parse failure**: log warning, drop the event. Per-source skip
  count printed in run summary. Surfacing as a data-quality follow-on
  if frequency is non-trivial.
- **All-source counts printed on stderr at end of run**: lets the
  operator catch silent regressions (e.g., "patents went from 12k to
  0 events").

## Testing

- **Unit test per builder**: tiny synthetic fixtures (3–5 rows each),
  assert the projection logic. Builders are pure functions taking
  in-memory `list[CohortRow]` and a file path; tests use `tmp_path` for
  the file.
- **`test_summarize.py`**: synthetic events list → expected per-firm
  aggregation rows.
- **`test_orchestrator.py`**: end-to-end test using `tmp_path` +
  synthetic per-source files, asserts the output parquet has the
  expected columns and event counts. Validates column types via
  pyarrow schema check.
- **No integration tests against real data files**. Real-data
  validation is a manual smoke-run, recorded as a Results section in
  a research memo (same pattern as UCC1's `sbir-ucc1-pilot.md`).
- **Test coverage target**: all builders + summarize + orchestrator.
  ≥30 unit tests across the package.

## Dependencies

- **`form_d_high_conf_cohort.jsonl`** — produced by UCC1's
  `scripts/data/ucc/export_cohort.py`. Either land first
  (PR #303 merged) or document the cohort generation as a prerequisite
  step.
- **`pyarrow`** — already a base dep (used elsewhere in the repo)
- **`pandas`** — already a base dep
- **`sbir_etl.enrichers.matching`** — for name normalization in
  `patents.py` builder
- **USAspending cache path** — needs confirmation of the actual file
  layout from the Phase 3 work; may be parquet, jsonl, or DuckDB. The
  `usaspending.py` builder adapts to whatever format Phase 3 already
  produces.

## Manual validation post-build

Once the script runs end-to-end on the real cohort:

1. Total event count printed; sanity-check against per-source pre-build
   counts (e.g., `wc -l form_d_details.jsonl` × (rough Form D match
   rate) should be in the ballpark of form_d events).
2. Per-firm summary spot-check on 5 known firms (Inhibrx, Pacific
   Biosciences, Active Motif, AADI, Transphorm) — verify event timeline
   tells a coherent capital story.
3. Output column types + null-rates spot-checked.
4. Results memo at `docs/research/capital-events-v1.md` documenting
   row counts, per-source contribution, known gaps.

## What this enables (out of scope to implement here, in scope to enable)

- "Time from first SBIR award to first Form D filing" by agency / vintage
- "Phase II → M&A exit latency" by agency / cohort year
- "Capital intensity" (Form D total / SBIR total) by agency
- Stage classification on top of the events table (pre-seed / growth /
  exit) — derived analysis, not part of v1
- Comparison cohort: same schema applied to SBIR-only firms (cohort C
  follow-on) for "VC-backed vs SBIR-only" comparisons
