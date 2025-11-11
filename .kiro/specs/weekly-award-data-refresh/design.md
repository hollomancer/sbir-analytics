# Design – Weekly SBIR Award Data Refresh

## Overview

Create a dedicated GitHub Actions workflow that runs on a weekly cron plus manual dispatch, downloads the latest SBIR.gov award CSV, validates and stores it at `data/raw/sbir/awards_data.csv`, and auto-opens a pull request containing the refreshed file and accompanying metadata. The workflow must skip commits when no data changes are detected and provide traceability for each refresh event.

## Workflow Triggers

1. **Cron:** `0 9 * * 1` (Mondays at 09:00 UTC ≈ 4am ET) to align with upstream update cadence while avoiding weekend maintenance windows.
2. **Manual Dispatch:** `workflow_dispatch` with inputs:
   - `force_refresh` (bool, default `false`) – bypass diff guardrails
   - `source_url` (string, default canonical URL) – alternate mirrors for debugging

## Job Definition

Single job `refresh-awards-data` running on `ubuntu-latest` runners with the following configuration:

| Setting | Value | Notes |
| --- | --- | --- |
| `permissions` | `contents: write`, `pull-requests: write` | required for committing and PR automation |
| `env` | `DATA_PATH=data/raw/sbir/awards_data.csv` | canonical repo location |
| `concurrency` | `data-refresh-awards` | prevents overlapping refreshes |

### Step Sequence

1. **Checkout** – `actions/checkout@v4` with `persist-credentials: true`, `fetch-depth: 2`.
2. **Set up Python** – `actions/setup-python@v5` (3.11) to reuse repo tooling for validation scripts.
3. **Download CSV** – shell script that:
   - Creates parent directory (`mkdir -p data/raw/sbir`).
   - Uses `curl --retry 5 --retry-delay 5 --fail --compressed` to fetch `${{ inputs.source_url || default }}` into `awards_data.csv.tmp`.
   - Renames temp file atomically.
4. **Validate & Profile** – run `python scripts/data/awards_refresh_validation.py` (to be implemented) which:
   - Streams file to count rows without loading entire dataset into memory (`sum(1 for _ in csv_reader)`).
   - Reads header to ensure expected 42 columns.
   - Computes SHA-256 checksum and byte size.
   - Writes metadata JSON to `reports/awards_data_refresh/<timestamp>.json`.
5. **Generate PR summary** – small Python helper that converts metadata JSON into Markdown table stored at `reports/awards_data_refresh/latest.md`.
6. **Git diff guard** – shell gate:
   ```bash
   if git diff --quiet && [[ "${{ inputs.force_refresh }}" != "true" ]]; then
       echo "No changes detected."
       exit 0
   fi
   ```
7. **Commit changes** – configure git user (`github-actions`), commit message `chore(data): refresh sbir awards <DATE>`.
8. **Open PR** – use `peter-evans/create-pull-request@v6` with:
   - Branch `data-refresh/<DATE>`
   - Title `chore(data): refresh sbir awards <DATE>`
   - Body template embedding Markdown summary plus metadata JSON excerpt.
   - Label `data-refresh`.
9. **Upload artifacts** – `actions/upload-artifact@v4` for raw CSV (optional) and metadata JSON for traceability.

## Data Validation & Metadata Strategy

- **Schema check:** Validate header columns against a frozen schema file (e.g., `docs/data/sbir_awards_columns.json`). Fail workflow if drift detected.
- **Row-count regression:** Compare new row count to previous metadata and flag >5% decreases as warnings (surface in PR body).
- **Compression:** Keep file uncompressed in repo for compatibility but consider optionally gzipping and storing as artifact to conserve workflow storage.
- **Metadata format:** JSON structure
  ```json
  {
    "refreshed_at_utc": "...",
    "source_url": "...",
    "sha256": "...",
    "bytes": 123456,
    "row_count": 533598,
    "row_delta": 123,
    "column_count": 42
  }
  ```

## Branch, Commit, and PR Conventions

- Branch: `data-refresh/<YYYY-MM-DD>`
- Commit: `chore(data): refresh sbir awards <YYYY-MM-DD>`
- PR body template:
  ```
  ## Summary
  - Source: <URL>
  - Downloaded: <timestamp>
  - Rows: <current> (<delta> vs previous)
  - SHA-256: `<hash>`

  ## Validation
  - [x] Schema matches expected 42 columns
  - [x] File size within +/- 10% of rolling median
  - [x] Metadata stored at reports/...
  ```

Use auto-labels `data`, `automation`, and request review from `@sbir-etl/data-stewards` CODEOWNERS entry (to be added).

## Failure Handling & Observability

- Workflow relies on GitHub's failure notifications; optionally extend with Slack webhook using an encrypted secret.
- Save `curl` response headers and first/last 5 rows as artifacts for debugging failed runs.
- Document runbook in `docs/data/awards-refresh.md` describing manual rerun steps.
- Add `timeout-minutes: 30` guard to prevent hung downloads.

## Future Enhancements

- Introduce virus scan or schema diff before commit if upstream format changes.
- Instead of storing raw CSV in git, move to Git LFS or release assets once existing downstream dependencies are decoupled.
- Trigger downstream Dagster asset materialization or DuckDB refresh once PR merges (separate workflow).

