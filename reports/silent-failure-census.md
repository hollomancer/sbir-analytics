# Silent-failure census: `sbir_etl/` and `packages/`

Tier: `pipelines` (audit of pipeline code). Taken against `origin/main` at `90b7c2953805`, before the fixes in this branch.

## What was counted

- Every `except` handler in `sbir_etl/` and `packages/`, leaving out `scripts/` and any `tests/` directory.
- **Broad** handlers: `except Exception`, `except BaseException`, bare `except:`, and tuples that include `Exception`.
- **Narrow tuples**: other `except (A, B)` handlers, such as `(TypeError, ValueError)` around a number parse. They are listed separately because most are field-level coercion, not pipeline failure handling.
- **Optional-import guards**: handlers for `ImportError` / `ModuleNotFoundError`, and broad handlers whose `try` body holds only import statements. Counted, not classified.

Classes:

- **(a)** re-raises or raises a wrapped error.
- **(b)** records the failure in the output, metadata, a status field, an error list or a check result, so a reader can see it.
- **(c)** logs and continues, or skips a record, with nothing in the output.
- **(d)** swallows silently: `pass`, `continue`, `return None` or an empty value, or a default assignment, with no log.

## How it was classified, and the limits

An AST script sorted each handler. Rules, in order: any `raise` in the handler body gives (a); an assignment, `append`/`add`/`update` call, dict key, keyword or return value that names an error, status, failure, skip or metadata field gives (b); a logger, `warnings` or `print` call gives (c); otherwise (d).

This is a heuristic. It does not follow what the caller does with a `None` or `False`. So some (c)/(d) blocks are in practice (a) or (b), because the caller raises or records the outcome. Many (d) blocks are also harmless by design: `close()` in cleanup code, best-effort format or row-count hints, and fallbacks whose next step fails loudly. Only the fixed group was reviewed by hand (see its section below). Treat the other rows as a triage list, not as verified defects.

## Totals

| Scope | (a) raise | (b) recorded | (c) log only | (d) silent | Total |
|---|---:|---:|---:|---:|---:|
| broad | 71 | 50 | 124 | 141 | 386 |
| narrow-tuple | 19 | 3 | 14 | 76 | 112 |
| **all classified** | **90** | **53** | **138** | **217** | **498** |

Optional-import guards (not classified): **72**.

## By module group (directory)

Sorted by (c)+(d). Counts include broad and narrow-tuple handlers; the "of which narrow" column shows how many of the (c)+(d) are narrow tuples.

