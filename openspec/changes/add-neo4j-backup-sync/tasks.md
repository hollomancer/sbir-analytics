# Add Neo4j Backup Sync — Implementation Tasks

Change: add-neo4j-backup-sync  
Status: Planned / Draft  
Owners: infra-team, data-platform, devops, security  
Reviewers: DBAs, platform, security

Goal
----
Provide a secure, auditable, and automated mechanism to synchronize Neo4j logical backups (produced by the repo's backup tooling) to remote object storage (S3-compatible). The work must be additive: local backup/restore remains available without cloud access; remote sync is opt-in and gated by configuration and CI secrets.

High-level acceptance criteria
- A robust upload script exists that uploads backup dumps + metadata to S3 (or S3-compatible endpoint) and verifies upload integrity (checksum/ETag).
- A verify-restore script exists that can (in a controlled environment) download a backup and exercise either a logical load or a consistency check to validate the backup.
- A GitHub Actions workflow (draftable dry-run variant) exists to run backup+upload on a schedule and can be run in dry-run mode without secrets.
- Documentation is added to `docs/neo4j/server.md` and `config/README.md` describing configuration, IAM requirements, retention, and operational runbook.
- All secrets are handled securely (OIDC role assumption preferred; no long-lived credentials committed).
- Tests (unit/integration) exist that validate upload logic using a local S3-compatible endpoint (minio) or mocked client.

Tasks
-----

## 1. Upload Script & Metadata (implementation)
- [ ] 1.1 Create `scripts/neo4j/upload_backup_to_s3.sh` (or `.py`) that:
  - Accepts CLI args: `--file`, `--bucket`, `--prefix`, `--region`, `--kms-key` (optional), `--sse` (optional), `--dry-run`.
  - Computes a strong checksum (sha256) for the backup file.
  - Optionally compresses the file (configurable).
  - Uploads to S3 with server-side encryption (SSE-S3 or SSE-KMS if provided).
  - Writes object metadata and/or a companion `<file>.meta.json` with: sha256, created_by (CI/job), commit SHA, db_name, timestamp, size, software version (script / repo sha).
  - Performs post-upload verification (head-object and metadata comparison), retries on transient failures, and returns meaningful non-zero exit codes on fatal failures.
  - Is idempotent: if the same key with matching checksum already exists, it exits 0 with a "skipped" status.
  - Logs structured events to stdout/stderr suitable for CI artifacts.
  - Includes a "prune local copy" option to remove local dumps after successful upload (opt-in).
  - Notes: keep implementation provider-agnostic by supporting aws cli / s3api and an S3 endpoint override for minio.

- [ ] 1.2 Add tests for upload script:
  - Unit tests for checksum calculation, metadata generation, and key naming.
  - Integration test using a local MinIO container (or test double) that verifies upload and metadata storage.

## 2. Verify / Restore Check Script (implementation)
- [ ] 2.1 Create `scripts/neo4j/verify_restore.sh` (or `.py`) that:
  - Accepts `--s3-uri`/`--bucket` + `--key` or `--file` and `--db` target.
  - Downloads backup to a temporary workspace.
  - Optionally runs `neo4j-admin check-consistency` (if available for the dump/Neo4j version) or attempts a load into a staging ephemeral Neo4j instance and runs a smoke query (configurable).
  - Supports `--dry-run` mode and `--skip-load` for cases where only checksum verification is desired.
  - Produces structured logs and a verification exit code.
- [ ] 2.2 Add integration tests for verify script (use MinIO + ephemeral Neo4j container in CI integration test job).

## 3. CI Workflow & Scheduling (automation)
- [ ] 3.1 Add a draft GitHub Actions workflow `ci/neo4j-backup-sync.yml` that:
  - Runs on schedule (cron) and supports manual dispatch.
  - Runs in two modes:
    - Dry-run: builds environment and performs all steps except uploading (no secrets required).
    - Live: assumes an IAM role via OIDC or uses CI secrets to obtain credentials, runs backup + upload, then optionally triggers verify-restore for a recent backup.
  - Steps:
    - Checkout repo.
    - Optionally build image or use runner tools.
    - Run `scripts/neo4j/backup.sh` to produce a `.dump` file.
    - Run `scripts/neo4j/upload_backup_to_s3.sh` for upload.
    - Optionally run `scripts/neo4j/verify_restore.sh` in a controlled ephemeral environment.
    - On failure: upload logs as artifacts, fail the job, and optionally notify via configured channels.
  - Provide good defaults and a `DRY_RUN=1` gate so maintainers can validate the workflow without secrets.
- [ ] 3.2 Document steps to enable role-based credentials for GitHub Actions (OIDC) in the repo docs (detailed in config docs; do not commit secrets).

## 4. IAM & Security (ops coordination)
- [ ] 4.1 Provide example minimal IAM policy for upload-only role (JSON snippet) and example KMS permissions if SSE-KMS is required:
  - `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` limited to the configured bucket prefix.
  - `kms:Encrypt`, `kms:Decrypt`, `kms:GenerateDataKey` limited to a single KMS key ARN (if used).
- [ ] 4.2 Document recommended OIDC trust policy for GitHub Actions to assume the role (example statements).
- [ ] 4.3 Coordinate with infra/ops to provision a dedicated backup bucket and role OR provide a clear runbook to request those (documented in change).

## 5. Retention & Bucket Lifecycle (ops)
- [ ] 5.1 Add recommended lifecycle configuration samples in docs:
  - dev: keep 7 days
  - staging: keep 30 days
  - prod: keep 90 (or XXX per org policy)
- [ ] 5.2 Provide sample lifecycle JSON/Terraform snippet for infra team to apply.

## 6. Documentation & Runbook (docs)
- [ ] 6.1 Update `docs/neo4j/server.md`:
  - Add a new "Remote Backup Sync (S3)" section explaining bucket naming, prefix conventions, how to enable sync, and how to run verify-restore.
  - Provide examples for running the upload locally with `aws cli` (if operator chooses to upload manually).
- [ ] 6.2 Update `config/README.md` and `config/docker.yaml` (if applicable) to include:
  - `BACKUP_S3_BUCKET`, `BACKUP_S3_PREFIX`, `BACKUP_RETENTION_DAYS`, `BACKUP_USE_SSE_KMS`, `BACKUP_KMS_KEY_ARN`, `BACKUP_S3_ENDPOINT` (for minio).
  - Explain precedence and secret handling for credentials / role ARNs.
- [ ] 6.3 Add a short "How to provision" note: who to contact to create bucket + IAM role, and the minimum steps to enable OIDC for GitHub Actions.

## 7. Testing & Validation (QA)
- [ ] 7.1 Unit tests for upload and verify scripts (mock S3 interactions).
- [ ] 7.2 Integration tests using Minio + ephemeral Neo4j within CI (or in a separate integration pipeline):
  - Upload a backup to Minio and verify metadata.
  - Run verify-restore against an ephemeral Neo4j and assert minimal smoke query results.
- [ ] 7.3 Manual acceptance run in staging: schedule a one-off job, run full backup+upload+verify, and inspect bucket + metadata.

## 8. Pre-commit / CI Secrets Guard (safety)
- [ ] 8.1 Add a lightweight pre-commit hook or CI check that scans for suspicious secret patterns committed into tracked files (e.g., "NEO4J_PASSWORD=" or AWS secret-looking strings).
- [ ] 8.2 Document remediation steps in the runbook if a secret is accidentally committed.

## 9. Optional Enhancements (future)
- [ ] 9.1 Add optional multipart uploads for very large dumps and support for ETag vs sha256 verification strategies.
- [ ] 9.2 Add database size estimation metadata during backup to help choose retention tiers.
- [ ] 9.3 Integrate with an existing backup catalog service or metadata DB if the org uses one.
- [ ] 9.4 Add cross-region replication guidance (if required by DR policy).
- [ ] 9.5 Add an automatic verify-restore scheduled job (weekly) that loads a recent backup into a staging instance and runs a deeper validation.

Implementation notes & conventions
---------------------------------
- Scripts MUST:
  - Avoid embedding long-lived credentials in code.
  - Provide `--dry-run` and `--verbose` flags for safe testing.
  - Exit with meaningful non-zero codes on failure; log structured messages for CI artifact uploads.
- CI workflows MUST:
  - Support a DRY_RUN mode that can be executed without secrets.
  - Use OIDC for credential exchange where possible. If secrets are necessary, store them in the repository's secrets manager and document their use.
- Documentation MUST:
  - Describe how to set up the bucket, lifecycle, and IAM role.
  - Provide step-by-step instructions for operators to run manual upload and a restore test.

Estimated effort
----------------
- Upload + verify scripts with unit tests: 2 days
- CI workflow + OIDC integration guidance (coordination with infra): 1–2 days (plus infra lead time to provision role & bucket)
- Integration tests & minio-based CI jobs: 1 day
- Docs, runbook, and examples: 0.5–1 day
- Total (developer effort, excluding infra provisioning): ~4–6 working days

Delivery plan (recommended)
---------------------------
1. Implement `upload_backup_to_s3.sh` with robust CLI and unit tests. Add dry-run behavior. (PR)
2. Implement `verify_restore.sh` scaffold and unit tests. (PR)
3. Add draft GitHub Actions workflow `ci/neo4j-backup-sync.yml` (DRY_RUN mode). (PR)
4. Add docs and IAM policy snippets. (PR)
5. Coordinate with infra to provision bucket + role and test the live workflow in staging.
6. After infra confirms, enable the workflow's live mode and validate via the integration test.

Open questions for stakeholders
------------------------------
- Which environments should have scheduled backups (prod only, or prod+staging)?
- Desired retention days per environment (dev/staging/prod).
- Whether to require SSE-KMS from day one or fall back to SSE-S3 for initial rollout.
- Who is the infra owner who will provision the bucket + IAM role and coordinate OIDC trust?

Task tracking
-------------
This file represents the implementation checklist. As tasks are completed, the owning engineer should update this tasks.md with checkboxes and short notes describing what was implemented and where (file paths/PR numbers). When the work is finished and accepted, mark the change as complete and link any CI runs demonstrating success.
