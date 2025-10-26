# Evaluate USAspending Postgres Dump for SBIR ETL

## Why
- USAspending is our primary source for federal contract follow-on data that powers SBIR enrichment (award metadata, recipient identifiers, obligations) and technology transition analytics.
- We currently have only a stub DuckDB extractor (`src/extractors/usaspending.py`) and no verified workflow for handling the compressed Postgres subset that ships on the "X10 Pro" removable drive (`usaspending-db-subset_20251006.zip`).
- Without profiling this dump we cannot confirm:
  - Which USAspending tables/columns are present in the subset and whether they cover SBIR-relevant data (financial assistance, contract actions, recipient metadata, account balances, etc.).
  - How to stage the offline media in `data/raw/` and verify integrity before ETL.
  - Whether DuckDB or Postgres-native tooling can ingest/query the dump efficiently enough for enrichment joins and transition detection.
- Transition detection and SBIR enrichment efforts are blocked until we can reference concrete schema/quality findings from this dataset.

## What Changes
- **Data acquisition & staging guidance**
  - Document how to mount "X10 Pro", copy `usaspending-db-subset_20251006.zip` into `data/raw/usaspending/`, and verify SHA256 + file size so the dump can be used in CI-like dev environments without corrupting the removable drive.
  - Track storage footprint (compressed vs. decompressed) and expected import time so contributors can provision adequate disk and temp space.
- **Postgres dump inspection workflow**
  - Provide repeatable commands (e.g., `pg_restore --list`, DuckDB `postgres_scanner`, or `pg_dump` metadata queries) that enumerate tables, row counts, and key columns without requiring a full database restore.
  - Capture profiling results (table list, approx. row counts, column samples) in `reports/usaspending_subset_profile.md` for reuse by enrichment + transition teams.
- **Enrichment join readiness evaluation**
  - Identify which USAspending tables/columns provide SBIR enrichment signals (UEI/DUNS/CAGE, PIID/FAIN, NAICS, PSC, place of performance) and map them to `Award` fields or new enrichment outputs.
  - Measure achievable match rates vs. SBIR sample data (target ≥70% per `config/base.yaml`) and note fallbacks (UEI vs. DUNS vs. PIID).
- **Tech transition data surface planning**
  - Highlight the subset fields needed for transition work (awarding/contracting agency, obligated amount history, competition type, action date series) and confirm they exist in the dump.
  - Produce a recommended pathway (DuckDB external table vs. temporary Postgres restore) for scoring transitions without copying the entire 51GB dataset into memory.
- **Tooling updates**
  - Extend `DuckDBUSAspendingExtractor` (or helper script) so it can read `.zip`/`.dump` assets by streaming them through `postgres_scanner` or piping through `pg_restore` → `COPY`, enabling lightweight ad-hoc queries during evaluation.

## Impact
### Affected Specs
- **data-extraction**: add requirement for staging/profiling offline USAspending Postgres dumps from removable media.
- **data-enrichment**: add requirement for producing USAspending → SBIR/transition mapping + coverage metrics before the enrichment feature ships.

### Affected Code / Docs
- `src/extractors/usaspending.py`: add zipped Postgres dump handling + metadata profiling helper.
- `scripts/profile_usaspending_dump.py` (new): command-line profiler that emits table stats + sample rows.
- `docs/data/usaspending-evaluation.md` (new): instructions for mounting "X10 Pro", copying the zip, and reading profiling outputs.
- `reports/usaspending_subset_profile.md` (new): running log of profiling runs (date, checksum, row counts, coverage observations).

### Dependencies / Tooling
- Requires local `pg_restore`/`pg_dump` CLI (PostgreSQL ≥14) and DuckDB ≥0.10 with `postgres_scanner` enabled.
- Access to removable drive (`/Volumes/X10 Pro` on macOS) during dev/test; automation must gracefully skip when drive not mounted.

### Risks & Mitigations
- **Large temp storage needs** (unzip + restore) → plan staged copy + cleanup commands, emphasize streaming options first.
- **Schema drift across snapshots** → store schema hash & snapshot date in profile report; add regression checklist when new dumps arrive.
- **Removable media availability** → document fallback (request drive, or host sanitized subset) and fail fast with actionable error message when path missing.