| Group | (a) | (b) | (c) | (d) | (c)+(d) | of which narrow | Import guards |
|---|---:|---:|---:|---:|---:|---:|---:|
| `sbir_etl/extractors` | 18 | 5 | 14 | 29 | 43 | 3 | 9 |
| `sbir_etl/enrichers` | 4 | 3 | 27 | 10 | 37 | 11 | 3 |
| `packages/sbir-analytics/sbir_analytics/assets/cet` | 18 | 3 | 1 | 32 | 33 | 0 | 17 |
| `packages/sbir-analytics/sbir_analytics/assets/uspto` | 0 | 12 | 9 | 13 | 22 | 0 | 13 |
| `sbir_etl/reporting/weekly` | 0 | 5 | 13 | 7 | 20 | 4 | 0 |
| `sbir_etl/transformers` | 4 | 5 | 6 | 12 | 18 | 1 | 2 |
| `packages/sbir-analytics/sbir_analytics/assets` | 6 | 1 | 15 | 1 | 16 | 0 | 4 |
| `sbir_etl/extractors/source_downloads` | 0 | 2 | 8 | 5 | 13 | 3 | 1 |
| `sbir_etl/utils/data` | 3 | 1 | 5 | 7 | 12 | 0 | 1 |
| `sbir_etl/utils` | 0 | 0 | 2 | 9 | 11 | 8 | 1 |
| `packages/sbir-analytics/sbir_analytics/assets/transition` | 0 | 3 | 2 | 8 | 10 | 1 | 1 |
| `sbir_etl/transformers/fiscal` | 1 | 0 | 6 | 4 | 10 | 5 | 0 |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates` | 0 | 0 | 4 | 5 | 9 | 4 | 1 |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_negative_controls` | 2 | 1 | 0 | 7 | 7 | 7 | 0 |
| `packages/sbir-ml/sbir_ml/ml/models` | 5 | 0 | 3 | 4 | 7 | 0 | 2 |
| `sbir_etl/enrichers/sec_edgar` | 1 | 0 | 4 | 3 | 7 | 7 | 0 |
| `sbir_etl/enrichers/naics` | 0 | 0 | 1 | 5 | 6 | 0 | 0 |
| `sbir_etl/enrichers/nih_reporter` | 2 | 0 | 0 | 6 | 6 | 6 | 0 |
| `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital` | 0 | 0 | 0 | 5 | 5 | 5 | 0 |
| `sbir_etl/utils/cache` | 0 | 0 | 2 | 3 | 5 | 0 | 0 |
| `sbir_etl/utils/enrichment` | 2 | 0 | 3 | 2 | 5 | 2 | 0 |
| `sbir_etl/utils/monitoring` | 0 | 0 | 1 | 4 | 5 | 0 | 1 |
| `packages/sbir-ml/sbir_ml/ml/features` | 0 | 0 | 1 | 3 | 4 | 0 | 2 |
| `packages/sbir-ml/sbir_ml/transition/analysis` | 0 | 0 | 1 | 3 | 4 | 2 | 0 |
| `sbir_etl/quality` | 0 | 5 | 2 | 2 | 4 | 1 | 3 |
| `sbir_etl/reporting/procurement_transition` | 0 | 1 | 0 | 4 | 4 | 3 | 0 |
| `sbir_etl/ucc` | 0 | 3 | 0 | 4 | 4 | 2 | 2 |
| `packages/sbir-analytics/sbir_analytics/assets/phase_transition` | 2 | 0 | 1 | 2 | 3 | 2 | 1 |
| `sbir_etl/capital_events/sources` | 0 | 0 | 0 | 3 | 3 | 3 | 0 |
| `sbir_etl/identity` | 0 | 0 | 0 | 3 | 3 | 3 | 1 |
| `sbir_etl/models` | 1 | 0 | 0 | 3 | 3 | 0 | 0 |
| `sbir_etl/reporting` | 0 | 0 | 0 | 3 | 3 | 2 | 0 |
| `packages/sbir-ml/sbir_ml/ml/train` | 0 | 0 | 1 | 1 | 2 | 0 | 2 |
| `sbir_etl/enrichers/usaspending` | 1 | 0 | 2 | 0 | 2 | 0 | 1 |
| `packages/sbir-analytics/sbir_analytics/assets/follow_on_multiplier` | 0 | 0 | 0 | 1 | 1 | 1 | 0 |
| `packages/sbir-analytics/sbir_analytics/assets/sensors` | 1 | 0 | 0 | 1 | 1 | 0 | 0 |
| `packages/sbir-ml/sbir_ml/transition/detection` | 0 | 0 | 1 | 0 | 1 | 0 | 0 |
| `packages/sbir-ml/sbir_ml/transition/features` | 0 | 0 | 1 | 0 | 1 | 1 | 0 |
| `sbir_etl/capital_events` | 0 | 0 | 0 | 1 | 1 | 1 | 0 |
| `sbir_etl/enrichers/naics/fiscal` | 0 | 0 | 1 | 0 | 1 | 0 | 0 |
| `sbir_etl/ot_consortium` | 0 | 0 | 1 | 0 | 1 | 0 | 0 |
| `sbir_etl/supply_chain` | 0 | 0 | 0 | 1 | 1 | 1 | 0 |
| `sbir_etl/validators` | 0 | 2 | 0 | 1 | 1 | 1 | 0 |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_census` | 6 | 1 | 0 | 0 | 0 | 0 | 1 |
| `packages/sbir-analytics/sbir_analytics/assets/sba_annual_report_structural_comparison` | 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| `packages/sbir-ml/sbir_ml/ml` | 2 | 0 | 0 | 0 | 0 | 0 | 2 |
| `packages/sbir-ml/sbir_ml/transition/performance` | 3 | 0 | 0 | 0 | 0 | 0 | 1 |
| `sbir_etl/config` | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| `sbir_etl/config/schemas` | 1 | 0 | 0 | 0 | 0 | 0 | 0 |

## Why the fixed group is not the top row

The task was to fix the group with the most (c)+(d) blocks on paths that feed governed outputs. Raw counts put six groups above the top-level asset files. On review:

- `sbir_etl/extractors` (43): 13 are narrow tuples. Of the 30 broad blocks, 4 close HTTP responses or sessions during cleanup, and about 15 are best-effort Stata or parquet format and row-count hints or format fallbacks in `uspto_extractor.py` and `uspto_ai_extractor.py`. Most `usaspending.py` blocks return `False`, which the asset callers turn into `ExtractionError`. About 4 blocks change an output when they fire. This is the first follow-up (see the ranked list below).
- `sbir_etl/enrichers` (37): mostly HTTP lookups in `company_enrichment.py` that serve the weekly reports, plus fiscal geography helpers. Both are operated exploratory work under `docs/steering/epistemic-tiers.md`.
- `assets/cet` (33): CET classification is operated exploratory, not a governed pipeline output.
- `assets/uspto` (22): all (c)/(d) blocks are in `ai_extraction.py` and `utils.py`. 7 are `con.close()` or `unregister` cleanup, and 4 sit in human-evaluation sampling.
- `sbir_etl/reporting/weekly` (20): recurring reports are operated exploratory.
- `sbir_etl/transformers` (18): 14 are in `bea_io_*` (fiscal estimation) and `company_cet_aggregator.py` (CET), both operated exploratory.

The top-level asset files are the Dagster assets themselves. A hand review found 7 blocks there that change or hide a materialized output when they fire, the most of any group on a governed path. `sbir_etl/extractors/source_downloads/` and `sbir_etl/identity/` were excluded by instruction.

## Ranked follow-ups

1. `sbir_etl/extractors/usaspending.py:229`: a COPY file whose DuckDB table fails to load is logged, and the import still returns `True`, so a partial dump looks complete. Also `uspto_ai_extractor.py:568/575/581` (failed numeric coercion leaves a string in a float field, with no count) and `contract_extractor.py:582` (an unparseable `federal_action_obligation` becomes `None` with no count in `self.stats`; this extractor feeds the Phase III census).
2. `assets/uspto/ai_extraction.py:201/222/229`: failed batches and failed files are skipped with a log line, and the checks JSON still reports `ok: true` with no failure count.
3. `sbir_etl/utils/data` (DuckDB client, 12 blocks): review which `return False` or empty-frame paths reach assets.
4. `sbir_etl/transformers/patent_transformer.py:252/256`: a similarity fallback returns `0.0` on any error. This is an entity matcher, so a silent `0.0` reads as a real non-match.
5. `assets/transition` and `assets/phase_iii_candidates` (10 and 9): check which (d) blocks drop candidate rows without a count.


## Fixed group: `packages/sbir-analytics/sbir_analytics/assets/` (top-level files)

Hand review of every broad (c)/(d) block in this group. "On review" means the caller already raises or records the outcome, so the block is not a silent failure in practice.

| Block | Class | Action |
|---|---|---|
| `_ingestion_utils.py:33` | b (on review) | Left as is. A broken configured path falls through to discovery, and the callers stamp the discovered path on every row as provenance. |
| `_ingestion_utils.py:42` | a (on review) | Left as is. Discovery failure returns (None, None); both callers then raise ExtractionError. |
| `nih_reporter_iterative_enrichment.py:168` | c -> b (fixed) | Metrics write failure now sets `metrics_emit_error` in asset metadata. |
| `sam_gov_ingestion.py:65` | a (on review) | Left as is. A parquet load failure always ends in ExtractionError a few lines later. |
| `sbir_ingestion.py:165` | c -> b (fixed) | `validated_sbir_awards` now sets `processed_parquet_status: write_failed` when the processed copy cannot be written. |
| `sbir_ingestion.py:216` | c (left) | Not a data failure: falls back from Dagster's log call to loguru for one info message about column names. |
| `transition_report.py:90` | c (left) | Deliberate and documented: a broken analysis registry must not take down the whole Dagster definitions load. The missing cohort assets are visible in the UI and the error is logged. |
| `usaspending_database_enrichment.py:40` | d -> a (fixed) | A failed DESCRIBE now raises ExtractionError instead of reporting the column as missing (which switched the SBIR filter to the heuristic path, or returned no grants). |
| `usaspending_database_enrichment.py:83` | c -> a (fixed) | A failed per-agency SBIR.gov API query now aborts the API attempt, so the bulk file is tried and a partial index is never used. |
| `usaspending_database_enrichment.py:93` | b (on review) | Left as is. Falls back to the bulk file; if that also fails, both callers record `sbir_gov_status: unavailable` in metadata. |
| `usaspending_database_enrichment.py:106` | b (on review) | Left as is. Same outcome as line 93: `sbir_gov_status: unavailable` in metadata. |
| `usaspending_database_enrichment.py:577` | c -> a (fixed) | A failed recipient query now raises ExtractionError instead of materializing an empty frame with `row_count: 0`. |
| `usaspending_ingestion.py:70` | a (on review) | Left as is. `dump_success = False` always ends in ExtractionError further down. |
| `usaspending_ingestion.py:177` | c -> b (fixed) | On a parquet failure the metadata now says `source: dump` (it said `parquet`) and carries `parquet_load_error`. |
| `usaspending_iterative_enrichment.py:84` | c -> a (fixed) | An unreadable enriched-awards file now raises instead of being treated as 'no enriched data', which skipped the refresh. |
| `usaspending_iterative_enrichment.py:215` | c -> b (fixed) | Metrics write failure now sets `metrics_emit_error` in asset metadata. |

## Every (c) and (d) block

`file:line` on `origin/main`, by group. `scope` is broad or narrow tuple.

### `sbir_etl/extractors` (43)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/extractors/contract_extractor.py:582` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/extractors/contract_extractor.py:1046` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/extractors/parallel_range_reader.py:238` | d | broad | `Exception` |
| `sbir_etl/extractors/parallel_range_reader.py:319` | d | broad | `Exception` |
| `sbir_etl/extractors/parallel_range_reader.py:526` | d | broad | `Exception` |
| `sbir_etl/extractors/parallel_range_reader.py:538` | d | broad | `Exception` |
| `sbir_etl/extractors/sam_gov.py:102` | d | broad | `Exception` |
| `sbir_etl/extractors/sbir.py:141` | d | broad | `Exception` |
| `sbir_etl/extractors/sbir.py:210` | c | broad | `Exception` |
| `sbir_etl/extractors/solicitation.py:669` | d | narrow-tuple | `(TransportError,TimeoutException,ValueError)` |
| `sbir_etl/extractors/usaspending.py:130` | c | broad | `Exception` |
| `sbir_etl/extractors/usaspending.py:229` | c | broad | `Exception` |
| `sbir_etl/extractors/usaspending.py:254` | c | broad | `Exception` |
| `sbir_etl/extractors/usaspending.py:278` | c | broad | `Exception` |
| `sbir_etl/extractors/usaspending.py:325` | d | broad | `Exception` |
| `sbir_etl/extractors/usaspending.py:465` | d | broad | `Exception` |
| `sbir_etl/extractors/usaspending.py:536` | c | broad | `Exception` |
| `sbir_etl/extractors/usaspending.py:554` | d | broad | `Exception` |
| `sbir_etl/extractors/usaspending.py:599` | c | broad | `Exception` |
| `sbir_etl/extractors/uspto_ai_extractor.py:259` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_ai_extractor.py:356` | c | broad | `Exception` |
| `sbir_etl/extractors/uspto_ai_extractor.py:367` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_ai_extractor.py:391` | c | broad | `Exception` |
| `sbir_etl/extractors/uspto_ai_extractor.py:447` | c | broad | `Exception` |
| `sbir_etl/extractors/uspto_ai_extractor.py:487` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_ai_extractor.py:495` | c | broad | `Exception` |
| `sbir_etl/extractors/uspto_ai_extractor.py:568` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_ai_extractor.py:575` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_ai_extractor.py:581` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_ai_extractor.py:614` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_extractor.py:349` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_extractor.py:361` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_extractor.py:394` | c | broad | `Exception` |
| `sbir_etl/extractors/uspto_extractor.py:417` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_extractor.py:446` | c | broad | `Exception` |
| `sbir_etl/extractors/uspto_extractor.py:494` | c | broad | `Exception` |
| `sbir_etl/extractors/uspto_extractor.py:544` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_extractor.py:546` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_extractor.py:570` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_extractor.py:574` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_extractor.py:576` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_extractor.py:589` | d | broad | `Exception` |
| `sbir_etl/extractors/uspto_extractor.py:591` | d | broad | `Exception` |

### `sbir_etl/enrichers` (37)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/enrichers/award_history.py:53` | d | narrow-tuple | `(ValueError,TypeError)` |
| `sbir_etl/enrichers/award_history.py:141` | d | narrow-tuple | `(ValueError,TypeError)` |
| `sbir_etl/enrichers/chunked_enrichment.py:422` | c | broad | `Exception` |
| `sbir_etl/enrichers/chunked_enrichment.py:461` | c | broad | `Exception` |
| `sbir_etl/enrichers/company_categorization.py:212` | c | broad | `Exception` |
| `sbir_etl/enrichers/company_categorization.py:384` | c | broad | `Exception` |
| `sbir_etl/enrichers/company_categorization.py:459` | c | broad | `Exception` |
| `sbir_etl/enrichers/company_enrichment.py:184` | d | broad | `Exception` |
| `sbir_etl/enrichers/company_enrichment.py:282` | c | broad | `Exception` |
| `sbir_etl/enrichers/company_enrichment.py:346` | d | narrow-tuple | `(ValueError,TypeError)` |
| `sbir_etl/enrichers/company_enrichment.py:427` | c | broad | `Exception` |
| `sbir_etl/enrichers/company_enrichment.py:438` | c | broad | `Exception` |
| `sbir_etl/enrichers/company_enrichment.py:513` | c | broad | `Exception` |
| `sbir_etl/enrichers/company_enrichment.py:657` | c | broad | `Exception` |
| `sbir_etl/enrichers/company_enrichment.py:778` | c | broad | `Exception` |
| `sbir_etl/enrichers/company_fuzzy_matcher.py:453` | d | narrow-tuple | `(IndexError,TypeError,ValueError)` |
| `sbir_etl/enrichers/congressional_district_resolver.py:111` | c | broad | `Exception` |
| `sbir_etl/enrichers/congressional_district_resolver.py:213` | c | broad | `Exception` |
| `sbir_etl/enrichers/congressional_district_resolver.py:284` | c | broad | `Exception` |
| `sbir_etl/enrichers/fiscal_bea_mapper.py:158` | c | broad | `Exception` |
| `sbir_etl/enrichers/fiscal_bea_mapper.py:176` | c | broad | `Exception` |
| `sbir_etl/enrichers/fpds_atom.py:252` | c | narrow-tuple | `(ParseError,UnicodeDecodeError)` |
| `sbir_etl/enrichers/geographic_resolver.py:479` | c | broad | `Exception` |
| `sbir_etl/enrichers/geographic_resolver.py:532` | c | broad | `Exception` |
| `sbir_etl/enrichers/inflation_adjuster.py:339` | d | narrow-tuple | `(ValueError,TypeError)` |
| `sbir_etl/enrichers/inflation_adjuster.py:379` | d | narrow-tuple | `(ValueError,TypeError)` |
| `sbir_etl/enrichers/inflation_adjuster.py:545` | c | broad | `Exception` |
| `sbir_etl/enrichers/inflation_adjuster.py:604` | d | narrow-tuple | `(JSONDecodeError,TypeError)` |
| `sbir_etl/enrichers/matching.py:68` | d | broad | `Exception` |
| `sbir_etl/enrichers/matching.py:128` | d | broad | `Exception` |
| `sbir_etl/enrichers/openai_client.py:131` | c | narrow-tuple | `(TimeoutException,RemoteProtocolError)` |
| `sbir_etl/enrichers/openai_client.py:216` | c | narrow-tuple | `(KeyError,IndexError)` |
| `sbir_etl/enrichers/patentsview.py:356` | c | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/enrichers/pi_enrichment.py:149` | c | broad | `Exception` |
| `sbir_etl/enrichers/pi_enrichment.py:204` | c | broad | `Exception` |
| `sbir_etl/enrichers/pi_enrichment.py:230` | c | broad | `Exception` |
| `sbir_etl/enrichers/pi_enrichment.py:263` | c | broad | `Exception` |

### `packages/sbir-analytics/sbir_analytics/assets/cet` (33)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-analytics/sbir_analytics/assets/cet/analytics.py:66` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/analytics.py:85` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/analytics.py:150` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/analytics.py:218` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/analytics.py:237` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/analytics.py:264` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/analytics.py:294` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/analytics.py:335` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/analytics.py:341` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/analytics.py:360` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/analytics.py:379` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/classifications.py:367` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/classifications.py:481` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/classifications.py:620` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/taxonomy.py:172` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/utils.py:59` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:63` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:76` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:246` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:268` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:421` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:432` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:444` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:463` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:473` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:481` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:509` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:526` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:538` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:660` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:666` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:698` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/cet/validation.py:700` | d | broad | `Exception` |

