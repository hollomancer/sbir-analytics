# Weekly SBIR Report DRY Re-evaluation

## Scope Reviewed

This review compares the weekly reporting path (`scripts/data/weekly_awards_report.py` and `.github/workflows/weekly-awards-report.yml`) to the rest of SBIR ETL/reporting code paths, especially:

- Enricher infrastructure (`sbir_etl/enrichers/`)
- Dagster ingestion assets (`packages/sbir-analytics/sbir_analytics/assets/sbir_ingestion.py`)
- Weekly refresh and validation scripts (`scripts/data/awards_refresh_validation.py`, `scripts/data/run_sbir_ingestion_checks.py`, `scripts/data/run_neo4j_sbir_load.py`)
- Existing weekly data checks documentation (`docs/data/sbir-weekly-checks.md`)

## Already Resolved (PRs #229, #231, #232)

The following redundancies were identified and resolved in prior work:

| Item | Resolution | PR |
|---|---|---|
| USAspending award type grouping (inline reimplementation) | Imported `build_award_type_groups` with fallback | #229 |
| Patent record parsing duplication | Extracted to public `parse_patent_record()` in patentsview.py | #229 |
| Zero rate limiting on external API calls | All 6 endpoints use shared `RateLimiter` | #229 |
| Uncontrolled OpenAI concurrency | Shared semaphore (`OPENAI_MAX_CONCURRENT=4`) | #229 |
| No sync access to async enricher clients | `SyncUSAspendingClient` / `SyncSAMGovClient` created and wired in | #231 |
| SAM.gov missing `registrationStatus` filter | Added `registration_status` param to `SAMGovAPIClient.search_entities()` | #231 |
| Hardcoded SBIR ALN set in `_is_sbir_award_type()` | Delegates to `classify_sbir_award()` from `sbir_etl.models.sbir_identification` | #232 |
| FPDS fallback code inline in script | Extracted to `sbir_etl/enrichers/fpds_atom.py` (`FPDSAtomClient`) | #232 |
| USAspending contract descriptions using raw httpx | Wired to `SyncUSAspendingClient.search_awards()` | #232 |

## Current Functional Positioning

1. **Weekly report is a parallel reporting lane, not the canonical ETL lane.**
   - `weekly_awards_report.py` performs its own source resolution and filtering for recent awards.
   - The ingestion scripts/assets independently materialize and validate the same source dataset for ETL and downstream loading.

2. **The report script is monolithic but increasingly delegates to the library.**
   - `scripts/data/weekly_awards_report.py` is ~4,600 LOC and defines ~70 functions.
   - It bundles data access, validation/dedup, enrichment lookups, LLM synthesis, URL building, and markdown rendering in one module.
   - Enrichment calls now route through `sbir_etl` sync wrappers when the library is installed.

## Remaining Redundancy Findings

### 1) Duplicate SBIR dataset access and freshness patterns

**Where duplicated now**
- Weekly report resolves S3 vs direct-download and checks freshness (`_resolve_csv_path`, `_check_data_freshness`, `fetch_weekly_awards`).
- Refresh validation script separately handles source URL metadata, row counts, schema checks, and summary generation.

**Share-code opportunity**
- Extract a shared `sbir_etl.reporting.sbir_source` utility:
  - `resolve_awards_source()` (S3-first/fallback logic)
  - `check_awards_freshness()` (key-date + max-award-date policy)
- Both weekly report and refresh-validation can consume this.

### 2) Overlapping validation/normalization with ingestion assets

**Where duplicated now**
- Weekly report uses `clean_and_dedup_awards()` which delegates to library validators (`validate_sbir_award_record`, `normalize_name`) but adds its own dedup logic.
- Dagster ingestion assets define canonical structural quality filters in `_apply_quality_filters`.

**Risk introduced**
- Weekly report "cleaned" dataset can drift from validated ETL dataset.

**Share-code opportunity**
- Introduce shared normalization/validation functions consumed by both asset code and weekly reporting.
- Weekly report could optionally consume `validated_sbir_awards` output artifact when available.

### 3) Repeated Dagster output serialization and markdown summary scaffolding

