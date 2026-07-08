# Form D Match False-Positive Diagnostic — STOPPED (data unavailable)

**Date:** 2026-07-08
**Branch:** `claude/formd-fp-diagnostic-fkkjpc`
**Status:** Not run. Guardrail triggered: match table cannot be located and regeneration exceeds ~30 minutes of compute.

## Summary

The requested diagnostic (sample 200 "generic-name" + 100 control matched companies
from the Form D fuzzy-match output, measure geographic no-overlap rate, adjudicate
false positives, produce a corrected match count) could not be run. **This checkout
has none of the required inputs**, and regenerating them means re-running the full
bulk Form D pipeline against 17+ years of SEC EDGAR data — well beyond the task's
30-minute compute ceiling and its "do not re-run the full scan" guardrail. Per the
task's own instructions, stopping and reporting what's missing is the correct action,
not improvising a smaller/synthetic version of the analysis.

## What was checked

| Item | Expected location | Found? |
|---|---|---|
| Form D match output (`form_d_details.jsonl`, `form_d_index.jsonl`) | `data/` (per `sbir_etl/capital_events/_common.py: data_dir()`) | **No.** `data/` is gitignored (`.gitignore:144`); this checkout's `data/` contains only `data/reference/*` (tracked exceptions: `cmf_registry.csv`, `naics_to_bea.csv`, `tax/state_effective_rates.csv`). No `.jsonl`/`.parquet`/`.duckdb` files anywhere on disk (`find` across the container found nothing). |
| SBIR award corpus (34,460 companies, states, PI names, award years) | `data/raw/sbir/award_data.csv` (default arg in `scripts/data/build_capital_events.py`) | **No.** Not present. |
| SEC Form D bulk structured data sets (ISSUERS/OFFERING/RELATEDPERSONS/STATEORCOUNTRY TSVs from sec.gov/data-research) | n/a — never ingested by this repo | **Not applicable.** The pipeline doesn't use these files at all (see below). |
| DuckDB store (`data/processed/sbir.duckdb`, per `config/base.yaml:482`) | `data/processed/` | **No.** Directory doesn't exist in this checkout. |
| Entity-resolution helpers `generic_token_guard`, `distinctive_tokens`, `name_similarity` ("NIH-linkage kernel") | repo-wide | **Do not exist.** See below. |

## The headline "3,992 (11.3%)" figure has no live source

That number traces to `docs/research/sec-edgar-sbir-learnings.md` (line 228), a
write-up from **PR #227 (April 2026)** using the EFTS full-text-search approach, not
the bulk-index approach the task describes. The same doc (line 91) notes the bulk
index approach the task references actually surfaces **10,405 candidate matches**,
not 3,992 — a materially different denominator for any FP-rate math. Neither number
is backed by a file that exists in this repository: the match artifacts were
produced in a past session, never committed (`data/` is gitignored by design), and
are gone. There is no ground truth here to sample from.

## The task's data-source assumption doesn't match the pipeline's actual design

The task instructs pulling SEC's quarterly **Form D structured data sets**
(ISSUERS/OFFERING/RELATEDPERSONS TSVs from
`https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets`) if not
already local, and specifically calls out `STATEORCOUNTRY` as the ISSUERS geography
field. This repo's actual Form D pipeline does not use those data sets at all — it
downloads EDGAR's `form.idx` full-text-search indexes
(`scripts/archive/data/fetch_form_d_index.py`, `INDEX_BASE =
".../Archives/edgar/full-index"`) for company/CIK/accession/date, then fetches and
parses each filing's `primary_doc.xml` directly
(`sbir_etl/enrichers/sec_edgar/form_d_scoring.py: parse_form_d_xml`) for issuer
address, offering amounts, and `relatedPersonsList`. There is no
`STATEORCOUNTRY`/`ISSUERS`/`RELATEDPERSONS`/`OFFERING` table anywhere in the repo
(confirmed via repo-wide grep — zero hits). Geography per issuer, if this were
re-run, would come from the XML's parsed issuer address state, not a TSV field —
the field-rule the task specifies doesn't map onto this codebase's data model as-is.

## The named entity-resolution helpers don't exist

The task says to reuse "the repo's NIH-linkage kernel" helpers —
`generic_token_guard(firm_name, corroborated)`, `distinctive_tokens`,
`normalize_name`, `name_similarity` — instead of reimplementing tokenization. A
repo-wide, case-insensitive search found **no "NIH-linkage kernel" module and none
of `generic_token_guard`, `distinctive_tokens`, or `name_similarity` anywhere in the
codebase.** The closest real analogues:

- `normalize_name()` — `sbir_etl/utils/text_normalization.py:19` (generic name
  normalizer: lowercase, strip accents/punctuation, optional suffix stripping —
  same *name*, different signature/purpose than what the task describes).
- `_distinctive_words()` — `sbir_etl/enrichers/sec_edgar/enricher.py:605` (module-
  private; generic-word-overlap guard used in CIK resolution).
- `jaro_winkler_similarity()` / `phonetic_match()` —
  `sbir_etl/enrichers/matching.py:161,187`.

None of these implement the "corroborated" generic-token-guard concept the task
describes. Building that logic fresh was out of scope for a read-only measurement
task, and doing so wasn't necessary since there is no match data to run it against
in any case.

## Why regeneration exceeds the guardrail

Reconstructing the inputs from scratch would require, in order:

1. Ingesting the full SBIR award corpus (not present) — separate ETL step.
2. Running `fetch_form_d_index.py` against **72 quarters** of EDGAR `form.idx`
   files (2009–2026) and fuzzy-matching 34,460 companies against ~761K Form D
   index entries.
3. Running `fetch_form_d_details.py`, which fetches `primary_doc.xml`
   **individually per matched accession** (thousands of filings, based on the
   10,405-candidate figure above) under SEC's 10 req/sec fair-access rate limit.

Step 3 alone, at the documented throughput, is on the order of hours, not the
~30-minute ceiling this task sets before requiring a stop. This is exactly the
condition the task's own guardrails call out: *"If the match table cannot be
located, or lacks join keys and regeneration would exceed ~30 minutes of compute,
STOP and report what is missing rather than re-running the full scan."*

## What would unblock this

- The actual `form_d_details.jsonl` / `form_d_index.jsonl` output from a completed
  pipeline run (e.g., pulled from wherever PR #227's artifacts were archived, if
  anywhere), **or**
- Explicit sign-off to spend the multi-hour compute/network budget to regenerate it
  via `scripts/archive/data/fetch_form_d_index.py` +
  `scripts/archive/data/fetch_form_d_details.py`, **or**
- A scoped-down version of this diagnostic run against a small, explicitly-approved
  sample (e.g., re-fetch just the top-30-token-bearing companies' matches) instead
  of the full 3,992/10,405-company universe — this would still take real EDGAR
  network calls but could plausibly fit a smaller time budget. This would need the
  SBIR award corpus made available first regardless.

No pipeline code or stored outputs were modified. No `formd_fp_sample_pairs.csv`
was produced — there was no data to sample.

## Limitations of this stop-report itself

This is a scoping/data-availability finding, not a false-positive rate estimate.
It does not tell you whether the FP concern (homograph collisions on generic
company names) is real or how big it is — that question is exactly as open as
before this task ran.