### `packages/sbir-analytics/sbir_analytics/assets/uspto` (22)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:143` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:161` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:174` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:201` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:222` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:227` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:229` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:236` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:304` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:360` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:409` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:433` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:707` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:718` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:777` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:800` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:848` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:929` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/ai_extraction.py:960` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/utils.py:119` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/utils.py:182` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/uspto/utils.py:348` | d | broad | `Exception` |

### `sbir_etl/reporting/weekly` (20)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/reporting/weekly/enrichment.py:180` | c | broad | `Exception` |
| `sbir_etl/reporting/weekly/enrichment.py:239` | c | broad | `Exception` |
| `sbir_etl/reporting/weekly/enrichment.py:311` | c | broad | `Exception` |
| `sbir_etl/reporting/weekly/enrichment.py:368` | c | broad | `Exception` |
| `sbir_etl/reporting/weekly/enrichment.py:586` | d | broad | `Exception` |
| `sbir_etl/reporting/weekly/enrichment.py:635` | d | broad | `Exception` |
| `sbir_etl/reporting/weekly/enrichment.py:653` | d | broad | `Exception` |
| `sbir_etl/reporting/weekly/llm.py:152` | c | broad | `Exception` |
| `sbir_etl/reporting/weekly/llm.py:178` | d | narrow-tuple | `(ValueError,AttributeError)` |
| `sbir_etl/reporting/weekly/llm.py:310` | c | narrow-tuple | `(JSONDecodeError,ValueError)` |
| `sbir_etl/reporting/weekly/llm.py:596` | c | broad | `Exception` |
| `sbir_etl/reporting/weekly/llm.py:737` | c | broad | `Exception` |
| `sbir_etl/reporting/weekly/orchestrator.py:138` | c | broad | `Exception` |
| `sbir_etl/reporting/weekly/orchestrator.py:196` | c | broad | `Exception` |
| `sbir_etl/reporting/weekly/orchestrator.py:200` | c | broad | `Exception` |
| `sbir_etl/reporting/weekly/orchestrator.py:260` | d | broad | `Exception` |
| `sbir_etl/reporting/weekly/orchestrator.py:315` | c | broad | `Exception` |
| `sbir_etl/reporting/weekly/orchestrator.py:319` | c | broad | `Exception` |
| `sbir_etl/reporting/weekly/rendering.py:38` | d | narrow-tuple | `(ValueError,AttributeError,TypeError)` |
| `sbir_etl/reporting/weekly/rendering.py:147` | d | narrow-tuple | `(ValueError,AttributeError)` |