**Where duplicated now**
- `_serialize_metadata` existed identically in `run_sbir_ingestion_checks.py` and `run_neo4j_sbir_load.py`.
- Several scripts hand-rolled near-identical markdown metric table patterns.

**Resolution (this PR)**
- Shared helpers in `sbir_etl/utils/reporting/script_helpers.py`:
  - `serialize_dagster_metadata()`
  - `render_metric_table(title, rows)`
  - `write_gha_outputs()`
- Duplicate code removed from 3 scripts.

### 4) Weekly report workflow detached from validation workflow outputs

**Where duplicated now**
- Weekly report workflow runs standalone and regenerates data selection/cleaning logic.
- Weekly checks documentation describes ingestion validation and enrichment artifacts in `reports/awards_data_refresh/`, but report generation does not consume those artifacts.

**Share-code opportunity**
- Use a single weekly SBIR "prepared awards" artifact contract (validated CSV + metadata JSON).
- Have the weekly report consume this artifact first; only fall back to direct source resolution if artifact is missing.

### 5) Missing library enrichers for ORCID and Semantic Scholar

**Where duplicated now**
- `lookup_pi_orcid()` (~130 LOC) and `lookup_pi_publications()` (~110 LOC) are inline in the script with no library equivalent.

**Share-code opportunity**
- Extract to `sbir_etl/enrichers/orcid_client.py` and `sbir_etl/enrichers/semantic_scholar.py` if academic/PI enrichment is in scope for other consumers.

### 6) OpenAI client inline in script

**Where duplicated now**
- `_openai_request_with_retry()`, `_openai_chat()`, `_openai_web_search()` (~130 LOC) with retry, semaphore, and token tracking — no library equivalent.

**Share-code opportunity**
- Extract to `sbir_etl/enrichers/openai_client.py` if other pipeline stages need LLM calls.

## Recommended DRY Refactor (Phased)

### Phase 1 (low risk, immediate) — done

1. Standardize shared reporting helpers in `sbir_etl/utils/reporting/script_helpers.py` for:
   - Dagster metadata serialization
   - Markdown metric table helper
   - GitHub output-file writer
2. Replace local duplicates in:
   - `run_sbir_ingestion_checks.py`
   - `run_neo4j_sbir_load.py`
   - `awards_refresh_validation.py`

**Status**: completed in this PR.

### Phase 2 (medium risk)

1. Extract source + freshness logic from `weekly_awards_report.py` into a shared source utility.
2. Repoint `weekly_awards_report.py` and `awards_refresh_validation.py` to that shared logic.
3. Add unit tests for freshness policy boundaries.

### Phase 3 (higher value, if academic enrichment is in scope)

1. Extract ORCID and Semantic Scholar clients to library enricher modules.
2. Extract OpenAI client to library enricher module.
3. Define shared dataclasses for PI research records.

### Phase 4 (structural)

1. Split `weekly_awards_report.py` into submodules:
   - `weekly_report/source.py`
   - `weekly_report/cleaning.py`
   - `weekly_report/enrichment.py`
   - `weekly_report/rendering.py`
2. Replace local cleaning path with shared ETL normalization/validation functions.
3. Define `WeeklyReportInput` dataclass backed by validated awards artifact + optional enrichments.

## Priority Ranking

1. **P0 (done):** Enricher-level DRY — sync wrappers, rate limiting, FPDS client, SBIR identification (PRs #229, #231, #232).
2. **P1 (done):** Shared metadata serialization + markdown helpers (this PR).
3. **P1:** Shared source/freshness utility across weekly report + refresh validation.
4. **P2:** Align weekly cleaning/validation semantics with ingestion assets.
5. **P2:** Extract ORCID, Semantic Scholar, OpenAI clients to library.
6. **P3:** Full modular decomposition of `weekly_awards_report.py`.

## Definition of Done for DRY Improvements

- A change to SBIR source resolution/freshness policy is implemented in exactly one module.
- Weekly report and weekly ingestion checks agree on record eligibility/validation semantics.
- Shared utility functions replace duplicate `_serialize_metadata` and markdown scaffolding.
- Weekly report has an artifact-first mode that reuses validated ETL outputs.
