---
Type: Overview
Owner: docs@project
Last-Reviewed: 2026-08-03
Status: active
---

# Data Sources Overview

No SBIR/STTR award data is committed to this repository. Full reproduction requires downloading
the public source datasets, supplying API credentials where required, and provisioning local disk
and services such as Neo4j.

The live data plane runs on the Mac mini. Source-download jobs write to the local data root on the
attached SSD; GitHub Actions is CI only. All source schedules default to stopped until a manual run
succeeds on that host.

## Primary sources

| Source | Purpose | Local entry point | Default schedule |
| --- | --- | --- | --- |
| SBIR.gov awards | Core awards, firms, topics, phases, and funding | `scripts/data/download_sbir.py` / `sbir_awards_download_job` | Mondays 09:00 UTC, stopped |
| USAspending | Recipient and federal transaction/contract evidence | `scripts/usaspending/download_database.py` / `usaspending_download_job` | Monthly on day 6 at 02:00 UTC, stopped |
| SAM.gov entities | UEI, CAGE, NAICS, registration, and address enrichment | `scripts/data/download_sam_gov.py` / `sam_gov_download_job` | Monthly on day 15 at 03:00 UTC, stopped |
| USPTO | PatentsView grants, assignments, and AI patent indicators | `scripts/data/download_uspto.py` / `uspto_download_job` | Monthly on day 1 at 09:00 UTC, stopped |

Schedule times are defaults from `sbir_analytics/definitions.py` and can be overridden with the
corresponding `SBIR_ETL__DAGSTER__SCHEDULES__...` variables. Follow the
[Mac mini runbook](../deployment/mac-mini-server.md#source-data-downloads) before enabling or
triggering any live download.

## Storage layout

The root comes from `SBIR_ETL__PATHS__DATA_ROOT`; the live profile maps it to the SSD.

```text
<data_root>/
├── raw/
│   ├── sbir/
│   ├── sam_gov/
│   ├── usaspending/
│   └── uspto/
├── usaspending/
├── transformed/
├── processed/
├── transition/
├── reports/
└── state/
```

Exact subpaths are owned by the downloader or asset that writes them. Do not assume an S3 handoff:
the AWS data plane was retired and the supported pipeline storage is the local filesystem.

## Source notes

### SBIR awards

The downloader keeps a canonical `raw/sbir/award_data.csv`, metadata, and dated history vintages so
upstream snapshots remain reproducible. See [Awards Refresh](awards-refresh.md).

### USAspending

Bulk PostgreSQL dumps support large local joins and transition analysis; the REST API supports
targeted and iterative enrichment. Large downloads are resumable and need substantial free space.
See [USAspending Iterative Refresh](../enrichment/usaspending-iterative-refresh.md).

### SAM.gov

`SAM_GOV_API_KEY` is required for the entity download. The downloader prefers bulk extracts and
protects the canonical parquet from being overwritten by a small paginated fallback. Keys expire
periodically; treat authentication failures as rotation prompts. See
[SAM.gov Integration](../enrichment/sam-gov-integration.md).

### USPTO

`USPTO_ODP_API_KEY` is required for PatentsView bulk files. The Dagster job also downloads the AI
patent dataset and uses browser automation for assignment archives because the portal no longer
serves them to a plain HTTP client. See [USPTO Data Refresh](uspto-data-refresh.md).

## Research and pilot sources

These sources support newer capital-formation, ownership, and procurement questions but are not
all scheduled operational pipelines. Their coverage is bounded and should not be generalized
beyond the documented study or pilot.

| Source | Current use | Maturity |
| --- | --- | --- |
| SEC EDGAR and Form D | Public-company ownership, disclosed fundraising, and transaction signals | Research workflows; public-filer lower bound |
| State UCC filings | Secured-debt and financing-pathway pilots | State-specific exploratory pilots |
| Public M&A and capital-event evidence | Unified firm event timeline | Local Parquet research output; see [Capital events](capital-events.md) |
| FFATA/FSRS subawards | Prime-to-awardee attribution | Specified recovery work; not a general scheduled source |
| Other Transaction and consortium records | Procurement-pathway classification | Bounded methodology work; coverage varies by source |

Relevant methods and data cuts live under [`docs/research/`](../research/) and `studies/`. A row in
this table means the repository has a documented use, not that the source is complete, loaded into
Neo4j, or externally citable.

## Quality controls

Shared thresholds live in `config/base.yaml`, including SBIR completeness/uniqueness gates and
enrichment match-rate expectations. Asset checks and validators should emit observed counts, source
vintages, and failure reasons rather than relying on static numbers in documentation.

Related references:

- [Data quality contract](../steering/data-quality.md)
- [Configuration](../configuration.md)
- [SBIR awards columns](sbir_awards_columns.json)
- [USPTO Patents Schema](../schemas/uspto-patents.md)