### `sbir_etl/transformers` (18)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/transformers/bea_io_adapter.py:150` | c | broad | `Exception` |
| `sbir_etl/transformers/bea_io_adapter.py:169` | c | broad | `Exception` |
| `sbir_etl/transformers/bea_io_adapter.py:391` | c | broad | `Exception` |
| `sbir_etl/transformers/bea_io_functions.py:265` | c | broad | `Exception` |
| `sbir_etl/transformers/bea_io_functions.py:326` | c | broad | `Exception` |
| `sbir_etl/transformers/bea_io_functions.py:489` | c | broad | `Exception` |
| `sbir_etl/transformers/company_cet_aggregator.py:102` | d | broad | `Exception` |
| `sbir_etl/transformers/company_cet_aggregator.py:120` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/transformers/company_cet_aggregator.py:126` | d | broad | `Exception` |
| `sbir_etl/transformers/company_cet_aggregator.py:148` | d | broad | `Exception` |
| `sbir_etl/transformers/company_cet_aggregator.py:301` | d | broad | `Exception` |
| `sbir_etl/transformers/company_cet_aggregator.py:347` | d | broad | `Exception` |
| `sbir_etl/transformers/company_cet_aggregator.py:379` | d | broad | `Exception` |
| `sbir_etl/transformers/company_cet_aggregator.py:446` | d | broad | `Exception` |
| `sbir_etl/transformers/patent_transformer.py:45` | d | broad | `Exception` |
| `sbir_etl/transformers/patent_transformer.py:233` | d | broad | `Exception` |
| `sbir_etl/transformers/patent_transformer.py:252` | d | broad | `Exception` |
| `sbir_etl/transformers/patent_transformer.py:256` | d | broad | `Exception` |

### `packages/sbir-analytics/sbir_analytics/assets` (16)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-analytics/sbir_analytics/assets/_ingestion_utils.py:33` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/_ingestion_utils.py:42` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/nih_reporter_iterative_enrichment.py:168` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/sam_gov_ingestion.py:65` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/sbir_ingestion.py:165` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/sbir_ingestion.py:216` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/transition_report.py:90` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/usaspending_database_enrichment.py:40` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/usaspending_database_enrichment.py:83` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/usaspending_database_enrichment.py:93` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/usaspending_database_enrichment.py:106` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/usaspending_database_enrichment.py:577` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/usaspending_ingestion.py:70` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/usaspending_ingestion.py:177` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/usaspending_iterative_enrichment.py:84` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/usaspending_iterative_enrichment.py:215` | c | broad | `Exception` |

### `sbir_etl/extractors/source_downloads` (13)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/extractors/source_downloads/sam_gov.py:220` | d | broad | `Exception` |
| `sbir_etl/extractors/source_downloads/sam_gov.py:228` | d | broad | `Exception` |
| `sbir_etl/extractors/source_downloads/sam_gov.py:313` | c | narrow-tuple | `(KeyError,TypeError,ValueError)` |
| `sbir_etl/extractors/source_downloads/sam_gov.py:417` | d | broad | `Exception` |
| `sbir_etl/extractors/source_downloads/sam_gov.py:457` | d | broad | `Exception` |
| `sbir_etl/extractors/source_downloads/sam_gov.py:974` | c | broad | `Exception` |
| `sbir_etl/extractors/source_downloads/sbir.py:200` | c | narrow-tuple | `(OSError,ValueError)` |
| `sbir_etl/extractors/source_downloads/sbir.py:310` | c | broad | `Exception` |
| `sbir_etl/extractors/source_downloads/usaspending.py:92` | c | narrow-tuple | `(OSError,JSONDecodeError)` |
| `sbir_etl/extractors/source_downloads/usaspending.py:310` | c | broad | `Exception` |
| `sbir_etl/extractors/source_downloads/usaspending_availability.py:189` | d | broad | `Exception` |
| `sbir_etl/extractors/source_downloads/uspto.py:441` | c | broad | `Exception` |
| `sbir_etl/extractors/source_downloads/uspto_browser.py:247` | c | broad | `Exception` |

