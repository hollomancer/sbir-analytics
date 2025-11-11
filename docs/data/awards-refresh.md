# SBIR Awards Data Refresh

Weekly automation keeps the canonical SBIR.gov CSV (`data/raw/sbir/award_data.csv`) in sync with the upstream feed while generating auditable metadata for reviewers.

## Workflow summary

- **Workflow:** `.github/workflows/weekly-award-data-refresh.yml` (runs Mondays at 09:00 UTC)
- **Triggers:** scheduled cron + `workflow_dispatch` with `force_refresh` (bool) and `source_url` (string) inputs
- **Branch / commit:** `data-refresh/<YYYY-MM-DD>` with commit `chore(data): refresh sbir awards <YYYY-MM-DD>`
- **Owners:** `@sbir-etl/data-stewards` (see `.github/CODEOWNERS`)

### Execution steps

1. Download `https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv` with retries and atomic writes.
2. Optionally override the source URL or force a refresh via manual dispatch inputs.
3. Run `scripts/data/awards_refresh_validation.py` to:
   - Verify the header matches `docs/data/sbir_awards_columns.json`
   - Count rows without loading the entire file into memory
   - Compute SHA-256 checksum and byte size
   - Emit metadata JSON + Markdown summary under `reports/awards_data_refresh/`
4. If the CSV is byte-identical and `force_refresh` is `false`, the workflow exits without a commit/PR.
5. When changes exist (or `force_refresh=true`), stage the refreshed CSV + metadata, create a PR via `peter-evans/create-pull-request`, and upload artifacts.

### Generated artifacts

- `reports/awards_data_refresh/<YYYY-MM-DD>.json` – immutable snapshot metadata
- `reports/awards_data_refresh/latest.json` – most recent metadata
- `reports/awards_data_refresh/latest.md` – Markdown summary used in the PR body
- Workflow artifacts:
  - `sbir-awards-csv` – gzip copy of the downloaded CSV (7-day retention)
  - `sbir-awards-metadata` – JSON + Markdown metadata (30-day retention)

## Manual operations

### Trigger a manual refresh

1. Navigate to **Actions → Weekly SBIR Awards Refresh → Run workflow**.
2. Optionally set:
   - `force_refresh` = `true` to capture metadata even if the CSV is unchanged.
   - `source_url` to point at an alternate mirror or local test server.
3. Monitor the run for validation logs and artifact uploads.

### Run validation locally

```bash
python scripts/data/awards_refresh_validation.py \
  --csv-path data/raw/sbir/award_data.csv \
  --schema-path docs/data/sbir_awards_columns.json \
  --metadata-dir reports/awards_data_refresh \
  --summary-path reports/awards_data_refresh/latest.md \
  --previous-metadata reports/awards_data_refresh/latest.json
```

The script streams the CSV, enforces the column schema, and writes both JSON + Markdown summaries. Use `--allow-schema-drift` only when schema changes have been reviewed.

## Troubleshooting

| Symptom | Likely cause | Next steps |
| --- | --- | --- |
| Workflow skipped commit/PR | No diff detected and `force_refresh=false` | Inspect run logs + gzip artifact to confirm upstream data is unchanged. |
| Workflow fails during validation | Header mismatch or structural drift | Review `reports/awards_data_refresh/latest.md`, update `docs/data/sbir_awards_columns.json`, rerun with `force_refresh`. |
| PR missing metadata | Validation skipped due to missing diff | Re-run workflow with `force_refresh=true` to capture metadata intentionally. |
| Need historical stats | Check `reports/awards_data_refresh/<date>.json` in git history; each file includes timestamp, row counts, SHA-256, and deltas. |

## PR review checklist

- Confirm metadata deltas (row count / SHA-256) look reasonable.
- Spot-check `reports/awards_data_refresh/latest.md` inside the PR for warnings (schema drift, large row drops).
- Approve via CODEOWNERS to keep automation unblocked.
