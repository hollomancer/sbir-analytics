# SBIR Awards Data Refresh

Automation keeps the canonical SBIR.gov awards CSV in sync in S3
(`s3://<S3_BUCKET>/raw/awards/`), which downstream pipelines consume.

## Workflow summary

- **Workflow:** `.github/workflows/data-refresh.yml` (`refresh-sbir` job)
- **Triggers:** scheduled cron + `workflow_dispatch` with `source` (e.g. `sbir`
  or `all`), `environment`, and `force_refresh` inputs
- **Auth:** AWS OIDC via the `AWS_ROLE_ARN` role (no static keys)
- **Behavior:** downloads the upstream CSV and uploads it to
  `s3://<S3_BUCKET>/raw/awards/`. The job does **not** create a branch, commit,
  or pull request, and it does not run schema validation in CI.

### Execution steps

1. **Check existing SBIR files** — `aws s3 ls s3://<S3_BUCKET>/raw/awards/`,
   summarized into the GitHub Actions run summary.
2. **Download SBIR awards** — installs `boto3`/`requests` and runs
   `scripts/data/download_sbir.py`, which downloads the upstream
   `award_data.csv` and uploads it to `s3://<S3_BUCKET>/raw/awards/`. The full
   download log is attached to the run summary.
3. **Check downloaded files** — re-lists the S3 prefix to confirm the upload.

### Outputs

- The refreshed CSV object under `s3://<S3_BUCKET>/raw/awards/`.
- The download log and before/after S3 listings in the workflow run summary.

## Manual operations

### Trigger a manual refresh

1. Navigate to **Actions → Data Refresh → Run workflow**.
2. Set inputs:
   - `source` = `sbir` (or `all`)
   - `environment` = `production` (default) or `test`
   - `force_refresh` = `true` to re-download even if unchanged
3. Monitor the run for the download log and S3 listings.

### Run validation locally (optional)

`scripts/data/awards_refresh_validation.py` is a standalone local tool (it is
**not** invoked by the workflow) for spot-checking a downloaded CSV against the
expected schema:

```bash
python scripts/data/awards_refresh_validation.py \
  --csv-path data/raw/sbir/award_data.csv \
  --schema-path docs/data/sbir_awards_columns.json \
  --metadata-dir reports/awards_data_refresh \
  --summary-path reports/awards_data_refresh/latest.md \
  --previous-metadata reports/awards_data_refresh/latest.json
```

The script streams the CSV, enforces the column schema, and writes JSON +
Markdown summaries. Use `--allow-schema-drift` only when schema changes have been
reviewed.

## Troubleshooting

| Symptom | Likely cause | Next steps |
| --- | --- | --- |
| No new object in S3 | Upstream unchanged, or download failed | Check the download log in the run summary; re-run with `force_refresh=true`. |
| AWS auth failure | `AWS_ROLE_ARN` misconfigured / OIDC trust | Verify the role and its trust policy for GitHub OIDC. |
| Schema drift suspected | Upstream column changes | Run `awards_refresh_validation.py` locally against the new CSV; update `docs/data/sbir_awards_columns.json` if the change is intended. |

## Verify a refresh

- Confirm a new/updated object under `s3://<S3_BUCKET>/raw/awards/` (timestamp,
  size) in the "Check downloaded files" step.
- Review the download log in the run summary for HTTP/transfer errors.