### `sbir_etl/utils/data` (12)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/utils/data/duckdb_client.py:225` | c | broad | `Exception` |
| `sbir_etl/utils/data/duckdb_client.py:266` | c | broad | `Exception` |
| `sbir_etl/utils/data/duckdb_client.py:305` | c | broad | `Exception` |
| `sbir_etl/utils/data/duckdb_client.py:355` | d | broad | `Exception` |
| `sbir_etl/utils/data/duckdb_client.py:502` | c | broad | `Exception` |
| `sbir_etl/utils/data/file_io.py:41` | d | broad | `Exception` |
| `sbir_etl/utils/data/file_io.py:48` | d | broad | `Exception` |
| `sbir_etl/utils/data/file_io.py:55` | d | broad | `Exception` |
| `sbir_etl/utils/data/file_io.py:65` | d | broad | `Exception` |
| `sbir_etl/utils/data/file_io.py:67` | d | broad | `Exception` |
| `sbir_etl/utils/data/file_io.py:190` | d | broad | `Exception` |
| `sbir_etl/utils/data/file_io.py:239` | c | broad | `Exception` |

### `sbir_etl/utils` (11)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/utils/cloud_storage.py:186` | d | narrow-tuple | `(OSError,JSONDecodeError)` |
| `sbir_etl/utils/cloud_storage.py:232` | c | broad | `Exception` |
| `sbir_etl/utils/coercion.py:39` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/utils/coercion.py:49` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/utils/date_utils.py:116` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/utils/date_utils.py:185` | d | narrow-tuple | `(ValueError,TypeError)` |
| `sbir_etl/utils/logging_config.py:76` | c | broad | `Exception` |
| `sbir_etl/utils/logging_config.py:80` | d | broad | `Exception` |
| `sbir_etl/utils/procurement_text.py:79` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/utils/tech_census.py:591` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/utils/tech_census.py:598` | d | narrow-tuple | `(TypeError,ValueError)` |

### `packages/sbir-analytics/sbir_analytics/assets/transition` (10)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-analytics/sbir_analytics/assets/transition/checks.py:146` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/transition/checks.py:220` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/transition/checks.py:226` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/transition/contracts.py:117` | d | narrow-tuple | `(OSError,JSONDecodeError)` |
| `packages/sbir-analytics/sbir_analytics/assets/transition/detections.py:157` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/transition/evidence.py:182` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/transition/evidence.py:196` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/transition/evidence.py:202` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/transition/scoring.py:151` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/transition/utils.py:59` | d | broad | `Exception` |

