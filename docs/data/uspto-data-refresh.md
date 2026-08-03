---
Type: Operator Guide
Owner: data-team
Last-Reviewed: 2026-08-03
Status: active
---

# USPTO Data Refresh

The USPTO refresh runs on the Mac mini and writes to local storage. The Dagster
`uspto_download_job` replaces the retired GitHub Actions/S3 handoff and downloads the three patent
datasets consumed by the pipeline.

Before operating the live job, read the
[Mac mini runbook](../deployment/mac-mini-server.md#source-data-downloads).

## Datasets

| Dataset | Current route | Output |
| --- | --- | --- |
| PatentsView granted patents | USPTO Open Data Portal files API | `<data_root>/raw/uspto/patentsview_patent.zip` |
| USPTO AI Patent Dataset | Direct streamed download | `<data_root>/raw/uspto/ai_patent_dataset.zip` |
| Patent assignments | Browser automation through the USPTO portal | `<data_root>/raw/uspto/assignments/` |

The assignment archives are extracted after download because downstream assets discover CSV, DTA,
and parquet files rather than ZIP archives.

## Prerequisites

- `USPTO_ODP_API_KEY` in the process environment or repo-root `.env` for PatentsView.
- Browser dependencies used by `scripts/data/download_uspto_browser.py` for assignments.
- Enough free space under `SBIR_ETL__PATHS__DATA_ROOT` for archives and extracted files.
- The full workspace installed with `make install`.

Anonymous PatentsView downloads stopped working on 2026-06-18. The files API returns either a file
or a short-lived presigned URL, and each product file has a low annual mint allowance. Do not use
the endpoint for speculative probes.

## Dagster job and schedule

- **Job:** `uspto_download_job`
- **Schedule:** `monthly_uspto_download`
- **Default cron:** `0 9 1 * *`
- **Default status:** STOPPED
- **Enable variable:**
  `SBIR_ETL__DAGSTER__SCHEDULES__MONTHLY_USPTO_DOWNLOAD_ENABLED=true`

Enable the schedule only after a manual server run succeeds.

## Manual commands

From the deployment checkout:

```bash
uv run dagster job execute -m sbir_analytics.definitions -j uspto_download_job
```

For a single PatentsView table on a development machine:

```bash
uv run python scripts/data/download_uspto.py \
  --dataset patentsview --table patent --local data/raw/uspto
```

The standalone downloader also supports `ai_patents`. Assignment automation is implemented in
`scripts/data/download_uspto_browser.py` and is orchestrated by the Dagster job.

## Integrity behavior

Downloads stream to disk while computing SHA-256 metadata. The job rejects HTML portal shells and
implausibly small files before downstream assets see them. Browser assignment failures are treated
as job failures, and extraction uses temporary staging so interrupted work does not leave truncated
CSV files in place.

## Downstream processing

- `uspto_validation_job` discovers and validates assignment inputs.
- USPTO assets under `packages/sbir-analytics/sbir_analytics/assets/uspto/` parse, validate,
  transform, and load patent data.
- `uspto_ai_extraction_job` processes AI patent predictions.

## Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| HTML saved instead of ZIP | Missing/invalid ODP key or portal-only route | Set `USPTO_ODP_API_KEY`; use browser automation for assignments |
| Presigned URL expired | Download did not start promptly | Re-run once; avoid wasting the annual mint allowance |
| Assignment job returns partial files | Browser download failure | Inspect each reported error and rerun after fixing browser/session access |
| Downstream assets find no assignments | ZIPs were not extracted | Run the Dagster job or extract into `raw/uspto/assignments/` |
| Disk-space failure | Archives plus extracted data exceed available space | Check the SSD before retrying; do not redirect live data into the checkout |

For source fields and graph mappings, see [USPTO Patents](../schemas/uspto-patents.md).
