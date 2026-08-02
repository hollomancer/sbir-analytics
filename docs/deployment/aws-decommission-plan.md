# AWS Decommission Plan

Retire the AWS data plane and make the Mac mini the single host for ingestion,
processing, and serving. GitHub Actions is reduced to pure CI (lint, typecheck,
tests, image builds).

See [the Mac mini runbook](mac-mini-server.md) for the target deployment.

## Why this is mostly subtractive

The server profile is already AWS-free:

- `.env.server.example` declares no AWS or S3 variables.
- `docker-compose.server.yml` never references them.
- `config/base.yaml` ships `use_s3_first: false` (lines 270, 288) and leaves all
  three `transition_*_s3*` keys empty.

Nothing currently served depends on AWS. The one load-bearing piece is
**ingestion**: GitHub Actions fetches external data and uses S3 as the handoff.
Actions runners cannot reach the mini (Tailscale-only, no self-hosted runner), so
`data-refresh.yml` has no destination once S3 is gone. That work must move onto
the mini before the workflow can be deleted.

## Sequencing constraints

Two ordering rules prevent a data-loss gap:

1. **Phase 0 (drain) precedes Phase 3.** Once S3 read paths are stripped, nothing
   in the repo can reach the bucket.
2. **Phase 2 (rehost ingestion) precedes Phase 4's deletion of
   `data-refresh.yml`.** Deleting the workflow first leaves no refresh path at all.

Phase 1 is independent of both and can land immediately.

## Phase 0 — Drain S3 to the SSD

**Status: blocked on operator action. The bucket is live.**

Copy current objects from `s3://sbir-etl-prod-data/` to
`/Volumes/SSDmini/sbir-analytics/data/`, preserving the prefix layout:

| S3 prefix | SSD destination |
|---|---|
| `raw/awards/` | `data/raw/sbir/` |
| `raw/sam_gov/` | `data/raw/sam_gov/` |
| `raw/usaspending/` | `data/raw/usaspending/` |
| `raw/uspto/` | `data/raw/uspto/` |
| `raw/transition/` | `data/transition/` |
| `processed/`, `enriched/` | `data/processed/` |

Verify: the SSD tree holds the newest object from each prefix, and byte sizes
match `aws s3 ls --recursive` output. Confirm free space on the SSD before
starting — the USAspending prefix is the large one.

## Phase 1 — Delete the AWS control plane

No runtime impact; nothing consumes any of it. Deleting this code does **not**
delete the live bucket, which persists until Phase 6.

- `infrastructure/cdk/` — entire tree. `foundation.py` (S3 bucket, GitHub OIDC
  role), `batch.py` (Spot and on-demand compute environments, job queue),
  `config.py`, `app.py`, `validation_app.py`, and 238 lines of CDK tests.
- `packages/sbir-analytics/sbir_analytics/lambda/weekly_refresh_handler.py` —
  512 lines, confirmed orphan (no references outside its own directory).
- `.github/workflows/ci.yml` — the `infrastructure-validate` job and the
  `infrastructure` path filter that gates it, plus the matching `infrastructure`
  output in `.github/actions/detect-changes/action.yml`.
- `docs/deployment/aws-deployment.md`, `aws-batch-analysis-jobs.md`,
  `usaspending-ec2-automation.md`, and the index entries pointing at them in
  `docs/deployment/README.md` and `docs/index.md`.

`.github/actions/setup-aws-credentials/` is **not** deleted here — it is still
consumed by `ci.yml:618` and four steps in `data-refresh.yml`. It goes in Phase 4
once those callers are removed.

Verify: `rg -i 'cdk|aws-actions|batch submit-job'` returns nothing; CI green.

## Phase 2 — Rehost ingestion on the mini

The substantive work. Convert the four download scripts to local-first output and
drive them from the Dagster daemon already running in the server profile.

`scripts/data/download_uspto.py:325` already has a `--local DIR` flag documented
as needing "no AWS credentials or boto3". Use it as the template for the rest.

| Script | LOC | Change |
|---|---|---|
| `scripts/data/download_sbir.py` | 142 | S3-only today; add local output |
| `scripts/data/download_sam_gov.py` | 610 | S3-only today; add local output |
| `scripts/data/download_uspto.py` | 485 | `--local` exists; make it the default |
| `scripts/usaspending/download_database.py` | 637 | Checkpoints currently live in S3 under `.checkpoints/`; move to the SSD |

USAspending bulk processing moves from AWS Batch onto the mini as a long-running
Dagster job. It needs resumable checkpointing on the SSD and a free-space guard
before download, since the dump is large and the run may take hours.

Then replace the four cron schedules in `data-refresh.yml` with
`ScheduleDefinition`s alongside the existing ones in `definitions.py:92-155`,
feeding `sbir_weekly_refresh_job`.

This also closes the gap recorded at `mac-mini-server.md:46` — that job is
disabled today precisely because SAM.gov and USAspending inputs are not on the
host.