### `sbir_etl/transformers/fiscal` (10)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/transformers/fiscal/nipa_rates.py:240` | c | broad | `Exception` |
| `sbir_etl/transformers/fiscal/nipa_rates.py:254` | c | broad | `Exception` |
| `sbir_etl/transformers/fiscal/nipa_rates.py:306` | c | broad | `Exception` |
| `sbir_etl/transformers/fiscal/nipa_rates.py:376` | d | narrow-tuple | `(ValueError,TypeError)` |
| `sbir_etl/transformers/fiscal/refresh_state_rates.py:359` | c | broad | `Exception` |
| `sbir_etl/transformers/fiscal/refresh_state_rates.py:372` | c | broad | `Exception` |
| `sbir_etl/transformers/fiscal/shocks.py:76` | c | narrow-tuple | `(ValueError,TypeError,AttributeError)` |
| `sbir_etl/transformers/fiscal/shocks.py:119` | d | narrow-tuple | `(ValueError,TypeError)` |
| `sbir_etl/transformers/fiscal/shocks.py:143` | d | narrow-tuple | `(ValueError,TypeError)` |
| `sbir_etl/transformers/fiscal/shocks.py:211` | d | narrow-tuple | `(ValueError,TypeError)` |

### `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates` (9)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/assets.py:236` | d | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/assets.py:442` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/assets.py:453` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/assets.py:575` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/assets.py:698` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/assets.py:711` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/assets.py:850` | c | broad | `Exception` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/similarity.py:40` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_candidates/similarity.py:62` | d | narrow-tuple | `(TypeError,ValueError)` |

### `packages/sbir-analytics/sbir_analytics/assets/phase_iii_negative_controls` (7)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_negative_controls/covariates.py:48` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_negative_controls/february_mirror.py:217` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_negative_controls/outcomes.py:57` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_negative_controls/placebo.py:66` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_negative_controls/quarantine.py:45` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_negative_controls/sam_eligibility.py:90` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_iii_negative_controls/source_keys.py:63` | d | narrow-tuple | `(TypeError,ValueError)` |

