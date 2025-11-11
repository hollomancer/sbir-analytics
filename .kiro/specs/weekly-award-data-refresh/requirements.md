# Requirements – Weekly SBIR Award Data Refresh

## Purpose

Define the behavioral requirements for automatically refreshing the SBIR.gov award CSV inside the repository on a weekly cadence via GitHub Actions while preserving data quality and repository stability.

## Glossary

- **Award_CSV** – Canonical SBIR.gov dataset served at `https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv`
- **Repo_Copy** – File tracked in this repository at `data/raw/sbir/awards_data.csv`
- **Sync_Workflow** – Scheduled GitHub Actions workflow that refreshes the Repo_Copy
- **Data_Diff_Report** – Commit/PR summary describing row-count deltas and metadata for a refreshed dataset

## Functional Requirements (EARS)

### R1 – Source-to-repo synchronization

**WHEN** the Sync_Workflow executes on its weekly schedule **THEN** it SHALL download the Award_CSV with TLS validation, store it as the Repo_Copy path, and ensure the directory structure exists before writing.

Acceptance:
- Download uses authenticated HTTPS with retries and checksum verification
- Repo_Copy is always overwritten atomically (temporary file rename) to avoid partial writes
- Workflow artifacts retain the raw download for debugging for at least 7 days

### R2 – Change detection and commit policy

**WHERE** the newly downloaded Award_CSV is byte-identical to the existing Repo_Copy **THEN** the Sync_Workflow SHALL exit successfully without creating commits, PRs, or tags.

**ELSE** the workflow SHALL commit only the changed Repo_Copy plus generated metadata files on a dedicated branch.

Acceptance:
- Workflow must compare SHA-256 hashes (or git diff) before attempting commits
- Commit messages follow `chore(data): refresh sbir awards YYYY-MM-DD`
- Branch naming convention `data-refresh/<YYYY-MM-DD>` prevents collisions

### R3 – Reporting and traceability

**WHEN** a data change is detected **THEN** the Sync_Workflow SHALL generate a Data_Diff_Report surfaced in the PR body with at minimum: download timestamp, file size, row count, SHA-256 hash, and delta versus the previous commit.

Acceptance:
- Metadata lives in `reports/awards_data_refresh/<YYYY-MM-DD>.json`
- PR body renders the metadata table for reviewer context
- Workflow uploads the metadata JSON as an artifact named `awards-data-refresh`

### R4 – Failure signaling and manual triggers

**WHEN** the Sync_Workflow encounters a download or validation failure **THEN** it SHALL fail loudly, annotate the run logs with actionable context, and block auto-merges.

**WHERE** a maintainer requests an out-of-band refresh **THEN** the workflow SHALL support `workflow_dispatch` inputs to override the schedule and optionally force a refresh even if no diff is detected.

Acceptance:
- Alerts rely on the default workflow failure notifications plus optional Slack/webhook integration stub
- Manual dispatch exposes inputs `force_refresh` (bool) and `source_url` (string, default canonical)
- Forced refresh bypasses hash comparison but still records the delta metadata

