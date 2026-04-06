# Weekly SBIR Report DRY Re-evaluation

## Scope Reviewed

This review compares the weekly reporting path (`scripts/data/weekly_awards_report.py` and `.github/workflows/weekly-awards-report.yml`) to the rest of SBIR ETL/reporting code paths, especially:

- Dagster ingestion assets (`packages/sbir-analytics/sbir_analytics/assets/sbir_ingestion.py`)
- Weekly refresh and validation scripts (`scripts/data/awards_refresh_validation.py`, `scripts/data/run_sbir_ingestion_checks.py`, `scripts/data/run_neo4j_sbir_load.py`)
- Existing weekly data checks documentation (`docs/data/sbir-weekly-checks.md`)

## Current Functional Positioning

1. **Weekly report is a parallel reporting lane, not the canonical ETL lane.**
   - `weekly_awards_report.py` performs its own source resolution and filtering for recent awards.
   - The ingestion scripts/assets independently materialize and validate the same source dataset for ETL and downstream loading.

2. **The report script is monolithic and responsibility-heavy.**
   - `scripts/data/weekly_awards_report.py` is 4,613 LOC and defines 72 functions.
   - It bundles data access, validation/dedup, enrichment lookups, LLM synthesis, URL building, and markdown rendering in one module.

## Redundancy Findings

### 1) Duplicate SBIR dataset access and freshness patterns

**Where duplicated now**
- Weekly report resolves S3 vs direct-download and checks freshness (`_resolve_csv_path`, `_check_data_freshness`, `fetch_weekly_awards`).
- Refresh validation script separately handles source URL metadata, row counts, schema checks, and summary generation.
- Download script has separate download/retry/hash/change-detection behavior.

**Why this violates DRY**
- Multiple components independently encode “how to get SBIR awards CSV” and “how fresh is it”.
- Changes in source reliability or metadata policy need edits in multiple scripts.

**Share-code opportunity**
- Extract a shared `sbir_etl.reporting.sbir_source` utility:
  - `resolve_awards_source()` (S3-first/fallback logic)
  - `check_awards_freshness()` (key-date + max-award-date policy)
  - `compute_dataset_fingerprint()` (size/hash/date)
- Both weekly report and refresh-validation can consume this.

### 2) Overlapping validation/normalization with ingestion assets

**Where duplicated now**
- Weekly report uses its own `clean_and_dedup_awards` path.
- Dagster ingestion assets already define canonical structural quality filters and coercion/dedup behavior in `_apply_quality_filters`, followed by validation asset logic.

**Risk introduced**
- Weekly report “cleaned” dataset can drift from validated ETL dataset.
- Any updates to validation semantics may land in assets but not report logic (or vice versa).

**Share-code opportunity**
- Introduce a shared “SBIR award normalization contract” helper module (pure functions) consumed by both asset code and weekly reporting.
- Weekly report should either:
  1) invoke reusable normalization/validation functions from ETL layer, or
  2) optionally consume `validated_sbir_awards` output artifact when available.

### 3) Repeated Dagster output serialization and markdown summary scaffolding

**Where duplicated now**
- `_serialize_metadata` exists in both `run_sbir_ingestion_checks.py` and `run_neo4j_sbir_load.py` with identical behavior.
- Several scripts hand-roll near-identical markdown “metric table + sections” patterns.

**Share-code opportunity**
- Add `scripts/data/_reporting_common.py` (or `sbir_etl/reporting/common.py`) with:
  - `serialize_dagster_metadata()`
  - `render_metric_table(title, rows)`
  - `write_gha_outputs(dict[str, Path | str])`

### 4) Weekly report workflow is detached from weekly validation workflow outputs

**Where duplicated now**
- Weekly report workflow runs standalone and regenerates data selection/cleaning logic.
- Weekly checks documentation describes ingestion validation and enrichment artifacts in `reports/awards_data_refresh/`, but report generation does not consume those artifacts.

**Share-code opportunity**
- Use a single weekly SBIR “prepared awards” artifact contract (validated CSV + metadata JSON).
- Have the weekly report consume this artifact first; only fall back to direct source resolution if artifact is missing.

### 5) URL construction helpers are local to weekly report

**Where duplicated now**
- `build_sbir_award_url`, `build_solicitation_url`, `build_usaspending_url` are local helpers.
- Other scripts and docs reference the same external systems but cannot reuse URL-building behavior.

**Share-code opportunity**
- Move URL builders to a shared `sbir_etl/reporting/links.py` utility and reuse across markdown outputs.

## Recommended DRY Refactor (Phased)

### Phase 1 (low risk, immediate)

1. Create `scripts/data/common/reporting_io.py` (or `sbir_etl/reporting/common.py`) for:
   - Dagster metadata serialization
   - Markdown metric table helper
   - GitHub output-file writer
2. Replace local duplicates in:
   - `run_sbir_ingestion_checks.py`
   - `run_neo4j_sbir_load.py`
   - `awards_refresh_validation.py` (markdown helper portions)

**Expected impact**: remove repeated utility code with no behavioral change.

### Phase 2 (medium risk)

1. Extract source + freshness logic from `weekly_awards_report.py` into a shared source utility.
2. Repoint `weekly_awards_report.py` and `awards_refresh_validation.py` to that shared logic.
3. Add unit tests for freshness policy boundaries (e.g., stale by `days+3`, stale by `days+14`).

**Expected impact**: one policy for source/freshness handling across report + refresh paths.

### Phase 3 (higher value)

1. Split `weekly_awards_report.py` into packages:
   - `weekly_report/source.py`
   - `weekly_report/cleaning.py`
   - `weekly_report/enrichment.py`
   - `weekly_report/rendering.py`
2. Replace local cleaning path with shared ETL normalization/validation functions.
3. Define `WeeklyReportInput` dataclass backed by validated awards artifact + optional enrichments.

**Expected impact**: lower maintenance risk, easier testing, and clearer alignment with canonical ETL outputs.

## Priority Ranking

1. **P1:** Shared metadata serialization + markdown helpers (quick win).
2. **P1:** Shared source/freshness utility across weekly report + refresh validation.
3. **P2:** Align weekly cleaning/validation semantics with ingestion assets.
4. **P2:** Make weekly report consume validated weekly artifact contract by default.
5. **P3:** Full modular decomposition of `weekly_awards_report.py`.

## Definition of Done for DRY Improvements

- A change to SBIR source resolution/freshness policy is implemented in exactly one module.
- Weekly report and weekly ingestion checks agree on record eligibility/validation semantics.
- Shared utility functions replace duplicate `_serialize_metadata` and markdown scaffolding.
- Weekly report has an artifact-first mode that reuses validated ETL outputs.
