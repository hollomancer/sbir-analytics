# SAM.gov Entity Integration

**Type**: Operator and Architecture Guide

**Owner**: Engineering Team

**Last-Reviewed**: 2026-08-03

**Status**: Active

SAM.gov entity records enrich SBIR companies with UEI, DUNS, CAGE, legal name, address, and NAICS
information. The supported bulk path is local parquet storage; the AWS/S3 handoff has been retired.

## Components

| Component | Responsibility |
| --- | --- |
| `scripts/data/download_sam_gov.py` | Download bulk/entity data and write local parquet plus metadata |
| `sam_gov_download_job` | Run the downloader on the always-on server |
| `sbir_etl/extractors/sam_gov.py` | Read and normalize entity parquet for ETL consumers |
| `sbir_etl/enrichers/sam_gov/client.py` | Targeted SAM.gov API client behavior |
| `packages/sbir-analytics/sbir_analytics/assets/sam_gov_ingestion.py` | Dagster ingestion asset |

## Download strategy

The downloader tries these routes in order:

1. SAM.gov bulk extract API.
2. Entity API asynchronous CSV extract.
3. A bounded paginated API fallback.

A full result is written as:

```text
<data_root>/raw/sam_gov/
├── sam_entity_records.parquet
└── sam_entity_records.meta.json
```

If the result has fewer than the canonical minimum row count, it is written as
`sam_entity_records_partial.parquet` so a small fallback cannot overwrite the full dataset.

## Prerequisites

Set `SAM_GOV_API_KEY` in the process environment. SAM.gov keys expire periodically, commonly around
60 days, so authentication failures should prompt key rotation rather than blind retries.

The live key belongs in `.env.server`, never committed YAML. Before running the live download, read
the [Mac mini runbook](../deployment/mac-mini-server.md#source-data-downloads).

## Dagster job and schedule

- **Job:** `sam_gov_download_job`
- **Schedule:** `monthly_sam_gov_download`
- **Default cron:** `0 3 15 * *`
- **Default status:** STOPPED
- **Enable variable:**
  `SBIR_ETL__DAGSTER__SCHEDULES__MONTHLY_SAM_GOV_DOWNLOAD_ENABLED=true`

Confirm a manual run on the deployment host before enabling the schedule.

## Manual commands

Development checkout, explicit destination:

```bash
SAM_GOV_API_KEY=... uv run python scripts/data/download_sam_gov.py \
  --dest data/raw/sam_gov
```

Live deployment checkout:

```bash
uv run dagster job execute -m sbir_analytics.definitions -j sam_gov_download_job
```

Use `--dry-run` on the standalone script to inspect behavior without writing the canonical output.

## Canonical fields

The downloader normalizes source headers into the columns downstream enrichment reads, including:

- `unique_entity_id`
- `legal_business_name`
- `dba_name`
- `physical_address_city`
- `physical_address_state`
- `cage_code`
- `primary_naics`
- `naics_code_string`
- `duns_number`

Matching should prefer stable identifiers such as UEI and DUNS. Name-based matching uses the
shared company identity primitives under `sbir_etl/identity/`.

## Failure modes

| Symptom | Meaning | Action |
| --- | --- | --- |
| Exit code 2 | API key missing, invalid, or expired | Rotate the key and update the host secret |
| Exit code 3 | Daily request quota exhausted | Retry after the reported reset time |
| Partial parquet produced | Bulk routes failed or returned too few rows | Preserve the canonical parquet; inspect logs and retry later |
| Empty entity asset | File missing or schema mismatch | Check the configured local path and normalized columns |

Never replace `sam_entity_records.parquet` manually with a partial download. Review the job metadata
for row count, output path, and the `partial` flag before enabling downstream refreshes.
