## 1. Offline Dump Staging
- [ ] 1.1 Document how to mount the "X10 Pro" removable drive and locate `usaspending-db-subset_20251006.zip`.
- [ ] 1.2 Copy the zip into `data/raw/usaspending/` (or configurable path) and record size + `sha256` checksum in the profile report.
- [ ] 1.3 Measure required disk space/time for unzip + temporary restore so engineers can provision scratch space.

## 2. Schema & Table Profiling
- [ ] 2.1 Implement `scripts/profile_usaspending_dump.py` that can read the zipped dump (via `pg_restore --list` or DuckDB `postgres_scanner`) and emit table/column metadata.
- [ ] 2.2 Run the profiler against the subset and publish `reports/usaspending_subset_profile.md` (tables, row counts, primary keys, important columns).
- [ ] 2.3 Add a lightweight DuckDB query example that confirms we can read at least one large table directly from the dump without a full Postgres restore.

## 3. Enrichment Coverage Assessment
- [ ] 3.1 Produce a notebook or script that joins the profiled USAspending data to a sample of SBIR awards (UEI/DUNS/PIID) and calculates match rate vs. the 70% target.
- [ ] 3.2 Enumerate which USAspending fields will feed SBIR enrichment (NAICS, PSC, place of performance, award history) and which will power tech transition scoring (competition type, obligated amounts, action dates).
- [ ] 3.3 Capture any data quality blockers (missing UEIs, inconsistent PIIDs, truncated text) in the report so downstream changes can plan mitigations.

## 4. Tooling Updates
- [ ] 4.1 Extend `src/extractors/usaspending.py` (or a helper) so it can accept the zipped `.dump` path, stream it through `pg_restore`/`postgres_scanner`, and expose helper methods for listing tables + sampling rows.
- [ ] 4.2 Provide a Dagster/CLI hook that surfaces the latest profiling stats (row counts, snapshot date) so enrichment/transition assets can assert the dataset is available before running.

## 5. Documentation & Handoff
- [ ] 5.1 Add `docs/data/usaspending-evaluation.md` covering staging steps, profiling workflow, and how to refresh the report when a new dump arrives.
- [ ] 5.2 Update `README.md` or relevant onboarding docs to mention the removable-drive workflow and the need to run the profiler before enabling USAspending-powered assets.
