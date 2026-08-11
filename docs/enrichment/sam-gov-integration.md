# SAM.gov Entity Integration

**Type**: Operator and Architecture Guide

**Maintainer**: Conrad Hollomon

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

1. SAM.gov Public Data Services catalog and latest UTF-8 monthly Public V2 bulk file (keyless).
2. Entity API asynchronous CSV extract.
3. A bounded paginated API fallback.

A full result is written as:

```text
<data_root>/raw/sam_gov/
├── sam_entity_records.parquet
└── sam_entity_records.meta.json
```

The Public V2 `.dat` has no header row. The downloader applies GSA's pinned 142-field positional
layout, requires matching BOF/EOF control records and record count, and validates the census identity
fields before writing the canonical parquet. Strategies 2 and 3 are always written as
`sam_entity_records_partial.parquet`, so a capped fallback cannot overwrite the full dataset.

## Prerequisites

No API key is needed for the supported Public Data Services bulk route. Set `SAM_GOV_API_KEY` only if
you intend to use strategy 2 or 3. SAM.gov keys expire periodically, commonly around 60 days, so
authentication failures on those fallbacks should prompt key rotation rather than blind retries.

The live key belongs in `.env.server`, never committed YAML. Before running the live download, read
the [self-hosted server runbook](../deployment/self-hosted-server.md#source-data-downloads).

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
uv run python scripts/data/download_sam_gov.py --strategy 1 \
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

The post-April 2022 public extract preserves the DUNS position but does not populate DUNS values.
Matching therefore prefers UEI and CAGE, with DUNS supplied only by separately audited official
identity-link records. Name/address keys can quarantine an uncertain candidate but do not establish
an identifier match.

## Failure modes

| Symptom | Meaning | Action |
| --- | --- | --- |
| Exit code 2 | API key missing, invalid, or expired | Rotate the key and update the host secret |
| Exit code 3 | Daily request quota exhausted | Retry after the reported reset time |
| Public V2 control/schema error | Source format, record count, or identity fields failed validation | Preserve the prior canonical parquet; inspect the catalog file and parser contract |
| Partial parquet produced | Only an authenticated capped fallback succeeded | Preserve the canonical parquet; inspect logs and retry strategy 1 later |
| Empty entity asset | File missing or schema mismatch | Check the configured local path and normalized columns |

Never replace `sam_entity_records.parquet` manually with a partial download. Review the job metadata
for row count, output path, and the `partial` flag before enabling downstream refreshes.