### `packages/sbir-ml/sbir_ml/ml/models` (7)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-ml/sbir_ml/ml/models/cet_classifier.py:537` | c | broad | `Exception` |
| `packages/sbir-ml/sbir_ml/ml/models/patent_classifier.py:69` | d | broad | `Exception` |
| `packages/sbir-ml/sbir_ml/ml/models/patent_classifier.py:117` | d | broad | `Exception` |
| `packages/sbir-ml/sbir_ml/ml/models/patent_classifier.py:124` | d | broad | `Exception` |
| `packages/sbir-ml/sbir_ml/ml/models/patent_classifier.py:274` | d | broad | `Exception` |
| `packages/sbir-ml/sbir_ml/ml/models/patent_classifier.py:402` | c | broad | `Exception` |
| `packages/sbir-ml/sbir_ml/ml/models/patent_classifier.py:453` | c | broad | `Exception` |

### `sbir_etl/enrichers/sec_edgar` (7)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/enrichers/sec_edgar/client.py:487` | c | narrow-tuple | `(HTTPError,TimeoutException)` |
| `sbir_etl/enrichers/sec_edgar/client.py:511` | c | narrow-tuple | `(HTTPError,TimeoutException)` |
| `sbir_etl/enrichers/sec_edgar/client.py:544` | c | narrow-tuple | `(HTTPError,TimeoutException)` |
| `sbir_etl/enrichers/sec_edgar/client.py:602` | c | narrow-tuple | `(HTTPError,TimeoutException)` |
| `sbir_etl/enrichers/sec_edgar/enricher.py:81` | d | narrow-tuple | `(ValueError,KeyError)` |
| `sbir_etl/enrichers/sec_edgar/enricher.py:134` | d | narrow-tuple | `(ValueError,KeyError,TypeError)` |
| `sbir_etl/enrichers/sec_edgar/enricher.py:453` | d | narrow-tuple | `(ValueError,TypeError)` |

### `sbir_etl/enrichers/naics` (6)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/enrichers/naics/core.py:54` | d | broad | `Exception` |
| `sbir_etl/enrichers/naics/core.py:89` | d | broad | `Exception` |
| `sbir_etl/enrichers/naics/core.py:91` | d | broad | `Exception` |
| `sbir_etl/enrichers/naics/core.py:134` | d | broad | `Exception` |
| `sbir_etl/enrichers/naics/core.py:138` | c | broad | `Exception` |
| `sbir_etl/enrichers/naics/core.py:145` | d | broad | `Exception` |

### `sbir_etl/enrichers/nih_reporter` (6)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/enrichers/nih_reporter/adapter.py:147` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/enrichers/nih_reporter/requests.py:113` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/enrichers/nih_reporter/requests.py:117` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/enrichers/nih_reporter/requests.py:239` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/enrichers/nih_reporter/requests.py:249` | d | narrow-tuple | `(KeyError,TypeError,IndexError)` |
| `sbir_etl/enrichers/nih_reporter/schema.py:149` | d | narrow-tuple | `(TypeError,ValueError)` |

### `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital` (5)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/cohort.py:135` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/form_d_inputs.py:160` | d | narrow-tuple | `(OSError,JSONDecodeError)` |
| `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/outcomes.py:88` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/reconcile.py:315` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/agency_private_capital/reconcile.py:324` | d | narrow-tuple | `(TypeError,ValueError)` |

### `sbir_etl/utils/cache` (5)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/utils/cache/api_cache.py:148` | c | broad | `Exception` |
| `sbir_etl/utils/cache/api_cache.py:153` | d | broad | `Exception` |
| `sbir_etl/utils/cache/api_cache.py:215` | c | broad | `Exception` |
| `sbir_etl/utils/cache/api_cache.py:245` | d | broad | `Exception` |
| `sbir_etl/utils/cache/api_cache.py:302` | d | broad | `Exception` |

### `sbir_etl/utils/enrichment` (5)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/utils/enrichment/checkpoints.py:170` | c | broad | `Exception` |
| `sbir_etl/utils/enrichment/freshness.py:51` | c | broad | `Exception` |
| `sbir_etl/utils/enrichment/freshness.py:180` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/utils/enrichment/freshness.py:224` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/utils/enrichment/metrics.py:235` | c | broad | `Exception` |

### `sbir_etl/utils/monitoring` (5)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/utils/monitoring/core.py:19` | d | broad | `Exception` |
| `sbir_etl/utils/monitoring/core.py:171` | d | broad | `Exception` |
| `sbir_etl/utils/monitoring/core.py:183` | d | broad | `Exception` |
| `sbir_etl/utils/monitoring/core.py:186` | d | broad | `Exception` |
| `sbir_etl/utils/monitoring/reporting.py:534` | c | broad | `Exception` |

### `packages/sbir-ml/sbir_ml/ml/features` (4)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-ml/sbir_ml/ml/features/evidence_extractor.py:89` | d | broad | `Exception` |
| `packages/sbir-ml/sbir_ml/ml/features/evidence_extractor.py:117` | c | broad | `Exception` |
| `packages/sbir-ml/sbir_ml/ml/features/patent_features.py:523` | d | broad | `Exception` |
| `packages/sbir-ml/sbir_ml/ml/features/patent_features.py:602` | d | broad | `Exception` |