Verify: each source materializes to the SSD from a cold start; schedules tick in
the Dagster daemon; `sbir_weekly_refresh_job` completes by hand before any
schedule is enabled, per the runbook.

## Phase 3 — Strip S3 from library code

`sbir_etl/utils/cloud_storage.py` (709 lines) has 16 non-test import sites, so
keep the function names and gut the S3 branches rather than deleting the module
and touching every caller.

Retain, reduced to local behavior:

- `resolve_data_path` — collapses to a local existence check
- `find_latest_sbir_awards`, `find_latest_usaspending_dump`,
  `find_latest_recipient_lookup_parquet`, `find_latest_sam_gov_parquet` — read the
  SSD tree
- `SbirAwardsSource`, `resolve_sbir_awards_csv`, `check_sbir_data_freshness`

Delete: `is_s3_path`, `get_s3_bucket_from_env`, `build_s3_path`,
`sync_s3_prefix_to_dir`, `upload_file_to_s3`, `cleanup_s3_cache`,
`_download_s3_to_temp`. Expect roughly 709 → 150 lines.

Then remove the S3 surface elsewhere:

- `sbir_etl/config/schemas/data.py` — `csv_path_s3`, `use_s3_first` (SBIR),
  `parquet_path_s3`, `use_s3_first` (SAM.gov), and the DuckDB `enable_httpfs` /
  `s3_region` fields
- `config/base.yaml` — lines 26-38 (`transition_contracts_output_s3_path`,
  `transition_dump_s3_prefix`, `transition_vendor_filters_s3_path`) and the
  `use_s3_first` / `*_s3` keys at 269-288
- S3 fallbacks in `extractors/sbir.py`, `extractors/sam_gov.py`,
  `extractors/usaspending.py`, `utils/data/duckdb_client.py`
- S3 branches in the asset layer: `assets/_ingestion_utils.py`,
  `sam_gov_ingestion.py`, `usaspending_ingestion.py`,
  `usaspending_database_enrichment.py`, `transition/contracts.py`,
  `modernbert/embeddings.py`, and `sbir_etl/reporting/weekly/fetching.py`

Verify: full test suite green; a cold materialization on the mini reads only from
the SSD.

## Phase 4 — Rescope CI to containers and tests

GitHub Actions becomes lint, typecheck, test, and image build only.

- **Delete** `.github/workflows/data-refresh.yml` (802 lines) and
  `.github/workflows/etl-pipeline.yml` (473 lines). Both are data-plane workflows
  whose work now belongs to the mini. Do not delete until Phase 2 has landed.
- `ci.yml` — remove the S3 data job (the OIDC block with `AWS_ROLE_ARN`,
  `S3_BUCKET: sbir-etl-prod-data`, `AWS_REGION: us-east-2`) and the `s3` path
  filter at lines 98-100. Note this job uses `continue-on-error` and falls back to
  fixtures when credentials are absent, so it reports green either way — which is
  why this coupling stayed invisible.
- `monthly-analysis.yml` — drop the `s3` choices from `sbir_source` and
  `usaspending_source`, the S3 download step, and the publish-to-S3 step.
- `weekly.yml` — drop `S3_BUCKET` (line 348) and the two `USE_S3_FIRST` overrides
  (510-511), which become redundant once the setting is gone.
- `Makefile` — the `test-s3` target (197-200) and the three `USE_S3_FIRST` toggle
  blocks (242-288).

Unchanged: Neo4j service containers, the `start-neo4j` / `stop-neo4j` composite
actions, and `build-images.yml`. That layer is already correctly scoped.

## Phase 5 — Tests

Delete outright:

- `tests/integration/test_s3_operations.py` (200 lines, real boto3 against a live
  bucket)
- `tests/unit/assets/test_transition_contracts_s3.py` (290)

Trim S3 cases from `tests/unit/utils/test_cloud_storage.py` (352),
`tests/unit/extractors/test_sam_gov_extractor.py`,
`tests/unit/assets/test_sam_gov_ingestion.py`,
`tests/integration/test_uspto_download.py`.

Remove the `requires_aws` marker (`pyproject.toml:221`) and the `aws_credentials`
fixture (`tests/conftest.py:433-450`).

Verify: `pytest -v --cov=sbir_etl` green; no skips attributable to missing AWS
credentials.

## Phase 6 — Dependencies and teardown

- Drop `boto3` (`pyproject.toml:41`), `boto3-stubs[s3]` (line 67), `s3path`, and
  any `pip install awscli` steps.
- Tear down the live AWS resources: the `sbir-etl-prod-data` bucket, the GitHub
  OIDC role, the Batch compute environments and job queue, and the
  `AWS_ROLE_ARN` repository secret.

Verify: `rg -i 'boto3|s3://|amazonaws'` returns only historical references in
documentation; the AWS account shows no remaining billable resources.

## Scope

Roughly 3,500 lines removed and 1,000 rewritten across the six phases.
