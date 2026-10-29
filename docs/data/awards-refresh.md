# SBIR Awards Data Refresh

Automation keeps the canonical SBIR.gov awards CSV current on the server's data
root, which downstream pipelines consume.

This runs on the self-hosted server, not GitHub Actions. Actions runners cannot reach the
tailnet-only host, so the machine that stores the data is the machine that
fetches it. See the
[self-hosted server runbook](../deployment/self-hosted-server.md#source-data-downloads).

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
points at persistent server storage.

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
  --dest "$SERVER_DATA_DIR/raw/sbir"
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

## `Phase` value vocabulary

Schema drift is not only columns. The export's `Phase` **values** are a closed
vocabulary that upstream can change without touching the 42-column header, so
the column-level checks above will not catch it.

| Literal `Phase` value | Counts as | Notes |
|---|---|---|
| `Phase I` | Phase I | |
| `Phase II` | Phase II | |
| `Phase III` | Phase III | Not observed in any export vintage to date |
| `Phase II – Direct to Phase II` | **Phase II** | En dash (U+2013). Added in the 2026-10-21 vintage |

A direct-to-Phase-II award **is a Phase II award for counting purposes**: it
skips Phase I rather than being a different instrument, and SBA's published
tables count it under Phase II.

The vocabulary lives in `SBIR_PHASE_VOCABULARY` in
`sbir_etl/extractors/sbir_award_export.py`, with two rules over it:

- `sbir_phase_for_counting()` — **use this for counting.** Applies the policy
  above, so the direct-to-Phase-II label returns `"II"`.
- `normalize_sbir_phase()` — exact-label reader; answers only what the source
  field literally says, and returns `None` for the direct-to-Phase-II label.

`unknown_sbir_phase_values()` reports labels outside the vocabulary. Callers
should raise on a non-empty result rather than treat an unclassified label as
"no phase": silently dropping or misfiling it moves award populations.

### The 2026-10-21 change

Between the 2026-09-17 and 2026-10-21 vintages SBIR.gov relabelled 3,303 SBIR
rows to `Phase II – Direct to Phase II`. These are **not new awards**: every one
matches a row present in the previous vintage, matched on the award-grain key
minus `Phase`. The composition matters if you build on it:

- **3,302** were previously labelled `Phase II` — a label refinement. (3,293
  matched on the full key; 9 matched on tracking number plus contract, with
  only a changed `Company` string.)
- **1** was previously labelled `Phase I` — a genuine phase correction, not a
  refinement. Treat it separately from the other 3,302.

The program totals agree to within that one row: 59,013 plain + 3,303
relabelled = 62,316, the prior vintage's SBIR Phase II total, with the
Phase I → Phase II correction accounting for the single-row residual against
the 3,302 that moved out of plain `Phase II`.

Two consequences worth remembering:

- Any consumer filtering on the literal `"Phase II"` loses 3,303 SBIR Phase II
  awards (5.30%) from this vintage onward.
- `Phase` is a component of `SBIR_AWARD_KEY_FIELDS`, so each relabelled row
  mints a new `sbir-source-v2` key and retires its old one. Across vintages
  these awards appear as deletions plus insertions, not as editions of an
  existing key — a cross-vintage key diff will not show them as relabels.

When a refresh introduces an unseen `Phase` value, classify it in
`SBIR_PHASE_VOCABULARY` and record it in the table above before counting
anything from that vintage.

## Verify a refresh

- Confirm `award_data.csv` and a new dated directory under `history/`, with
  matching sizes and a fresh `downloaded_at` in the sidecar.
- Review the Dagster run logs for HTTP or transfer errors.
- Check for unclassified `Phase` values (see above); a new spelling is a
  vocabulary change that must be classified before any count is trusted.

## Related

- [self-hosted server runbook](../deployment/self-hosted-server.md#source-data-downloads) —
  all four source-download schedules and their prerequisites
- [AWS decommission plan](../deployment/aws-decommission-plan.md) — why this
  moved off GitHub Actions and S3
