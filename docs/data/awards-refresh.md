# SBIR Awards Data Refresh

Automation keeps the canonical SBIR.gov awards CSV current on the server's data
root, which downstream pipelines consume.

This runs on the Mac mini, not GitHub Actions. Actions runners cannot reach the
tailnet-only host, so the machine that stores the data is the machine that
fetches it. See the
[Mac mini runbook](../deployment/mac-mini-server.md#source-data-downloads).

## Job summary

- **Job:** `sbir_awards_download_job` (Dagster)
- **Schedule:** `weekly_sbir_awards_download`, Mondays 09:00 UTC
- **Default status:** STOPPED. Enable with
  `SBIR_ETL__DAGSTER__SCHEDULES__WEEKLY_SBIR_AWARDS_DOWNLOAD_ENABLED=true`, and
  only after a manual run succeeds on the host.
- **Script:** `scripts/data/download_sbir.py`
- **Behavior:** downloads the upstream CSV and writes it locally. The job does
  **not** create a branch, commit, or pull request, and it does not run schema
  validation.

## Output layout

```text
<data_root>/raw/sbir/
├── award_data.csv                  # canonical; what extractors read
├── award_data.meta.json            # source_url, sha256, downloaded_at, size
└── history/
    └── 2026-08-02/
        ├── award_data.csv          # dated vintage
        └── award_data.meta.json
```

`<data_root>` comes from `SBIR_ETL__PATHS__DATA_ROOT`, which the server profile
points at the SSD.

The `history/` series matters: SBIR.gov serves only the current snapshot, so a
past vintage exists nowhere else once upstream overwrites it. Do not prune it.

## Change detection

Each run hashes the download and compares it to the sha256 in the newest
vintage's sidecar. When they match, the run reports no change and writes
nothing. A missing or unreadable sidecar falls back to re-downloading rather
than failing.

## Manual operations

### Trigger a manual refresh

```bash
# From the deployment checkout
uv run dagster job execute -m sbir_analytics.definitions -j sbir_awards_download_job

# Or invoke the script directly
uv run python scripts/data/download_sbir.py \
  --dest /Volumes/SSDmini/sbir-analytics/data/raw/sbir
```

### Run validation locally (optional)

`scripts/data/awards_refresh_validation.py` is a standalone local tool (it is
**not** invoked by the job) for spot-checking a downloaded CSV against the
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
Markdown summaries. Use `--allow-schema-drift` only when schema changes have
been reviewed.

## Troubleshooting

| Symptom | Likely cause | Next steps |
| --- | --- | --- |
| Reports "No changes detected" every run | Upstream file genuinely unchanged | Check `downloaded_at` in the sidecar; SBIR.gov does not publish weekly. |
| A vintage has a CSV but no sidecar | Interrupted write | Harmless — the next run re-downloads and writes a fresh vintage. |
| Canonical CSV missing but history present | Manual deletion | Re-run the job, or copy the newest vintage back to `award_data.csv`. |
| HTTP errors from SBIR.gov | Upstream outage | The script retries 3 times with exponential backoff; re-run later. |
| Schema drift suspected | Upstream column changes | Run `awards_refresh_validation.py` against the new CSV; update `docs/data/sbir_awards_columns.json` if intended. |

## Verify a refresh

- Confirm `award_data.csv` and a new dated directory under `history/`, with
  matching sizes and a fresh `downloaded_at` in the sidecar.
- Review the Dagster run logs for HTTP or transfer errors.

## Related

- [Mac mini runbook](../deployment/mac-mini-server.md#source-data-downloads) —
  all four source-download schedules and their prerequisites
- [AWS decommission plan](../deployment/aws-decommission-plan.md) — why this
  moved off GitHub Actions and S3
