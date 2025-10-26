# Data Extraction - USAspending Dump Evaluation Delta

## ADDED Requirements

### Requirement: Offline USAspending Dump Profiling
The system SHALL support staging and profiling the compressed USAspending Postgres subset that ships on removable media before it is ingested into DuckDB/Postgres.

#### Scenario: Stage removable-drive snapshot
- **WHEN** the "X10 Pro" drive containing `usaspending-db-subset_20251006.zip` is mounted at `/Volumes/X10 Pro`
- **THEN** the operator copies the zip into `data/raw/usaspending/`
- **AND** the system records size, SHA256 checksum, snapshot date, and path in `reports/usaspending_subset_profile.md`
- **AND** the staging step fails with an actionable error if the drive is missing or the checksum check fails.

#### Scenario: Profile dump without full restore
- **WHEN** the staged zip is present in `data/raw/usaspending/`
- **THEN** running `poetry run profile_usaspending_dump --input data/raw/usaspending/usaspending-db-subset_20251006.zip`
- **AND** the command streams the archive through `pg_restore --list` or DuckDB `postgres_scanner`
- **AND** outputs machine-readable table metadata (table name, row count estimate, primary key fields, key columns) plus a Markdown summary saved to `reports/usaspending_subset_profile.md`.

### Requirement: USAspending Snapshot Availability Gate
The system SHALL verify that a profiled USAspending snapshot is available before any ETL asset that depends on USAspending data executes.

#### Scenario: Gate enrichment asset on profiling metadata
- **WHEN** Dagster materializes an asset that needs USAspending data (e.g., `usaspending_awards_raw`)
- **THEN** it checks for a fresh profiling artifact (<30 days old) with the expected filename `usaspending-db-subset_20251006.zip`
- **AND** if the artifact is missing, stale, or references a different checksum, the asset fails fast with guidance to rerun the profiling command after staging the removable-drive snapshot.