### `packages/sbir-ml/sbir_ml/transition/analysis` (4)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-ml/sbir_ml/transition/analysis/analytics.py:47` | d | broad | `Exception` |
| `packages/sbir-ml/sbir_ml/transition/analysis/usaspending_commercialization.py:358` | c | broad | `Exception` |
| `packages/sbir-ml/sbir_ml/transition/analysis/usaspending_commercialization.py:368` | d | narrow-tuple | `(ValueError,TypeError)` |
| `packages/sbir-ml/sbir_ml/transition/analysis/usaspending_commercialization.py:442` | d | narrow-tuple | `(URLError,OSError)` |

### `sbir_etl/quality` (4)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/quality/uspto_validators.py:119` | d | broad | `Exception` |
| `sbir_etl/quality/uspto_validators.py:352` | d | narrow-tuple | `(ValueError,TypeError)` |
| `sbir_etl/quality/uspto_validators.py:545` | c | broad | `Exception` |
| `sbir_etl/quality/uspto_validators.py:743` | c | broad | `Exception` |

### `sbir_etl/reporting/procurement_transition` (4)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/reporting/procurement_transition/core.py:149` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/reporting/procurement_transition/core.py:161` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/reporting/procurement_transition/core.py:877` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/reporting/procurement_transition/core.py:1256` | d | broad | `Exception` |

### `sbir_etl/ucc` (4)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/ucc/cohort_state_filter.py:297` | d | broad | `Exception` |
| `sbir_etl/ucc/cohort_state_filter.py:340` | d | broad | `Exception` |
| `sbir_etl/ucc/export_cohort.py:179` | d | narrow-tuple | `(ValueError,TypeError)` |
| `sbir_etl/ucc/export_cohort.py:186` | d | narrow-tuple | `(ValueError,TypeError)` |

### `packages/sbir-analytics/sbir_analytics/assets/phase_transition` (3)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-analytics/sbir_analytics/assets/phase_transition/phase_ii.py:105` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_transition/sbir_gov_source.py:67` | d | narrow-tuple | `(TypeError,ValueError)` |
| `packages/sbir-analytics/sbir_analytics/assets/phase_transition/utils.py:128` | c | broad | `Exception` |

### `sbir_etl/capital_events/sources` (3)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/capital_events/sources/sbir_awards.py:33` | d | narrow-tuple | `(ValueError,TypeError)` |
| `sbir_etl/capital_events/sources/sbir_awards.py:47` | d | narrow-tuple | `(ValueError,TypeError)` |
| `sbir_etl/capital_events/sources/usaspending.py:70` | d | narrow-tuple | `(ValueError,TypeError)` |

### `sbir_etl/identity` (3)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/identity/canonical_merge.py:83` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/identity/exact_awards.py:82` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/identity/sbir_awards.py:62` | d | narrow-tuple | `(TypeError,ValueError)` |

### `sbir_etl/models` (3)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/models/award.py:210` | d | broad | `Exception` |
| `sbir_etl/models/award.py:214` | d | broad | `Exception` |
| `sbir_etl/models/award.py:602` | d | broad | `Exception` |

### `sbir_etl/reporting` (3)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/reporting/dod_supply_chain_baseline.py:92` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/reporting/phase_transition_analysis.py:222` | d | narrow-tuple | `(TypeError,ValueError)` |
| `sbir_etl/reporting/tech_area_cohort.py:416` | d | broad | `Exception` |

### `packages/sbir-ml/sbir_ml/ml/train` (2)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-ml/sbir_ml/ml/train/patent_training.py:111` | d | broad | `Exception` |
| `packages/sbir-ml/sbir_ml/ml/train/patent_training.py:120` | c | broad | `Exception` |

### `sbir_etl/enrichers/usaspending` (2)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/enrichers/usaspending/client.py:620` | c | broad | `Exception` |
| `sbir_etl/enrichers/usaspending/client.py:636` | c | broad | `Exception` |

### `packages/sbir-analytics/sbir_analytics/assets/follow_on_multiplier` (1)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-analytics/sbir_analytics/assets/follow_on_multiplier/integration.py:23` | d | narrow-tuple | `(TypeError,ValueError)` |

### `packages/sbir-analytics/sbir_analytics/assets/sensors` (1)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-analytics/sbir_analytics/assets/sensors/source_download_chaining.py:122` | d | broad | `Exception` |

### `packages/sbir-ml/sbir_ml/transition/detection` (1)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-ml/sbir_ml/transition/detection/evidence.py:568` | c | broad | `Exception` |

### `packages/sbir-ml/sbir_ml/transition/features` (1)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `packages/sbir-ml/sbir_ml/transition/features/vendor_resolver.py:364` | c | narrow-tuple | `(KeyError,AttributeError)` |

### `sbir_etl/capital_events` (1)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/capital_events/cross_enrichment.py:47` | d | narrow-tuple | `(TypeError,ValueError)` |

### `sbir_etl/enrichers/naics/fiscal` (1)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/enrichers/naics/fiscal/enricher.py:94` | c | broad | `Exception` |

### `sbir_etl/ot_consortium` (1)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/ot_consortium/registry.py:91` | c | broad | `Exception` |

### `sbir_etl/supply_chain` (1)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/supply_chain/defense_funding.py:35` | d | narrow-tuple | `(TypeError,ValueError)` |

### `sbir_etl/validators` (1)

| Location | Class | Scope | Handler |
|---|---|---|---|
| `sbir_etl/validators/sbir_awards.py:317` | d | narrow-tuple | `(TypeError,ValueError)` |
