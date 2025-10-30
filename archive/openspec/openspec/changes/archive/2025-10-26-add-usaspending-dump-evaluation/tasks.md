## 1. Offline Dump Staging
- [x] 1.1 Document how to mount the "X10 Pro" removable drive and locate `usaspending-db-subset_20251006.zip` without moving it off-device.
- [x] 1.2 Record size + `sha256` checksum directly from the mounted drive and log the canonical path (e.g., `/Volumes/X10 Pro/usaspending-db-subset_20251006.zip`) in the profile report.
- [x] 1.3 Measure read throughput and any temporary scratch requirements when streaming queries from the removable drive so engineers can anticipate latency and workspace needs.

## 2. Schema & Table Profiling
- [x] 2.1 Implement `scripts/profile_usaspending_dump.py` that can read the zipped dump in-place (via `pg_restore --list` or DuckDB `postgres_scanner`) and emit table/column metadata.
- [x] 2.2 Run the profiler against the subset on the removable drive and publish `reports/usaspending_subset_profile.md` (tables, row counts, primary keys, important columns).
- [x] 2.3 Add a lightweight DuckDB query example that confirms we can read at least one large table directly from the mounted dump without a full Postgres restore.

## 3. Enrichment Coverage Assessment
- [x] 3.1 Produce a notebook or script that joins the profiled USAspending data to a sample of SBIR awards (UEI/DUNS/PIID) and calculates match rate vs. the 70% target.
- [x] 3.2 Enumerate which USAspending fields will feed SBIR enrichment (NAICS, PSC, place of performance, award history) and which will power tech transition scoring (competition type, obligated amounts, action dates).
- [x] 3.3 Capture any data quality blockers (missing UEIs, inconsistent PIIDs, truncated text) in the report so downstream changes can plan mitigations.

## 4. Tooling Updates
- [x] 4.1 Extend `src/extractors/usaspending.py` (or a helper) so it can accept the zipped `.dump` path, stream it through `pg_restore`/`postgres_scanner`, and expose helper methods for listing tables + sampling rows.
- [x] 4.2 Provide a Dagster/CLI hook that surfaces the latest profiling stats (row counts, snapshot date) so enrichment/transition assets can assert the dataset is available before running.

## 5. Documentation & Handoff
- [x] 5.1 Add `docs/data/usaspending-evaluation.md` covering staging steps, profiling workflow, and how to refresh the report when a new dump arrives.
- [x] 5.2 Update `README.md` or relevant onboarding docs to mention the removable-drive workflow and the need to run the profiler before enabling USAspending-powered assets.
